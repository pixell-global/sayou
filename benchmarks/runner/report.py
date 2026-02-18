"""Report generation — JSON and table output."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.runner.adapter import AdapterResult, JudgeResult
from benchmarks.runner.config import BenchmarkConfig
from benchmarks.runner.stats import (
    bootstrap_ci,
    compute_all_pairwise,
)


def build_report(
    all_results: dict[str, list[AdapterResult]],
    config: BenchmarkConfig,
) -> dict:
    """Build the full benchmark report from adapter results.

    Args:
        all_results: Dict of adapter_name -> list of AdapterResult (one per scenario).
        config: Benchmark configuration.

    Returns:
        Full report dict suitable for JSON serialization.
    """
    report = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "benchmark": config.benchmark,
            "config": {
                "adapters": config.adapters,
                "scenarios": config.scenarios,
                "k": config.k,
                "answer_model": config.answer_model,
                "judge_model": config.judge_model,
                "n_bootstrap": config.n_bootstrap,
            },
        },
        "summary": {},
        "per_adapter": {},
        "significance_tests": [],
    }

    # Collect all scores per adapter (aligned by QA pair order for paired tests)
    adapter_all_scores: dict[str, list[float]] = {}

    for adapter_name, adapter_results in all_results.items():
        # Flatten all judge results across scenarios
        all_judge: list[JudgeResult] = []
        for ar in adapter_results:
            all_judge.extend(ar.judge_results)

        raw_scores = [jr.score for jr in all_judge]
        normalized = [s / 3.0 for s in raw_scores]
        adapter_all_scores[adapter_name] = normalized

        ci = bootstrap_ci(normalized, n_bootstrap=config.n_bootstrap, ci=config.ci_level)

        # Retrieval metrics
        retrieval_recalls = []
        retrieval_precisions = []
        retrieval_latencies = []
        context_tokens_list = []

        for jr in all_judge:
            evidence = set(jr.qa_pair.evidence_sessions)
            retrieved = set(jr.retrieval.source_sessions)
            if evidence:
                retrieval_recalls.append(len(evidence & retrieved) / len(evidence))
            if retrieved:
                retrieval_precisions.append(len(evidence & retrieved) / len(retrieved))
            retrieval_latencies.append(jr.retrieval.retrieval_time_ms)
            context_tokens_list.append(jr.retrieval.context_tokens)

        # Breakdowns
        by_type = _breakdown(all_judge, lambda jr: jr.qa_pair.qa_type, config)
        by_difficulty = _breakdown(all_judge, lambda jr: jr.qa_pair.difficulty, config)

        # Ingestion metrics
        total_ingest_ms = sum(ar.total_ingest_time_ms for ar in adapter_results)
        total_storage = sum(ar.total_storage_bytes for ar in adapter_results)

        adapter_report: dict = {
            "answer_quality": {
                "mean_score": ci.mean,
                "ci_lower": ci.lower,
                "ci_upper": ci.upper,
                "n": ci.n,
                "raw_mean_0_3": sum(raw_scores) / len(raw_scores) if raw_scores else 0,
            },
            "by_qa_type": by_type,
            "by_difficulty": by_difficulty,
            "retrieval": {
                "session_recall": _safe_mean(retrieval_recalls),
                "session_precision": _safe_mean(retrieval_precisions),
            },
            "efficiency": {
                "total_ingest_time_ms": total_ingest_ms,
                "retrieval_latency_p50_ms": _percentile(retrieval_latencies, 50),
                "retrieval_latency_p95_ms": _percentile(retrieval_latencies, 95),
                "mean_context_tokens": _safe_mean(context_tokens_list),
                "total_storage_bytes": total_storage,
            },
        }

        # Task evaluation results (if any task QAs were evaluated)
        task_results = _collect_task_results(adapter_results)
        if task_results:
            adapter_report["task_evaluation"] = task_results

        # Tool coverage (sayou-specific, populated by sayou adapter)
        tool_coverage = _collect_tool_coverage(adapter_results)
        if tool_coverage:
            adapter_report["tool_coverage"] = tool_coverage

        report["per_adapter"][adapter_name] = adapter_report

    # Summary table (adapter -> mean score)
    report["summary"] = {
        name: {
            "mean_score": report["per_adapter"][name]["answer_quality"]["mean_score"],
            "ci": f"[{report['per_adapter'][name]['answer_quality']['ci_lower']:.3f}, "
                  f"{report['per_adapter'][name]['answer_quality']['ci_upper']:.3f}]",
        }
        for name in all_results
    }

    # Significance tests
    if len(adapter_all_scores) >= 2:
        # Verify all score lists have same length
        lengths = [len(v) for v in adapter_all_scores.values()]
        if len(set(lengths)) == 1:
            sig_results = compute_all_pairwise(
                adapter_all_scores, n_bootstrap=config.n_bootstrap
            )
            report["significance_tests"] = [
                {
                    "system_a": sr.system_a,
                    "system_b": sr.system_b,
                    "mean_diff": sr.mean_diff,
                    "p_value": sr.p_value,
                    "significant": sr.significant,
                    "ci": f"[{sr.ci_lower:.4f}, {sr.ci_upper:.4f}]",
                }
                for sr in sig_results
            ]

    return report


def _collect_task_results(adapter_results: list[AdapterResult]) -> dict | None:
    """Collect task evaluation results from adapter results metadata."""
    task_data: list[dict] = []
    for ar in adapter_results:
        for jr in ar.judge_results:
            if jr.qa_pair.qa_type == "task" and hasattr(jr, "task_meta") and jr.task_meta:
                task_data.append({
                    "scenario_id": ar.scenario_id,
                    "question": jr.qa_pair.question,
                    **jr.task_meta,
                })

    if not task_data:
        return None

    holistic_scores = [t["holistic_score"] for t in task_data]
    all_found = sum(len(t.get("evidence_found", [])) for t in task_data)
    all_total = sum(
        len(t.get("evidence_found", [])) + len(t.get("evidence_missing", []))
        for t in task_data
    )
    return {
        "mean_holistic": _safe_mean(holistic_scores),
        "evidence_coverage_pct": all_found / all_total if all_total > 0 else 0.0,
        "evidence_found": all_found,
        "evidence_total": all_total,
        "per_task": task_data,
    }


def _collect_tool_coverage(adapter_results: list[AdapterResult]) -> dict | None:
    """Collect tool coverage stats from sayou adapter metadata."""
    tool_hits: dict[str, int] = defaultdict(int)
    total_queries = 0
    multi_tool_only = 0

    for ar in adapter_results:
        for jr in ar.judge_results:
            meta = getattr(jr.retrieval, "metadata", None)
            if not meta or "tool_hits" not in meta:
                continue
            total_queries += 1
            hits = meta["tool_hits"]
            for tool, count in hits.items():
                if count > 0:
                    tool_hits[tool] += 1
            # Check if any result was found ONLY by 2nd/3rd tool
            if hits.get("search", 0) == 0 and (hits.get("grep", 0) > 0 or hits.get("chunk_search", 0) > 0):
                multi_tool_only += 1

    if total_queries == 0:
        return None

    return {
        "total_queries": total_queries,
        "tool_hit_rate": {tool: count / total_queries for tool, count in tool_hits.items()},
        "multi_tool_bonus_pct": multi_tool_only / total_queries,
    }


def _breakdown(
    results: list[JudgeResult],
    key_fn,
    config: BenchmarkConfig,
) -> dict:
    """Break down scores by a grouping key."""
    groups: dict[str, list[float]] = defaultdict(list)
    for jr in results:
        groups[key_fn(jr)].append(jr.score / 3.0)

    out = {}
    for key, scores in sorted(groups.items()):
        ci = bootstrap_ci(scores, n_bootstrap=config.n_bootstrap, ci=config.ci_level)
        out[key] = {
            "mean_score": ci.mean,
            "ci_lower": ci.lower,
            "ci_upper": ci.upper,
            "n": ci.n,
        }
    return out


def _safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    import numpy as np
    return float(np.percentile(values, p))


# ---------------------------------------------------------------------------
# LOCOMO report builder
# ---------------------------------------------------------------------------


def build_locomo_report(
    all_results: dict[str, list],
    config: BenchmarkConfig,
) -> dict:
    """Build a LOCOMO benchmark report with accuracy %, p95 latency, tokens/query.

    Args:
        all_results: Dict of adapter_name -> list of dicts with keys:
            "correct" (bool), "retrieval_time_ms" (float), "context_tokens" (int),
            "question", "reference", "answer", "reasoning".
        config: Benchmark configuration.
    """
    # Published reference scores for context
    reference_scores = {
        "mem0 (published)": 66.9,
        "Zep (published, LongMemEval)": 71.2,
    }

    report = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "benchmark": "locomo",
            "config": {
                "adapters": config.adapters,
                "scenarios": config.scenarios,
                "k": config.k,
                "answer_model": config.answer_model,
                "judge_model": config.judge_model,
            },
        },
        "reference_scores": reference_scores,
        "results": {},
    }

    for adapter_name, results_list in all_results.items():
        correct_count = sum(1 for r in results_list if r["correct"])
        total = len(results_list)
        accuracy = (correct_count / total * 100) if total > 0 else 0.0

        latencies = [r["retrieval_time_ms"] for r in results_list]
        tokens = [r["context_tokens"] for r in results_list]

        report["results"][adapter_name] = {
            "accuracy_pct": round(accuracy, 1),
            "correct": correct_count,
            "total": total,
            "p95_latency_ms": _percentile(latencies, 95),
            "mean_tokens_per_query": _safe_mean(tokens),
        }

    return report


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def save_json(report: dict, output_path: Path) -> None:
    """Save report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def print_table(report: dict) -> None:
    """Print a formatted summary table to stdout."""
    benchmark = report.get("metadata", {}).get("benchmark", "samb")
    if benchmark == "locomo":
        _print_locomo_table(report)
    else:
        _print_samb_table(report)


