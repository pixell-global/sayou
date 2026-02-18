"""Zep Cloud memory adapter for benchmarking.

Zep uses a temporal knowledge graph + vector embeddings for memory.
It scores ~71% on LongMemEval, the highest of any OSS memory system.

Retrieval uses an agentic approach: an LLM agent tries multiple graph
search queries and reads thread contexts to gather comprehensive context.

Requires: pip install zep-cloud
Environment: ZEP_API_KEY (free tier: 1,000 episodes/month)

Uses the Zep v3 SDK (zep-cloud >= 3.x) which uses threads instead of
sessions and has a different Message schema.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from benchmarks.runner.adapter import (
    IngestMetrics,
    MemoryAdapter,
    RetrievalResult,
    SessionData,
)


class ZepAdapter(MemoryAdapter):
    """Zep Cloud with temporal knowledge graph + vector search.

    Ingestion: Feeds conversation messages as episodes into a Zep thread.
    Zep's server-side pipeline extracts facts into a knowledge graph.

    Retrieval: Agentic LLM loop that tries multiple graph search queries
    and reads thread contexts to gather comprehensive context.
    """

    name = "zep"

    def __init__(self):
        self._client = None
        self._thread_ids: dict[str, list[str]] = {}
        self._user_ids: dict[str, str] = {}

    @classmethod
    def available(cls) -> bool:
        try:
            import zep_cloud  # noqa: F401
        except ImportError:
            return False
        return bool(_get_zep_key())

    async def setup(self) -> None:
        from zep_cloud.client import AsyncZep

        api_key = _get_zep_key()
        if not api_key:
            raise RuntimeError("ZEP_API_KEY not found")
        self._client = AsyncZep(api_key=api_key)

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        from zep_cloud import Message as ZepMessage

        start = time.perf_counter()
        total_bytes = 0

        if scenario_id not in self._user_ids:
            user_id = f"samb_{scenario_id}_{uuid.uuid4().hex[:8]}"
            try:
                await self._client.user.add(user_id=user_id)
            except Exception:
                pass
            self._user_ids[scenario_id] = user_id

        user_id = self._user_ids[scenario_id]

        thread_id = f"{scenario_id}_{session.session_id}_{uuid.uuid4().hex[:8]}"
        try:
            await self._client.thread.create(
                thread_id=thread_id,
                user_id=user_id,
            )
        except Exception:
            pass

        self._thread_ids.setdefault(scenario_id, []).append(thread_id)

        zep_messages = []
        for msg in session.messages:
            zep_messages.append(ZepMessage(
                role=msg.role,
                content=msg.content,
            ))
            total_bytes += len(msg.content.encode("utf-8"))

        await self._client.thread.add_messages(
            thread_id,
            messages=zep_messages,
        )

        await asyncio.sleep(1)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return IngestMetrics(time_ms=elapsed_ms, storage_bytes=total_bytes)

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        if query.startswith("EVIDENCE:"):
            parts = query.split("|QUERY:", 1)
            query = parts[1] if len(parts) > 1 else query

        start = time.perf_counter()

        user_id = self._user_ids.get(scenario_id)
        zep_threads = self._thread_ids.get(scenario_id, [])

        context, num_results, source_sessions = await _agentic_zep_retrieve(
            client=self._client,
            user_id=user_id,
            thread_ids=zep_threads,
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
        for thread_id in self._thread_ids.get(scenario_id, []):
            try:
                await self._client.thread.delete(thread_id)
            except Exception:
                pass

        user_id = self._user_ids.pop(scenario_id, None)
        if user_id:
            try:
                await self._client.user.delete(user_id=user_id)
            except Exception:
                pass

        self._thread_ids.pop(scenario_id, None)

    async def teardown(self) -> None:
        for scenario_id in list(self._thread_ids.keys()):
            await self.reset(scenario_id)
        self._client = None


# ── Agentic retrieval for Zep ────────────────────────────────────────

_ZEP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "graph_search",
            "description": "Search Zep's knowledge graph for facts matching a query. The graph contains extracted facts from conversations. Try different queries to find more facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for the knowledge graph",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_thread_context",
            "description": "Get the accumulated context from a specific conversation thread. Each thread represents one conversation session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_index": {
                        "type": "integer",
                        "description": "Index of the thread (0-based) from the list of available threads",
                    },
                },
                "required": ["thread_index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_threads",
            "description": "List all available conversation threads with their IDs.",
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

_ZEP_AGENT_PROMPT = """\
You are a retrieval agent searching a memory system to find information relevant to a user's query.

