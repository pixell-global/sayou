"""mem0 memory adapter for benchmarking.

Uses mem0's LLM-based fact extraction and embedding-based retrieval.
This is the most popular open-source memory layer for LLM applications,
making it a useful comparison point for Sayou.

Retrieval uses an agentic approach: an LLM agent tries multiple search
queries to find all relevant memories, rather than a single-shot search.

Requires: pip install mem0ai
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from benchmarks.runner.adapter import (
    IngestMetrics,
    MemoryAdapter,
    RetrievalResult,
    SessionData,
)


class Mem0Adapter(MemoryAdapter):
    """mem0 with OpenAI LLM + embeddings and Qdrant vector store.

    Ingestion: m.add() feeds conversation messages through LLM fact extraction.
    Retrieval: Agentic LLM loop that tries multiple search queries to find
    all relevant memories.
    """

    name = "mem0"

    def __init__(self):
        self._memory = None
        self._tmpdir: tempfile.TemporaryDirectory | None = None
        self._config: dict | None = None

    @classmethod
    def available(cls) -> bool:
        try:
            import mem0  # noqa: F401
            return bool(_get_openai_key())
        except ImportError:
            return False

    async def setup(self) -> None:
        api_key = _get_openai_key()

        self._tmpdir = tempfile.TemporaryDirectory(prefix="samb_mem0_")
        qdrant_path = str(Path(self._tmpdir.name) / "qdrant")

        self._config = {
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "api_key": api_key,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": api_key,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "samb_bench",
                    "path": qdrant_path,
                },
            },
            "version": "v1.1",
        }

        self._memory = await asyncio.to_thread(_create_memory, self._config)

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        start = time.perf_counter()
        total_bytes = 0

        messages = []
        for msg in session.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content,
            })
            total_bytes += len(msg.content.encode("utf-8"))

        user_id = _user_id(scenario_id)

        # mem0's add() is sync and uses internal threads — run in executor
        await asyncio.to_thread(
            self._memory.add,
            messages,
            user_id=user_id,
            metadata={"session_id": session.session_id},
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return IngestMetrics(time_ms=elapsed_ms, storage_bytes=total_bytes)

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        # Strip oracle format if present
        if query.startswith("EVIDENCE:"):
            parts = query.split("|QUERY:", 1)
            query = parts[1] if len(parts) > 1 else query

        start = time.perf_counter()

        user_id = _user_id(scenario_id)

        # Agentic retrieval: LLM tries multiple search queries
        context, num_results, source_sessions = await _agentic_mem0_retrieve(
            memory=self._memory,
            user_id=user_id,
            query=query,
            k=k,
            api_key=_get_openai_key(),
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        return RetrievalResult(
            context=context,
            source_sessions=source_sessions,
            retrieval_time_ms=elapsed_ms,
            num_results=num_results,
            context_tokens=len(context) // 4,
        )

    async def reset(self, scenario_id: str) -> None:
        user_id = _user_id(scenario_id)
        try:
            await asyncio.to_thread(self._memory.delete_all, user_id=user_id)
        except Exception:
            pass

        # Recreate Memory object to avoid SQLite threading issues
        if self._config:
            self._memory = await asyncio.to_thread(_create_memory, self._config)

    async def teardown(self) -> None:
        self._memory = None
        self._config = None
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None


def _create_memory(config: dict):
    """Create a mem0 Memory instance (sync, runs in thread)."""
    from mem0 import Memory
    return Memory.from_config(config)


# ── Agentic retrieval for mem0 ───────────────────────────────────────

_MEM0_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_memories",
            "description": "Search the memory store for memories matching a query. Uses embedding similarity. Try different phrasings to find more results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_memories",
            "description": "Get ALL stored memories for the user. Use this to see everything available when search results are sparse.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Call when you have gathered enough context.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

_MEM0_AGENT_PROMPT = """\
You are a retrieval agent searching a memory store to find information relevant to a user's query.

The memory store contains extracted facts from past conversations. Each memory is a short text \
snippet (1-2 sentences) capturing a specific fact, decision, or preference.

Your goal: find ALL relevant memories by trying multiple search queries.

