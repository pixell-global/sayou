"""Memory adapter abstract base class and data types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    turn_index: int


@dataclass
class SessionData:
    """A loaded session with its messages."""

    session_id: str
    scenario_id: str
    day: int | None
    time_of_day: str | None
    request: str
    messages: list[Message]


@dataclass
class QAPair:
    """A question-answer pair for evaluation."""

    question: str
    expected_answer: str
    qa_type: str  # fact_recall, decision_reasoning, task, etc.
    difficulty: str  # single-hop, detail, multi-hop
    evidence_sessions: list[str]  # Session IDs containing the answer
    required_evidence: list[str] = field(default_factory=list)  # For task QAs


@dataclass
class RetrievalResult:
    """Result of a retrieval query."""

    context: str
    source_sessions: list[str]
    retrieval_time_ms: float
    num_results: int
    context_tokens: int  # approximate token count
    metadata: dict = field(default_factory=dict)  # For tool coverage tracking


@dataclass
class IngestMetrics:
    """Metrics from ingesting a session."""

    time_ms: float
    storage_bytes: int


@dataclass
class ScenarioData:
    """A full loaded scenario."""

    scenario_id: str
    title: str
    domain: str
    category: str
    sessions: list[SessionData]
    qa_pairs: list[QAPair]


@dataclass
class JudgeResult:
    """Result from the LLM judge for a single QA pair."""

    qa_pair: QAPair
    adapter_name: str
    generated_answer: str
    score: int  # 0-3
    key_facts: list[str]
    matched_facts: list[str]
    missing_facts: list[str]
    reasoning: str
    retrieval: RetrievalResult
    task_meta: dict | None = None  # For task QAs: holistic_score, evidence_found, etc.


@dataclass
class AdapterResult:
    """Aggregate results for one adapter on one scenario."""

    adapter_name: str
    scenario_id: str
    judge_results: list[JudgeResult] = field(default_factory=list)
    ingest_metrics: list[IngestMetrics] = field(default_factory=list)
    total_ingest_time_ms: float = 0.0
    total_storage_bytes: int = 0


class MemoryAdapter(ABC):
    """Abstract base class for memory system adapters."""

    name: str = "base"

    @classmethod
    def available(cls) -> bool:
        """Check if this adapter's dependencies are installed."""
        return True

    @abstractmethod
    async def setup(self) -> None:
        """Initialize the adapter (create connections, etc.)."""

    @abstractmethod
    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        """Ingest a single session into the memory system."""

    @abstractmethod
    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        """Retrieve context relevant to a query."""

    @abstractmethod
    async def reset(self, scenario_id: str) -> None:
        """Clear all data for a scenario."""

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up resources."""
