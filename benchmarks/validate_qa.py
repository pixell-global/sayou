"""
Validate that QA pairs in the benchmark dataset are answerable from evidence sessions.

For each QA pair, checks whether the expected answer's key facts can be found in the
messages of the referenced evidence sessions. Outputs a validation report.

Usage:
    python -m benchmarks.validate_qa
    python -m benchmarks.validate_qa --scenario 01
    python -m benchmarks.validate_qa --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent / "dataset" / "scenarios"
GENERATED_DIR = Path(__file__).parent / "dataset" / "generated"


def load_generated(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def extract_session_text(dataset: dict, session_ids: list[str]) -> str:
    """Extract all message content from specified sessions."""
    texts = []
    for session in dataset.get("sessions", []):
        if session["id"] in session_ids:
            for msg in session.get("messages", []):
                texts.append(msg.get("content", ""))
    return " ".join(texts)


def extract_key_terms(answer: str) -> list[str]:
    """Extract significant terms and numbers from an answer for validation."""
    terms = []

    # Extract numbers (including decimals, percentages, durations)
    numbers = re.findall(r'\d+(?:\.\d+)?%?', answer)
    terms.extend(numbers)

    # Extract quoted strings
    quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", answer)
    for q in quoted:
        terms.append(q[0] or q[1])

    # Extract technical terms (capitalized words, hyphenated terms)
    technical = re.findall(r'\b[A-Z][a-zA-Z]+(?:-[a-zA-Z]+)*\b', answer)
    terms.extend(technical)

    # Extract key phrases (3+ word sequences with meaningful words)
    words = answer.lower().split()
    stopwords = {
        "the", "a", "an", "is", "was", "were", "are", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare",
        "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
        "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "and", "but", "or", "nor", "not", "so", "yet", "both",
        "each", "every", "all", "any", "few", "more", "most", "other",
        "some", "such", "no", "only", "own", "same", "than", "too", "very",
        "just", "because", "about", "it", "its", "this", "that", "these",
        "those", "which", "who", "whom", "what", "when", "where", "why",
        "how", "if", "while", "also",
    }
    meaningful_words = [w for w in words if w not in stopwords and len(w) > 2]
    terms.extend(meaningful_words[:10])  # Top 10 meaningful words

    return terms


def validate_qa_pair(
    qa: dict,
    dataset: dict,
    verbose: bool = False,
) -> dict:
    """Validate a single QA pair against evidence sessions.

    Returns a result dict with validation details.
    """
    question = qa["question"]
    expected_answer = qa["answer"]
    evidence_ids = qa.get("evidence_sessions", [])

    # Get text from evidence sessions
    evidence_text = extract_session_text(dataset, evidence_ids).lower()

    if not evidence_text.strip():
        return {
            "question": question,
            "expected_answer": expected_answer,
            "evidence_sessions": evidence_ids,
            "valid": False,
            "reason": "No content found in evidence sessions",
            "match_score": 0.0,
            "matched_terms": [],
            "missing_terms": [],
        }

    # Extract key terms from the answer
    key_terms = extract_key_terms(expected_answer)
    if not key_terms:
        return {
            "question": question,
            "expected_answer": expected_answer,
            "evidence_sessions": evidence_ids,
            "valid": True,
            "reason": "No key terms to validate (simple answer)",
            "match_score": 1.0,
            "matched_terms": [],
            "missing_terms": [],
        }

    # Check which terms appear in evidence
    matched = []
    missing = []
    for term in key_terms:
        if term.lower() in evidence_text:
            matched.append(term)
        else:
            missing.append(term)

    match_score = len(matched) / len(key_terms) if key_terms else 1.0

    # A QA pair is valid if at least 40% of key terms are found
    # (threshold is lenient because LLM may rephrase details)
    is_valid = match_score >= 0.4

    reason = ""
    if is_valid:
        reason = f"Found {len(matched)}/{len(key_terms)} key terms in evidence"
    else:
        reason = f"Only {len(matched)}/{len(key_terms)} key terms found — answer may not match generated content"

    return {
        "question": question,
        "expected_answer": expected_answer,
        "evidence_sessions": evidence_ids,
        "valid": is_valid,
        "reason": reason,
        "match_score": round(match_score, 3),
        "matched_terms": matched[:5],  # Truncate for readability
        "missing_terms": missing[:5],
    }


def validate_scenario(generated_path: Path, verbose: bool = False) -> dict:
    """Validate all QA pairs for one scenario."""
    dataset = load_generated(generated_path)

    qa_pairs = dataset.get("qa_pairs", [])
    if not qa_pairs:
        return {
            "scenario_id": dataset.get("scenario_id", "unknown"),
            "title": dataset.get("title", "unknown"),
            "total_qa": 0,
            "valid": 0,
            "invalid": 0,
            "pass_rate": 1.0,
            "results": [],
        }

    results = []
    for qa in qa_pairs:
        result = validate_qa_pair(qa, dataset, verbose=verbose)
        results.append(result)

    valid_count = sum(1 for r in results if r["valid"])
    invalid_count = len(results) - valid_count

    return {
        "scenario_id": dataset.get("scenario_id", "unknown"),
        "title": dataset.get("title", "unknown"),
        "total_qa": len(results),
        "valid": valid_count,
        "invalid": invalid_count,
        "pass_rate": round(valid_count / len(results), 3) if results else 1.0,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate QA pairs against generated conversations")
    parser.add_argument("--scenario", default=None, help="Validate only this scenario (e.g., '01')")
    parser.add_argument("--verbose", action="store_true", help="Show details for each QA pair")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    generated_files = sorted(GENERATED_DIR.glob("*.json"))
    if not generated_files:
        print(f"No generated files found in {GENERATED_DIR}")
        sys.exit(1)

    if args.scenario:
        generated_files = [f for f in generated_files if f.name.startswith(f"{args.scenario}-")]
        if not generated_files:
            print(f"No generated file matching '{args.scenario}'")
            sys.exit(1)

    all_results = []
    total_qa = 0
    total_valid = 0

    for gf in generated_files:
        report = validate_scenario(gf, verbose=args.verbose)
        all_results.append(report)
        total_qa += report["total_qa"]
        total_valid += report["valid"]

    if args.json:
        print(json.dumps({
            "total_qa_pairs": total_qa,
            "total_valid": total_valid,
            "total_invalid": total_qa - total_valid,
            "overall_pass_rate": round(total_valid / total_qa, 3) if total_qa else 1.0,
            "scenarios": all_results,
        }, indent=2))
        return

    # Human-readable output
    print(f"\n{'='*70}")
    print("QA VALIDATION REPORT")
    print(f"{'='*70}\n")

    for report in all_results:
        status = "PASS" if report["pass_rate"] >= 0.95 else "WARN" if report["pass_rate"] >= 0.8 else "FAIL"
        print(f"  [{status}] {report['scenario_id']}: {report['title']}")
        print(f"       {report['valid']}/{report['total_qa']} QA pairs validated ({report['pass_rate']:.0%})")

        if args.verbose:
            for r in report["results"]:
                marker = "OK" if r["valid"] else "XX"
                print(f"         [{marker}] {r['question'][:70]}...")
                if not r["valid"]:
                    print(f"              Score: {r['match_score']:.0%}, Missing: {r['missing_terms'][:3]}")
            print()

    print(f"\n{'='*70}")
    overall_rate = total_valid / total_qa if total_qa else 1.0
    print(f"  OVERALL: {total_valid}/{total_qa} QA pairs validated ({overall_rate:.1%})")
    if overall_rate >= 0.95:
        print("  Status: PASS")
    elif overall_rate >= 0.8:
        print("  Status: WARN — some QA pairs may need manual review")
    else:
        print("  Status: FAIL — significant mismatch between QA pairs and generated content")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