Strategy:
1. Search with the main query first.
2. Extract key terms, names, numbers, or technical concepts from the query and search for each.
3. If results are sparse, try broader or rephrased queries.
4. Use get_all_memories if targeted searches aren't finding enough.
5. Call "done" when you have enough context or exhausted options.

Try at least 2-3 different search queries before giving up.
"""

_MAX_MEM0_ROUNDS = 6


async def _agentic_mem0_retrieve(
    memory, user_id: str, query: str, k: int, api_key: str,
) -> tuple[str, int, list[str]]:
    """Agentic retrieval loop for mem0."""
    import openai

    client = openai.AsyncOpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": _MEM0_AGENT_PROMPT},
        {"role": "user", "content": f"Find all relevant context for:\n\n{query}"},
    ]

    all_memories: dict[str, str] = {}  # id -> text (dedup)
    source_sessions: list[str] = []
    seen_sessions: set[str] = set()

    for _round in range(_MAX_MEM0_ROUNDS):
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=_MEM0_TOOLS,
                tool_choice="auto",
                temperature=0,
                max_tokens=512,
            )
        except Exception:
            break

        choice = response.choices[0]
        if not choice.message.tool_calls:
            break

        messages.append(choice.message)

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if fn_name == "search_memories":
                search_query = args.get("query", query)
                try:
                    results = await asyncio.to_thread(
                        memory.search, search_query, user_id=user_id, limit=k,
                    )
                    mems = _extract_memories(results)
                    new_count = 0
                    lines = []
                    for mem_id, text, sid in mems:
                        if mem_id not in all_memories:
                            all_memories[mem_id] = text
                            new_count += 1
                            if sid and sid not in seen_sessions:
                                source_sessions.append(sid)
                                seen_sessions.add(sid)
                        lines.append(f"• {text}")
                    result_str = "\n".join(lines) if lines else "(no results)"
                    result_str += f"\n({new_count} new, {len(all_memories)} total collected)"
                except Exception as e:
                    result_str = f"(error: {e})"

            elif fn_name == "get_all_memories":
                try:
                    results = await asyncio.to_thread(
                        memory.get_all, user_id=user_id,
                    )
                    mems = _extract_memories(results)
                    new_count = 0
                    lines = []
                    for mem_id, text, sid in mems:
                        if mem_id not in all_memories:
                            all_memories[mem_id] = text
                            new_count += 1
                            if sid and sid not in seen_sessions:
                                source_sessions.append(sid)
                                seen_sessions.add(sid)
                        lines.append(f"• {text}")
                    result_str = "\n".join(lines[:30]) if lines else "(no memories)"
                    if len(lines) > 30:
                        result_str += f"\n... ({len(lines)} total)"
                    result_str += f"\n({new_count} new, {len(all_memories)} total collected)"
                except Exception as e:
                    result_str = f"(error: {e})"

            elif fn_name == "done":
                result_str = "Search complete."

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str,
            })

            if fn_name == "done":
                break

        if fn_name == "done":
            break

    texts = list(all_memories.values())[:k]
    context = "\n\n---\n\n".join(texts) if texts else ""
    return context, len(texts), source_sessions


def _extract_memories(results) -> list[tuple[str, str, str]]:
    """Extract (id, text, session_id) tuples from mem0 results."""
    if isinstance(results, dict):
        memories = results.get("results", results.get("memories", []))
    elif isinstance(results, list):
        memories = results
    else:
        return []

    out = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        mem_id = mem.get("id", str(id(mem)))
        text = mem.get("memory", "")
        meta = mem.get("metadata", {}) or {}
        sid = meta.get("session_id", "")
        if text:
            out.append((str(mem_id), text, sid))
    return out


def _user_id(scenario_id: str) -> str:
    return f"samb_{scenario_id.replace('/', '_')}"


def _get_openai_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    key = os.environ.get("SAYOU_AGENT_OPENAI_API_KEY")
    if key:
        return key
    env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in ("OPENAI_API_KEY", "SAYOU_AGENT_OPENAI_API_KEY"):
                    return v.strip()
    return None
