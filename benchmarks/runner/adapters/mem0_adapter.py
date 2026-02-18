"""mem0 memory adapter for benchmarking.

Uses mem0's LLM-based fact extraction and embedding-based retrieval.
This is the most popular open-source memory layer for LLM applications,
making it a useful comparison point for Sayou.

Requires: pip install mem0ai
"""

from __future__ import annotations

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
    Retrieval: m.search() performs embedding-based similarity search.
    """

    name = "mem0"

    def __init__(self):
        self._memory = None
        self._tmpdir: tempfile.TemporaryDirectory | None = None

    @classmethod
    def available(cls) -> bool:
        try:
            import mem0  # noqa: F401
            return bool(_get_openai_key())
        except ImportError:
            return False

    async def setup(self) -> None:
        from mem0 import Memory

        self._tmpdir = tempfile.TemporaryDirectory(prefix="samb_mem0_")
        qdrant_path = str(Path(self._tmpdir.name) / "qdrant")

        api_key = _get_openai_key()

        config = {
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

        self._memory = Memory.from_config(config)

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        start = time.perf_counter()
        total_bytes = 0

        # Build conversation messages in the format mem0 expects
        messages = []
        for msg in session.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content,
            })
            total_bytes += len(msg.content.encode("utf-8"))

        # Use scenario_id as user_id for isolation between scenarios
        # Include session_id in metadata for traceability
        user_id = _user_id(scenario_id)

        self._memory.add(
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
        results = self._memory.search(query, user_id=user_id, limit=k)

        # mem0 returns a dict with "results" key (v1.1) or a list
        if isinstance(results, dict):
            memories = results.get("results", [])
        else:
            memories = results if isinstance(results, list) else []

        chunks = []
        source_sessions = []
        seen_sessions = set()

        for mem in memories:
            # Each memory has "memory" (the extracted fact) and optional "metadata"
            text = mem.get("memory", "") if isinstance(mem, dict) else str(mem)
            if text:
                chunks.append(text)
            meta = mem.get("metadata", {}) if isinstance(mem, dict) else {}
            sid = meta.get("session_id", "") if isinstance(meta, dict) else ""
            if sid and sid not in seen_sessions:
                source_sessions.append(sid)
                seen_sessions.add(sid)

        context = "\n\n---\n\n".join(chunks) if chunks else ""
        elapsed_ms = (time.perf_counter() - start) * 1000

        return RetrievalResult(
            context=context,
            source_sessions=source_sessions,
            retrieval_time_ms=elapsed_ms,
            num_results=len(chunks),
            context_tokens=len(context) // 4,
        )

    async def reset(self, scenario_id: str) -> None:
        user_id = _user_id(scenario_id)
        try:
            self._memory.delete_all(user_id=user_id)
        except Exception:
            pass

    async def teardown(self) -> None:
        self._memory = None
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None


def _user_id(scenario_id: str) -> str:
    """Create a consistent user_id from scenario_id for mem0 isolation."""
    return f"samb_{scenario_id.replace('/', '_')}"


def _get_openai_key() -> str | None:
    """Get OpenAI API key from environment or .env file."""
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
