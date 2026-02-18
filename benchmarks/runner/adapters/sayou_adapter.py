"""Sayou workspace adapter for benchmarking.

Uses the ConversationObserver to ingest sessions — the same pipeline that
runs in production. The observer extracts observations (decisions, discoveries,
preferences, facts) from each conversation turn and writes structured files
to the workspace. This means the benchmark tests retrieval against the
observer's output, not raw transcripts.

Retrieval uses an **agentic approach**: an LLM agent iteratively explores the
workspace using tools (list, search, grep, read, search_chunks), mimicking
how Claude Code uses sayou in production. This tests the full retrieval
pipeline rather than a single-shot keyword search.
"""

from __future__ import annotations

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


class SayouAdapter(MemoryAdapter):
    """Evaluates Sayou with the observer pipeline (production-realistic).

    Ingestion: Each session's turns are fed through ConversationObserver,
    which uses GPT-4o-mini to extract observations and writes structured
    conversation files to the workspace.

    Retrieval: Uses search + grep + search_chunks across the workspace.
    """

    name = "sayou"

    def __init__(self):
        self._tmpdir: tempfile.TemporaryDirectory | None = None
        self._ws = None
        self._db_path: Path | None = None
        self._observer = None
        # Maps file path -> set of original session IDs that contributed to it
        self._path_to_sessions: dict[str, set[str]] = {}

    @classmethod
    def available(cls) -> bool:
        try:
            from agent.observer import ConversationObserver  # noqa: F401
        except ImportError:
            return False
        # Need an OpenAI key for the observer (check both env vars)
        return bool(_get_openai_key())

    async def setup(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="samb_sayou_")
        self._db_path = Path(self._tmpdir.name) / "bench.db"
        storage_path = Path(self._tmpdir.name) / "storage"
        storage_path.mkdir()

        from sayou.workspace import Workspace
        self._ws = Workspace(
            slug="default",
            database_url=f"sqlite+aiosqlite:///{self._db_path}",
            storage_path=str(storage_path),
        )
        await self._ws.open()

        from agent.observer import ConversationObserver
        api_key = _get_openai_key()
        if not api_key:
            raise RuntimeError("No OpenAI API key found for observer")
        self._observer = ConversationObserver(api_key=api_key, model="gpt-4o-mini")

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        """Ingest a session by feeding each turn through the observer."""
        start = time.perf_counter()
        total_bytes = 0

        # Split session into turns (user message + assistant response pairs)
        turns = _extract_turns(session)
        history: list[dict] = []

        # Prefix with scenario ID to avoid path collisions across scenarios
        # (all scenarios use s1-s6, so without prefix paths would collide
        # after soft-delete between scenarios)
        sid_prefix = scenario_id.replace("scenario-", "")

        for turn_idx, (user_msg, assistant_events) in enumerate(turns):
            # Unique session ID per turn so observer writes separate files
            turn_session_id = f"{sid_prefix}_{session.session_id}_t{turn_idx}"

            await self._observer.observe(
                workspace=self._ws,
                session_id=turn_session_id,
                user_message=user_msg,
                collected_events=assistant_events,
                artifact_paths=[],
                history=history,
            )

            # Track which original session ID this turn belongs to
            # Observer writes to conversations/{date}-{session_id[:8]}.md
            conv_path = self._observer._conversation_path(turn_session_id)
            self._path_to_sessions.setdefault(conv_path, set()).add(session.session_id)

            # Build history for next turn (observer uses this for context)
            history.append({"role": "user", "content": user_msg})
            for evt in assistant_events:
                if evt["type"] == "content":
                    text = evt["data"].get("text", "")
                    if text:
                        history.append({"role": "assistant", "content": text})

        # Measure storage from what was actually written
        try:
            listing = await self._ws.list("conversations", recursive=True)
            for f in listing.get("files", []):
                file_data = await self._ws.read(f["path"])
                total_bytes += len(file_data.get("content", "").encode("utf-8"))
        except Exception:
            pass

        elapsed_ms = (time.perf_counter() - start) * 1000
        return IngestMetrics(time_ms=elapsed_ms, storage_bytes=total_bytes)

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        # Strip oracle format if present
        if query.startswith("EVIDENCE:"):
            parts = query.split("|QUERY:", 1)
            query = parts[1] if len(parts) > 1 else query

        start = time.perf_counter()

        seen_paths: set[str] = set()
        file_contents: list[str] = []
        source_sessions: list[str] = []
        tool_hits = {"list": 0, "search": 0, "grep": 0, "read": 0, "search_chunks": 0}

        def _track_file(path: str, content: str, tool: str):
            """Track a file that was read for the first time."""
            if path in seen_paths:
                return
            seen_paths.add(path)
            file_contents.append(content)
            tool_hits[tool] += 1
            for sid in self._path_to_sessions.get(path, set()):
                if sid not in source_sessions:
                    source_sessions.append(sid)

        # Run agentic retrieval loop
        context = await _agentic_retrieve(
            ws=self._ws,
            query=query,
            k=k,
            track_file=_track_file,
            tool_hits=tool_hits,
            api_key=_get_openai_key(),
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        return RetrievalResult(
            context=context,
            source_sessions=source_sessions,
            retrieval_time_ms=elapsed_ms,
            num_results=len(file_contents),
            context_tokens=len(context) // 4,
            metadata={"tool_hits": tool_hits},
        )

    async def reset(self, scenario_id: str) -> None:
        """Create a fresh workspace between scenarios.

        Soft-delete doesn't release the UNIQUE constraint on file paths,
        so files from scenario N would block scenario N+1 (which reuses
        session IDs s1-s6). Instead, tear down and recreate the workspace
        with a fresh SQLite database.
        """
        self._path_to_sessions.clear()
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Remove old DB and storage, create fresh ones
        if self._tmpdir:
            import shutil
            db_path = Path(self._tmpdir.name) / "bench.db"
            storage_path = Path(self._tmpdir.name) / "storage"
            if db_path.exists():
                db_path.unlink()
            # Also remove WAL/SHM files if present
            for suffix in ("-wal", "-shm"):
                wal = db_path.parent / (db_path.name + suffix)
                if wal.exists():
                    wal.unlink()
            if storage_path.exists():
                shutil.rmtree(storage_path)
            storage_path.mkdir()

            from sayou.workspace import Workspace
            self._ws = Workspace(
                slug="default",
                database_url=f"sqlite+aiosqlite:///{db_path}",
                storage_path=str(storage_path),
            )
            await self._ws.open()

    async def teardown(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._observer = None
        self._path_to_sessions.clear()
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None


def _extract_turns(session: SessionData) -> list[tuple[str, list[dict]]]:
    """Split a session into (user_message, assistant_events) pairs.

    Each turn is one user message followed by the assistant's response,
    matching how the observer processes real conversations.
    """
    turns: list[tuple[str, list[dict]]] = []
    current_user_msg: str | None = None
    current_events: list[dict] = []

    for msg in session.messages:
        if msg.role == "user":
            # Flush previous turn if we have one
            if current_user_msg is not None:
                turns.append((current_user_msg, current_events))
                current_events = []
            current_user_msg = msg.content
        elif msg.role == "assistant" and current_user_msg is not None:
            # Build content events matching the observer's expected format
            current_events.append({
                "type": "content",
                "data": {"text": msg.content},
            })

    # Flush last turn
    if current_user_msg is not None:
        turns.append((current_user_msg, current_events))

    return turns


# ── Agentic retrieval ─────────────────────────────────────────────

# Tool definitions for the OpenAI function-calling API
_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_folder",
            "description": "List files and subfolders in a workspace folder. Use this first to understand the workspace structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Folder path to list (default: '/')",
                        "default": "/",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list recursively",
                        "default": False,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Full-text search across all files. Returns ranked results. Good for finding files related to a topic.",
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
            "name": "grep",
            "description": "Search for exact text in file contents. Like grep — finds files containing a specific string. Use this to find specific values, numbers, names, or technical terms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for (exact substring match)",
                    },
                    "path_pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files (e.g., 'conversations/**')",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full content of a file. Use this after finding relevant files via search, grep, or list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_chunks",
            "description": "Search at the chunk level for more precise matches within files. Each file is split into sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Call this when you have gathered enough context to answer the query. Pass all the relevant content you've collected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief note about what you found",
                    },
                },
            },
        },
    },
]

