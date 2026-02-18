"""Load SAMB dataset JSON files into typed dataclasses."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.runner.adapter import Message, QAPair, ScenarioData, SessionData


def load_scenario(path: Path) -> ScenarioData:
    """Load a single scenario JSON file."""
    with open(path) as f:
        data = json.load(f)

    sessions = []
    for s in data["sessions"]:
        messages = []
        for i, m in enumerate(s["messages"]):
            messages.append(Message(
                role=m["role"],
                content=m["content"],
                turn_index=i,
            ))
        sessions.append(SessionData(
            session_id=s["id"],
            scenario_id=data["scenario_id"],
            day=s.get("day"),
            time_of_day=s.get("time"),
            request=s.get("user_request", ""),
            messages=messages,
        ))

    qa_pairs = []
    for qa in data.get("qa_pairs", []):
        qa_pairs.append(QAPair(
            question=qa["question"],
            expected_answer=qa["answer"],
            qa_type=qa.get("type", "unknown"),
            difficulty=qa.get("difficulty", "unknown"),
            evidence_sessions=qa.get("evidence_sessions", []),
            required_evidence=qa.get("required_evidence", []),
        ))

    return ScenarioData(
        scenario_id=data["scenario_id"],
        title=data["title"],
        domain=data.get("domain", ""),
        category=data.get("category", ""),
        sessions=sessions,
        qa_pairs=qa_pairs,
    )


def load_all_scenarios(dataset_dir: Path, scenario_filter: list[str] | None = None) -> list[ScenarioData]:
    """Load all scenarios from the dataset directory.

    Args:
        dataset_dir: Path to the generated dataset directory.
        scenario_filter: Optional list of scenario numbers (e.g., ["01", "02"]).
    """
    files = sorted(dataset_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No scenario files found in {dataset_dir}")

    if scenario_filter:
        filtered = []
        for f in files:
            for sf in scenario_filter:
                if f.name.startswith(f"{sf}-"):
                    filtered.append(f)
                    break
        files = filtered
        if not files:
            raise FileNotFoundError(
                f"No scenarios matching {scenario_filter} in {dataset_dir}"
            )

    return [load_scenario(f) for f in files]