The memory system has:
1. A **knowledge graph** of extracted facts from past conversations. Use graph_search to query it.
2. **Conversation threads** — each thread has accumulated context from one session. Use \
get_thread_context to read a thread's context.

Your goal: find ALL relevant facts and context by trying multiple approaches.

Strategy:
1. Start with a graph search using the main query.
2. Extract key terms (names, numbers, technical concepts) and search for each separately.
3. List threads and read contexts from threads that seem relevant.
4. If graph search returns few results, try broader or rephrased queries.
5. Call "done" when you have enough context or exhausted options.

Try at least 2-3 different graph search queries before giving up.
"""

_MAX_ZEP_ROUNDS = 6


async def _agentic_zep_retrieve(
    client, user_id: str, thread_ids: list[str],
    query: str, k: int, api_key: str,
) -> tuple[str, int, list[str]]:
    """Agentic retrieval loop for Zep."""
    import openai

    oai_client = openai.AsyncOpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": _ZEP_AGENT_PROMPT},
        {"role": "user", "content": f"Find all relevant context for:\n\n{query}\n\nThere are {len(thread_ids)} conversation threads available."},
    ]

    collected: list[str] = []  # Deduplicated chunks
    seen_facts: set[str] = set()
    source_sessions: list[str] = []
    read_threads: set[int] = set()

    for _round in range(_MAX_ZEP_ROUNDS):
        try:
            response = await oai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=_ZEP_TOOLS,
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

        last_fn = None
        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            last_fn = fn_name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if fn_name == "graph_search":
                search_query = args.get("query", query)
                try:
                    graph_results = await client.graph.search(
                        user_id=user_id,
                        query=search_query,
                        limit=k,
                    )
                    lines = []
                    new_count = 0
                    for edge in (graph_results.edges or []):
                        fact = getattr(edge, "fact", None) or ""
                        if fact and fact not in seen_facts:
                            seen_facts.add(fact)
                            collected.append(fact)
                            new_count += 1
                        if fact:
                            lines.append(f"• {fact}")
                    result_str = "\n".join(lines) if lines else "(no results)"
                    result_str += f"\n({new_count} new, {len(collected)} total collected)"
                except Exception as e:
                    result_str = f"(error: {e})"

            elif fn_name == "get_thread_context":
                idx = args.get("thread_index", 0)
                if idx < 0 or idx >= len(thread_ids):
                    result_str = f"(invalid index: {idx}, must be 0-{len(thread_ids)-1})"
                elif idx in read_threads:
                    result_str = "(already read this thread)"
                else:
                    read_threads.add(idx)
                    thread_id = thread_ids[idx]
                    try:
                        ctx = await client.thread.get_user_context(thread_id)
                        if ctx and ctx.context:
                            if ctx.context not in seen_facts:
                                collected.append(ctx.context)
                                seen_facts.add(ctx.context)
                            # Track source session
                            parts = thread_id.split("_")
                            if len(parts) >= 2:
                                sid = parts[1]
                                if sid not in source_sessions:
                                    source_sessions.append(sid)
                            result_str = ctx.context
                            if len(result_str) > 1500:
                                result_str = result_str[:1500] + "..."
                        else:
                            result_str = "(no context available for this thread)"
                    except Exception as e:
                        result_str = f"(error: {e})"

            elif fn_name == "list_threads":
                lines = []
                for i, tid in enumerate(thread_ids):
                    parts = tid.split("_")
                    session_label = parts[1] if len(parts) >= 2 else tid
                    lines.append(f"[{i}] Thread: session {session_label}")
                result_str = "\n".join(lines) if lines else "(no threads)"

            elif fn_name == "done":
                result_str = "Search complete."

            else:
                result_str = f"(unknown tool: {fn_name})"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str,
            })

        if last_fn == "done":
            break

    texts = collected[:k]
    context = "\n\n---\n\n".join(texts) if texts else ""
    return context, len(texts), source_sessions


def _get_zep_key() -> str | None:
    key = os.environ.get("ZEP_API_KEY")
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
                if k.strip() == "ZEP_API_KEY":
                    return v.strip()
    return None


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