def _print_locomo_table(report: dict) -> None:
    """Print LOCOMO results as a formatted table."""
    print("\n" + "=" * 72)
    print("LOCOMO Benchmark Results")
    print("=" * 72)

    print(f"\n{'Adapter':<25} {'Accuracy':<12} {'p95 Latency':<15} {'Tokens/Query':<12}")
    print("-" * 65)

    for name, data in report["results"].items():
        print(f"{name:<25} {data['accuracy_pct']:>5.1f}%       "
              f"{data['p95_latency_ms']:>8.1f}ms    "
              f"{data['mean_tokens_per_query']:>8.0f}")

    # Show published reference scores
    refs = report.get("reference_scores", {})
    if refs:
        print()
        print("Published Reference Scores:")
        for name, score in refs.items():
            print(f"  {name:<40} {score:.1f}%")

    print("\n" + "=" * 72)


def _print_samb_table(report: dict) -> None:
    """Print SAMB results as a formatted table."""
    print("\n" + "=" * 72)
    print("SAMB Benchmark Results")
    print("=" * 72)

    # Summary table
    print(f"\n{'Adapter':<15} {'Mean Score':<12} {'95% CI':<20} {'N':>5}")
    print("-" * 55)
    for name, summary in report["summary"].items():
        adapter_data = report["per_adapter"][name]
        n = adapter_data["answer_quality"]["n"]
        print(f"{name:<15} {summary['mean_score']:.3f}        {summary['ci']:<20} {n:>5}")

    # Per-adapter detail
    for name, data in report["per_adapter"].items():
        print(f"\n--- {name} ---")

        # Retrieval
        ret = data["retrieval"]
        print(f"  Retrieval — Recall: {ret['session_recall']:.3f}, "
              f"Precision: {ret['session_precision']:.3f}")

        # Efficiency
        eff = data["efficiency"]
        print(f"  Efficiency — Ingest: {eff['total_ingest_time_ms']:.0f}ms, "
              f"Retrieval P50: {eff['retrieval_latency_p50_ms']:.1f}ms, "
              f"P95: {eff['retrieval_latency_p95_ms']:.1f}ms")
        print(f"  Context tokens (mean): {eff['mean_context_tokens']:.0f}, "
              f"Storage: {eff['total_storage_bytes']:,} bytes")

        # By difficulty
        if data.get("by_difficulty"):
            print("  By Difficulty:")
            for diff, stats in data["by_difficulty"].items():
                print(f"    {diff:<12} {stats['mean_score']:.3f} "
                      f"[{stats['ci_lower']:.3f}, {stats['ci_upper']:.3f}] "
                      f"(n={stats['n']})")

        # By QA type
        if data.get("by_qa_type"):
            print("  By QA Type:")
            for qt, stats in data["by_qa_type"].items():
                if qt == "task":
                    # Task QAs use 1-5 scale, not 0-3
                    continue
                print(f"    {qt:<25} {stats['mean_score']:.3f} "
                      f"[{stats['ci_lower']:.3f}, {stats['ci_upper']:.3f}] "
                      f"(n={stats['n']})")

        # Task evaluation
        task = data.get("task_evaluation")
        if task:
            print("  Task Evaluation:")
            print(f"    Holistic Score: {task['mean_holistic']:.1f}/5")
            print(f"    Evidence Coverage: {task['evidence_coverage_pct']:.0%} "
                  f"({task['evidence_found']}/{task['evidence_total']} items)")

        # Tool coverage (sayou-specific)
        tc = data.get("tool_coverage")
        if tc:
            print("  Tool Coverage:")
            for tool, rate in tc["tool_hit_rate"].items():
                print(f"    {tool:<20} {rate:.0%}")
            print(f"    Multi-tool bonus: {tc['multi_tool_bonus_pct']:.0%}")

    # Task evaluation comparison (if multiple adapters have task results)
    adapters_with_tasks = [
        (name, data["task_evaluation"])
        for name, data in report["per_adapter"].items()
        if data.get("task_evaluation")
    ]
    if len(adapters_with_tasks) >= 2:
        print(f"\n{'Task Evaluation Comparison':}")
        print(f"{'Adapter':<20} {'Holistic (1-5)':<18} {'Evidence Coverage':<20}")
        print("-" * 58)
        for name, task in adapters_with_tasks:
            coverage_str = f"{task['evidence_coverage_pct']:.0%} ({task['evidence_found']}/{task['evidence_total']})"
            print(f"{name:<20} {task['mean_holistic']:<18.1f} {coverage_str:<20}")

    # Significance tests
    if report.get("significance_tests"):
        print(f"\n{'Significance Tests (Bonferroni-corrected)':}")
        print(f"{'Pair':<30} {'Diff':>7} {'p-value':>9} {'Sig?':>5}")
        print("-" * 55)
        for st in report["significance_tests"]:
            sig = "*" if st["significant"] else ""
            print(f"{st['system_a']} vs {st['system_b']:<15} "
                  f"{st['mean_diff']:>+.4f} {st['p_value']:>9.4f} {sig:>5}")

    print("\n" + "=" * 72)