_AGENT_SYSTEM_PROMPT = """\
You are a retrieval agent exploring a workspace to find information relevant to a user's query.

The workspace contains structured observation files extracted from conversations. Files are \
organized under folders like conversations/, and contain markdown with YAML frontmatter.

Your goal: find ALL relevant files and read them to gather comprehensive context for the query.

Strategy:
1. Start by listing the workspace root to understand the folder structure.
2. Use search/grep to find relevant files. Try multiple queries — rephrase, use specific \
terms, technical keywords, numbers, or names from the query.
3. Read promising files to get their full content.
4. If search results are sparse, try grep with specific terms (e.g., "bcrypt", "JWT", "$612", \
"rate limit"). Grep finds exact substrings that full-text search might miss.
5. Call "done" when you have gathered enough context OR exhausted your search options.

Important:
- Be thorough. Try at least 2-3 different search/grep queries before giving up.
- Read files that look relevant — don't just list them.
- The workspace may have observations spread across multiple files. One file per conversation \
turn is common.
"""

_MAX_AGENT_ROUNDS = 8  # Max LLM round-trips (tool calls)


async def _agentic_retrieve(
    ws,
    query: str,
    k: int,
    track_file,
    tool_hits: dict,
    api_key: str,
) -> str:
    """Run an LLM agent loop that explores the workspace to find context.

    The agent uses workspace tools (list, search, grep, read, search_chunks)
    iteratively, mimicking how Claude Code explores a sayou workspace.
    Returns the concatenated content of all files the agent read.
    """
    import openai

    client = openai.AsyncOpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": _AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Find all relevant context for this query:\n\n{query}"},
    ]

    collected_content: list[str] = []
    read_paths: set[str] = set()

    for _round in range(_MAX_AGENT_ROUNDS):
        try:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=_TOOLS,
                tool_choice="auto",
                temperature=0,
                max_tokens=1024,
            )
        except Exception:
            break

        choice = response.choices[0]

        # If the model wants to stop (no tool calls), we're done
        if not choice.message.tool_calls:
            break

        # Add the assistant message with tool calls
        messages.append(choice.message)

        # Execute each tool call
        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            result_str = await _execute_tool(
                ws, fn_name, args, read_paths, collected_content,
                track_file, tool_hits, k,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str,
            })

            # If agent called "done", stop
            if fn_name == "done":
                context = "\n\n---\n\n".join(collected_content[:k])
                return context

    # Agent exhausted rounds or stopped — return what we have
    context = "\n\n---\n\n".join(collected_content[:k])
    return context


