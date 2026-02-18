"""Oracle adapter — upper bound returning exact evidence sessions."""

from __future__ import annotations

import time

from benchmarks.runner.adapter import (
    IngestMetrics,
    MemoryAdapter,
    RetrievalResult,
    SessionData,
)


class OracleAdapter(MemoryAdapter):
    """Returns full text of exact evidence sessions listed in QA pairs.

    This adapter cheats by using the ground-truth evidence_sessions field.
    It separates retrieval failures from reasoning failures — if the oracle
    scores poorly, the QA pair or judge is the problem, not retrieval.

    Note: retrieve() requires the caller to pass the evidence session IDs
    via the query parameter formatted as "EVIDENCE:s1,s2|QUERY:actual question".
    The CLI handles this formatting.
    """

    name = "oracle"

    def __init__(self):
        # scenario_id -> session_id -> full text
        self._sessions: dict[str, dict[str, str]] = {}

    async def setup(self) -> None:
        pass

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        if scenario_id not in self._sessions:
            self._sessions[scenario_id] = {}

        text = _session_to_text(session)
        self._sessions[scenario_id][session.session_id] = text

        return IngestMetrics(
            time_ms=0.0,
            storage_bytes=len(text.encode("utf-8")),
        )

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        start = time.perf_counter()

        # Parse evidence session IDs from the query format
        evidence_ids, _ = _parse_oracle_query(query)
        scenario_sessions = self._sessions.get(scenario_id, {})

        chunks = []
        source_sessions = []
        for sid in evidence_ids:
            text = scenario_sessions.get(sid)
            if text:
                chunks.append(text)
                source_sessions.append(sid)

        context = "\n\n---\n\n".join(chunks)
        elapsed_ms = (time.perf_counter() - start) * 1000

        return RetrievalResult(
            context=context,
            source_sessions=source_sessions,
            retrieval_time_ms=elapsed_ms,
            num_results=len(chunks),
            context_tokens=_approx_tokens(context),
        )

    async def reset(self, scenario_id: str) -> None:
        self._sessions.pop(scenario_id, None)

    async def teardown(self) -> None:
        self._sessions.clear()


def _session_to_text(session: SessionData) -> str:
    """Convert a session to readable text."""
    lines = [f"Session {session.session_id} — Day {session.day or '?'}"]
    if session.time_of_day:
        lines[0] += f", {session.time_of_day}"
    if session.request:
        lines.append(f"Topic: {session.request}")
    lines.append("")

    for msg in session.messages:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content}")
        lines.append("")

    return "\n".join(lines)


def _parse_oracle_query(query: str) -> tuple[list[str], str]:
    """Parse 'EVIDENCE:s1,s2|QUERY:actual question' format.

    Returns (evidence_ids, actual_query).
    """
    if query.startswith("EVIDENCE:"):
        parts = query.split("|QUERY:", 1)
        evidence_part = parts[0].removeprefix("EVIDENCE:")
        evidence_ids = [s.strip() for s in evidence_part.split(",") if s.strip()]
        actual_query = parts[1] if len(parts) > 1 else ""
        return evidence_ids, actual_query
    return [], query


def _approx_tokens(text: str) -> int:
    """Rough token count (~4 chars per token)."""
    return len(text) // 4
