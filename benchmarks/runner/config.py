"""Benchmark configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DATASET_DIR = Path(__file__).parent.parent / "dataset" / "generated"
LOCOMO_DIR = Path(__file__).parent.parent / "locomo" / "data"
RESULTS_DIR = Path(__file__).parent.parent / "results"


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""

    # Benchmark type: "samb" or "locomo"
    benchmark: str = "samb"

    # Adapters to evaluate
    adapters: list[str] = field(default_factory=lambda: ["no-memory", "sayou", "mem0"])

    # Scenario filter (None = all)
    scenarios: list[str] | None = None

    # Retrieval depth
    k: int = 10

    # LLM settings
    answer_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o-mini"
    answer_temperature: float = 0.0
    judge_temperature: float = 0.0

    # Output
    output_formats: list[str] = field(default_factory=lambda: ["json", "table"])
    verbose: bool = False

    # Paths
    dataset_dir: Path = DATASET_DIR
    locomo_dir: Path = LOCOMO_DIR
    results_dir: Path = RESULTS_DIR

    # Stats
    n_bootstrap: int = 1000
    ci_level: float = 0.95
