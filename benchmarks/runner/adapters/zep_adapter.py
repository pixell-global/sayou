"""Zep Cloud memory adapter for benchmarking.

Zep uses a temporal knowledge graph + vector embeddings for memory.
It scores ~71% on LongMemEval, the highest of any OSS memory system.

Requires: pip install zep-cloud
Environment: ZEP_API_KEY (free tier: 1,000 episodes/month)

Uses the Zep v3 SDK (zep-cloud >= 3.x) which uses threads instead of
sessions and has a different Message schema.
"""

from __future__ import annotations

import asyncio
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

    Retrieval: Combines thread user context with graph search results.
    """

    name = "zep"

    def __init__(self):
        self._client = None
        # Map scenario_id -> list of thread IDs created in Zep
        self._thread_ids: dict[str, list[str]] = {}
        # Map scenario_id -> user_id in Zep
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

        # Create a unique user for this scenario if not exists
        if scenario_id not in self._user_ids:
            user_id = f"samb_{scenario_id}_{uuid.uuid4().hex[:8]}"
            try:
                await self._client.user.add(user_id=user_id)
            except Exception:
                pass  # User may already exist
            self._user_ids[scenario_id] = user_id

        user_id = self._user_ids[scenario_id]

        # Create a Zep thread for this conversation session
        thread_id = f"{scenario_id}_{session.session_id}_{uuid.uuid4().hex[:8]}"
        try:
            await self._client.thread.create(
                thread_id=thread_id,
                user_id=user_id,
            )
        except Exception:
            pass

        self._thread_ids.setdefault(scenario_id, []).append(thread_id)

        # Convert messages to Zep format and add to thread
        zep_messages = []
        for msg in session.messages:
            zep_messages.append(ZepMessage(
                role=msg.role,
                content=msg.content,
            ))
            total_bytes += len(msg.content.encode("utf-8"))

        # Add messages to the thread
        await self._client.thread.add_messages(
            thread_id,
            messages=zep_messages,
        )

        # Wait a moment for Zep's server-side processing
        await asyncio.sleep(1)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return IngestMetrics(time_ms=elapsed_ms, storage_bytes=total_bytes)

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        # Strip oracle format if present
        if query.startswith("EVIDENCE:"):
            parts = query.split("|QUERY:", 1)
            query = parts[1] if len(parts) > 1 else query

        start = time.perf_counter()
        chunks: list[str] = []
        source_sessions: list[str] = []

        user_id = self._user_ids.get(scenario_id)
        zep_threads = self._thread_ids.get(scenario_id, [])

        # 1. Get user context from each thread
        for thread_id in zep_threads:
            try:
                ctx = await self._client.thread.get_user_context(thread_id)
                if ctx and ctx.context:
                    chunks.append(ctx.context)
                    # Extract original session ID from the thread ID
                    # Format: scenario-XX_sN_uuid
                    parts = thread_id.split("_")
                    if len(parts) >= 2:
                        original_sid = parts[1]
                        if original_sid not in source_sessions:
                            source_sessions.append(original_sid)
                if len(chunks) >= k:
                    break
            except Exception:
                continue

        # 2. Graph search for relevant facts
        if user_id and len(chunks) < k:
            try:
                graph_results = await self._client.graph.search(
                    user_id=user_id,
                    query=query,
                    limit=k,
                )
                for edge in (graph_results.edges or []):
                    fact = getattr(edge, "fact", None) or ""
                    if fact and fact not in chunks:
                        chunks.append(fact)
                    if len(chunks) >= k:
                        break
            except Exception:
                pass

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
        """Delete Zep threads and user for this scenario."""
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
        # Clean up any remaining threads
        for scenario_id in list(self._thread_ids.keys()):
            await self.reset(scenario_id)
        self._client = None


def _get_zep_key() -> str | None:
    """Get Zep API key from environment or .env file."""
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
