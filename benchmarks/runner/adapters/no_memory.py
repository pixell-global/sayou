"""No-memory adapter — lower bound baseline returning empty context."""

from __future__ import annotations

from benchmarks.runner.adapter import (
    IngestMetrics,
    MemoryAdapter,
    RetrievalResult,
    SessionData,
)


class NoMemoryAdapter(MemoryAdapter):
    """Returns empty context for all queries. Floor baseline."""

    name = "no-memory"

    async def setup(self) -> None:
        pass

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        return IngestMetrics(time_ms=0.0, storage_bytes=0)

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        return RetrievalResult(
            context="",
            source_sessions=[],
            retrieval_time_ms=0.0,
            num_results=0,
            context_tokens=0,
        )

    async def reset(self, scenario_id: str) -> None:
        pass

    async def teardown(self) -> None:
        pass
