"""
Compute quality metrics for the generated benchmark dataset.

Measures lexical diversity, intra-corpus similarity, turn length distribution,
opening phrase diversity, and persona adherence.

Usage:
    python -m benchmarks.quality_metrics
    python -m benchmarks.quality_metrics --json
    python -m benchmarks.quality_metrics --scenario 01
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import yaml

SCENARIOS_DIR = Path(__file__).parent / "dataset" / "scenarios"
GENERATED_DIR = Path(__file__).parent / "dataset" / "generated"


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    import re
    return re.findall(r'\b\w+\b', text.lower())


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def distinct_n(texts: list[str], n: int) -> float:
    """Distinct-N: ratio of unique n-grams to total n-grams.

    Higher = more diverse vocabulary. Target: Distinct-1 > 0.4, Distinct-2 > 0.6.
    """
    all_ngrams = []
    for text in texts:
        tokens = tokenize(text)
        all_ngrams.extend(ngrams(tokens, n))
    if not all_ngrams:
        return 0.0
    return len(set(all_ngrams)) / len(all_ngrams)


def self_bleu(texts: list[str], max_samples: int = 200) -> float:
    """Self-BLEU: average BLEU score of each text against all others.

    Lower = more diverse. Target: < 0.3.
    Uses a simplified BLEU-4 approximation.
    """
    if len(texts) < 2:
        return 0.0

    # Sample if too many texts
    if len(texts) > max_samples:
        import random
        random.seed(42)
        texts = random.sample(texts, max_samples)

    tokenized = [tokenize(t) for t in texts]
    scores = []

    for i, hypothesis in enumerate(tokenized):
        if len(hypothesis) < 4:
            continue
        references = [tokenized[j] for j in range(len(tokenized)) if j != i]
        score = _bleu_against_refs(hypothesis, references)
        scores.append(score)

    return sum(scores) / len(scores) if scores else 0.0


def _bleu_against_refs(hypothesis: list[str], references: list[list[str]]) -> float:
    """Simplified corpus-level BLEU-4 score."""
    # Combine all reference n-grams
    precisions = []
    for n in range(1, 5):
        hyp_ngrams = ngrams(hypothesis, n)
        if not hyp_ngrams:
            precisions.append(0.0)
            continue

        ref_counts: Counter = Counter()
        for ref in references:
            ref_ngrams_counter = Counter(ngrams(ref, n))
            for ng, count in ref_ngrams_counter.items():
                ref_counts[ng] = max(ref_counts[ng], count)

        clipped = sum(min(count, ref_counts.get(ng, 0))
                       for ng, count in Counter(hyp_ngrams).items())
        precisions.append(clipped / len(hyp_ngrams))

    # Geometric mean of precisions
    if any(p == 0 for p in precisions):
        return 0.0

    log_avg = sum(math.log(p) for p in precisions) / len(precisions)

    # Brevity penalty
    ref_len = min(len(r) for r in references) if references else 0
    if len(hypothesis) >= ref_len or ref_len == 0:
        bp = 1.0
    else:
        bp = math.exp(1 - ref_len / len(hypothesis))

    return bp * math.exp(log_avg)


def opening_phrase_diversity(messages_by_session: list[list[dict]]) -> float:
    """Percentage of unique first-5-words across user opening messages.

    Higher = more diverse openings. Target: > 80%.
    """
    openings = []
    for session_msgs in messages_by_session:
        user_msgs = [m for m in session_msgs if m.get("role") == "user"]
        if user_msgs:
            words = tokenize(user_msgs[0].get("content", ""))[:5]
            openings.append(" ".join(words))

    if not openings:
        return 1.0

    unique = len(set(openings))
    return unique / len(openings)


def turn_length_stats(messages: list[dict]) -> dict:
    """Compute turn length statistics for user vs assistant messages."""
    user_lengths = []
    assistant_lengths = []

    for msg in messages:
        content = msg.get("content", "")
        word_count = len(tokenize(content))
        if msg.get("role") == "user":
            user_lengths.append(word_count)
        elif msg.get("role") == "assistant":
            assistant_lengths.append(word_count)

    def stats(lengths: list[int]) -> dict:
        if not lengths:
            return {"mean": 0, "median": 0, "min": 0, "max": 0, "count": 0}
        lengths.sort()
        n = len(lengths)
        return {
            "mean": round(sum(lengths) / n, 1),
            "median": lengths[n // 2],
            "min": lengths[0],
            "max": lengths[-1],
            "count": n,
        }

    return {
        "user": stats(user_lengths),
        "assistant": stats(assistant_lengths),
    }


def forbidden_phrase_count(messages: list[dict]) -> dict:
    """Count occurrences of forbidden/robotic phrases."""
    from benchmarks.generate import FORBIDDEN_PHRASES, FORBIDDEN_OPENINGS

    counts: dict[str, int] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "").lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in content:
                counts[phrase] = counts.get(phrase, 0) + 1

    # Check user openings
    user_msgs = [m for m in messages if m.get("role") == "user"]
    opening_violations = 0
    if user_msgs:
        first = user_msgs[0].get("content", "").strip().lower()
        for opening in FORBIDDEN_OPENINGS:
            if first.startswith(opening.lower()):
                opening_violations += 1

    return {
        "forbidden_phrases": counts,
        "total_forbidden": sum(counts.values()),
        "opening_violations": opening_violations,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_metrics(generated_dir: Path, scenario_filter: str | None = None) -> dict:
    """Compute all quality metrics on the generated dataset."""
    generated_files = sorted(generated_dir.glob("*.json"))
    if scenario_filter:
        generated_files = [f for f in generated_files if f.name.startswith(f"{scenario_filter}-")]

    all_user_texts = []
    all_assistant_texts = []
    all_messages = []
    messages_by_session = []
    scenario_details = []
    total_sessions = 0
    total_forbidden = 0
    total_opening_violations = 0

    for gf in generated_files:
        with open(gf) as f:
            dataset = json.load(f)

        scenario_user_texts = []
        scenario_assistant_texts = []

        for session in dataset.get("sessions", []):
            total_sessions += 1
            session_msgs = session.get("messages", [])
            messages_by_session.append(session_msgs)
            all_messages.extend(session_msgs)

            for msg in session_msgs:
                content = msg.get("content", "")
                if msg.get("role") == "user":
                    all_user_texts.append(content)
                    scenario_user_texts.append(content)
                elif msg.get("role") == "assistant":
                    all_assistant_texts.append(content)
                    scenario_assistant_texts.append(content)

            fp = forbidden_phrase_count(session_msgs)
            total_forbidden += fp["total_forbidden"]
            total_opening_violations += fp["opening_violations"]

        scenario_details.append({
            "scenario_id": dataset.get("scenario_id"),
            "title": dataset.get("title"),
            "sessions": len(dataset.get("sessions", [])),
            "user_distinct_1": round(distinct_n(scenario_user_texts, 1), 4),
            "assistant_distinct_1": round(distinct_n(scenario_assistant_texts, 1), 4),
        })

    # Compute corpus-level metrics
    d1_user = distinct_n(all_user_texts, 1)
    d2_user = distinct_n(all_user_texts, 2)
    d1_assistant = distinct_n(all_assistant_texts, 1)
    d2_assistant = distinct_n(all_assistant_texts, 2)

    sb_user = self_bleu(all_user_texts)
    sb_assistant = self_bleu(all_assistant_texts)

    opening_div = opening_phrase_diversity(messages_by_session)
    turn_stats = turn_length_stats(all_messages)

    return {
        "corpus_stats": {
            "scenarios": len(generated_files),
            "sessions": total_sessions,
            "user_messages": len(all_user_texts),
            "assistant_messages": len(all_assistant_texts),
        },
        "lexical_diversity": {
            "user_distinct_1": round(d1_user, 4),
            "user_distinct_2": round(d2_user, 4),
            "assistant_distinct_1": round(d1_assistant, 4),
            "assistant_distinct_2": round(d2_assistant, 4),
            "targets": "Distinct-1 > 0.4, Distinct-2 > 0.6",
        },
        "self_bleu": {
            "user": round(sb_user, 4),
            "assistant": round(sb_assistant, 4),
            "target": "< 0.3 (lower = more diverse)",
        },
        "opening_diversity": {
            "score": round(opening_div, 4),
            "target": "> 0.8 (80% unique openings)",
        },
        "turn_lengths": turn_stats,
        "quality_violations": {
            "total_forbidden_phrases": total_forbidden,
            "total_opening_violations": total_opening_violations,
            "target": "0",
        },
        "per_scenario": scenario_details,
    }


def main():
    parser = argparse.ArgumentParser(description="Compute quality metrics for benchmark dataset")
    parser.add_argument("--scenario", default=None, help="Compute for one scenario (e.g., '01')")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    metrics = compute_metrics(GENERATED_DIR, scenario_filter=args.scenario)

    if args.json:
        print(json.dumps(metrics, indent=2))
        return

    # Human-readable output
    print(f"\n{'='*70}")
    print("QUALITY METRICS REPORT")
    print(f"{'='*70}\n")

    cs = metrics["corpus_stats"]
    print(f"  Corpus: {cs['scenarios']} scenarios, {cs['sessions']} sessions, "
          f"{cs['user_messages']} user msgs, {cs['assistant_messages']} assistant msgs\n")

    ld = metrics["lexical_diversity"]
    print("  Lexical Diversity (Distinct-N):")
    d1_pass = "PASS" if ld["user_distinct_1"] > 0.4 else "FAIL"
    d2_pass = "PASS" if ld["user_distinct_2"] > 0.6 else "FAIL"
    print(f"    User    Distinct-1: {ld['user_distinct_1']:.4f}  [{d1_pass}]  (target > 0.4)")
    print(f"    User    Distinct-2: {ld['user_distinct_2']:.4f}  [{d2_pass}]  (target > 0.6)")
    d1a_pass = "PASS" if ld["assistant_distinct_1"] > 0.4 else "FAIL"
    d2a_pass = "PASS" if ld["assistant_distinct_2"] > 0.6 else "FAIL"
    print(f"    Assist  Distinct-1: {ld['assistant_distinct_1']:.4f}  [{d1a_pass}]  (target > 0.4)")
    print(f"    Assist  Distinct-2: {ld['assistant_distinct_2']:.4f}  [{d2a_pass}]  (target > 0.6)")

    sb = metrics["self_bleu"]
    sb_u_pass = "PASS" if sb["user"] < 0.3 else "FAIL"
    sb_a_pass = "PASS" if sb["assistant"] < 0.3 else "FAIL"
    print(f"\n  Self-BLEU (lower = more diverse):")
    print(f"    User:      {sb['user']:.4f}  [{sb_u_pass}]  (target < 0.3)")
    print(f"    Assistant: {sb['assistant']:.4f}  [{sb_a_pass}]  (target < 0.3)")

    od = metrics["opening_diversity"]
    od_pass = "PASS" if od["score"] > 0.8 else "FAIL"
    print(f"\n  Opening Diversity: {od['score']:.1%}  [{od_pass}]  (target > 80%)")

    tl = metrics["turn_lengths"]
    print(f"\n  Turn Lengths (words):")
    print(f"    User:      mean={tl['user']['mean']}, median={tl['user']['median']}, "
          f"range=[{tl['user']['min']}, {tl['user']['max']}]")
    print(f"    Assistant: mean={tl['assistant']['mean']}, median={tl['assistant']['median']}, "
          f"range=[{tl['assistant']['min']}, {tl['assistant']['max']}]")

    qv = metrics["quality_violations"]
    qv_pass = "PASS" if qv["total_forbidden_phrases"] == 0 and qv["total_opening_violations"] == 0 else "FAIL"
    print(f"\n  Quality Violations:  [{qv_pass}]")
    print(f"    Forbidden phrases: {qv['total_forbidden_phrases']}")
    print(f"    Opening violations: {qv['total_opening_violations']}")

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
