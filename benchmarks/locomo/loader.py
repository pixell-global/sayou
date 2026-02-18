"""Load LOCOMO dataset into SAMB-compatible dataclasses.

LOCOMO (snap-research/locomo) provides 10 long conversations with ~2000 QA pairs.
This loader converts them to the same SessionData/QAPair format used by SAMB,
so the existing runner pipeline can evaluate both benchmarks.

Expected dataset layout (after cloning snap-research/locomo):
  locomo/
    data/
      1.json
      2.json
      ...
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.runner.adapter import Message, QAPair, ScenarioData, SessionData


def load_locomo_conversation(path: Path) -> ScenarioData:
    """Load a single LOCOMO conversation JSON file."""
    with open(path) as f:
        data = json.load(f)

    conv_id = path.stem  # e.g., "1"
    scenario_id = f"locomo-{conv_id}"

    # LOCOMO stores the conversation as a flat list of utterances.
    # We treat the entire conversation as one session.
    messages: list[Message] = []
    conversation = data.get("conversation", [])
    for i, turn in enumerate(conversation):
        speaker = turn.get("speaker", "").lower()
        text = turn.get("text", turn.get("utterance", ""))
        # Map LOCOMO speakers to user/assistant roles.
        # In LOCOMO, speakers are participant names — we alternate roles
        # based on the speaker identity.
        role = "user" if i % 2 == 0 else "assistant"
        if speaker:
            # Use first speaker as "user", second as "assistant"
            if not hasattr(load_locomo_conversation, "_speaker_map"):
                load_locomo_conversation._speaker_map = {}
            smap = load_locomo_conversation._speaker_map
            if scenario_id not in smap:
                smap[scenario_id] = {}
            if speaker not in smap[scenario_id]:
                smap[scenario_id][speaker] = "user" if len(smap[scenario_id]) == 0 else "assistant"
            role = smap[scenario_id][speaker]
        messages.append(Message(role=role, content=text, turn_index=i))

    session = SessionData(
        session_id="s1",
        scenario_id=scenario_id,
        day=1,
        time_of_day=None,
        request=messages[0].content if messages else "",
        messages=messages,
    )

    # Load QA pairs from all question types
    qa_pairs: list[QAPair] = []
    for qa_type in ("single-hop", "multi-hop", "temporal", "open-domain", "adversarial"):
        questions = data.get(qa_type, [])
        for qa in questions:
            question = qa.get("question", "")
            answer = qa.get("answer", "")
            if not question or not answer:
                continue
            # Evidence sessions: LOCOMO provides "evidence" as turn indices
            evidence = qa.get("evidence", [])
            evidence_sessions = ["s1"] if evidence else []
            qa_pairs.append(QAPair(
                question=question,
                expected_answer=answer,
                qa_type=qa_type,
                difficulty=qa_type,
                evidence_sessions=evidence_sessions,
            ))

    return ScenarioData(
        scenario_id=scenario_id,
        title=f"LOCOMO Conversation {conv_id}",
        domain="conversation",
        category="recall",
        sessions=[session],
        qa_pairs=qa_pairs,
    )


def load_all_locomo(
    dataset_dir: Path,
    scenario_filter: list[str] | None = None,
) -> list[ScenarioData]:
    """Load all LOCOMO conversations from the dataset directory.

    Args:
        dataset_dir: Path to the locomo/data/ directory containing JSON files.
        scenario_filter: Optional list of conversation IDs (e.g., ["1", "2"]).
    """
    # Reset speaker map between full loads
    if hasattr(load_locomo_conversation, "_speaker_map"):
        load_locomo_conversation._speaker_map = {}

    files = sorted(dataset_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No LOCOMO files found in {dataset_dir}")

    if scenario_filter:
        filtered = []
        for f in files:
            if f.stem in scenario_filter:
                filtered.append(f)
        files = filtered
        if not files:
            raise FileNotFoundError(
                f"No LOCOMO conversations matching {scenario_filter} in {dataset_dir}"
            )

    return [load_locomo_conversation(f) for f in files]