async def _execute_tool(
    ws, fn_name: str, args: dict,
    read_paths: set, collected_content: list,
    track_file, tool_hits: dict, k: int,
) -> str:
    """Execute a single tool call and return the result as a string."""
    try:
        if fn_name == "list_folder":
            path = args.get("path", "/")
            recursive = args.get("recursive", False)
            result = await ws.list(path, recursive=recursive)
            # Format listing compactly
            files = result.get("files", [])
            folders = result.get("folders", [])
            lines = []
            for f in folders:
                lines.append(f"📁 {f.get('name', f.get('path', ''))}/")
            for f in files:
                lines.append(f"📄 {f.get('path', f.get('name', ''))}")
            tool_hits["list"] += 1
            if not lines:
                return "(empty folder)"
            return "\n".join(lines[:50])  # Cap output

        elif fn_name == "search":
            query = args.get("query", "")
            result = await ws.search(query=query)
            hits = result.get("results", [])
            tool_hits["search"] += 1
            if not hits:
                return "(no results)"
            lines = []
            for r in hits[:10]:
                path = r.get("path", "")
                snippet = r.get("snippet", r.get("content_text", ""))
                if snippet and len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                lines.append(f"• {path}: {snippet}")
            return "\n".join(lines)

        elif fn_name == "grep":
            query = args.get("query", "")
            path_pattern = args.get("path_pattern")
            result = await ws.grep(query, path_pattern=path_pattern)
            hits = result.get("results", [])
            tool_hits["grep"] += 1
            if not hits:
                return "(no matches)"
            lines = []
            for r in hits[:10]:
                path = r.get("path", "")
                matches = r.get("matches", [])
                match_preview = "; ".join(
                    m.get("line", "")[:100] for m in matches[:3]
                )
                lines.append(f"• {path}: {match_preview}")
            return "\n".join(lines)

        elif fn_name == "read_file":
            path = args.get("path", "")
            if path in read_paths:
                return "(already read this file)"
            result = await ws.read(path, token_budget=8000)
            content = result.get("content", "")
            read_paths.add(path)
            if content:
                collected_content.append(content)
                track_file(path, content, "read")
            tool_hits["read"] += 1
            # Return truncated content so the LLM can see what it got
            if len(content) > 1500:
                return content[:1500] + f"\n... ({len(content)} chars total, full content collected)"
            return content or "(empty file)"

        elif fn_name == "search_chunks":
            query = args.get("query", "")
            limit = args.get("limit", 10)
            result = await ws.search_chunks(query, limit=limit)
            hits = result.get("results", [])
            tool_hits["search_chunks"] += 1
            if not hits:
                return "(no chunk matches)"
            lines = []
            for r in hits[:10]:
                path = r.get("path", "")
                content = r.get("content", "")
                if content and len(content) > 200:
                    content = content[:200] + "..."
                lines.append(f"• {path} [chunk {r.get('chunk_index', '?')}]: {content}")
                # Also read the full file if we haven't yet
                if path not in read_paths and len(collected_content) < k:
                    try:
                        file_data = await ws.read(path, token_budget=8000)
                        file_content = file_data.get("content", "")
                        if file_content:
                            read_paths.add(path)
                            collected_content.append(file_content)
                            track_file(path, file_content, "search_chunks")
                    except Exception:
                        pass
            return "\n".join(lines)

        elif fn_name == "done":
            return "Search complete."

        else:
            return f"(unknown tool: {fn_name})"

    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


def _get_openai_key() -> str | None:
    """Get OpenAI API key from environment or .env file."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    key = os.environ.get("SAYOU_AGENT_OPENAI_API_KEY")
    if key:
        return key
    # Try loading from .env file (same as pydantic-settings does)
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
