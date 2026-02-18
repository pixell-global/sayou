"""SAMB/LOCOMO Benchmark Runner CLI.

Usage:
    # SAMB (default) — all adapters, all scenarios
    python -m benchmarks.runner.cli

    # LOCOMO — industry comparison
    python -m benchmarks.runner.cli --benchmark locomo --adapter sayou mem0

    # Specific adapters and scenarios
    python -m benchmarks.runner.cli --adapter sayou mem0 --scenario 01 03 08

    # Retrieval depth
    python -m benchmarks.runner.cli --k 5

    # Output formats
    python -m benchmarks.runner.cli --output json table
    python -m benchmarks.runner.cli --verbose

    # Model overrides
    python -m benchmarks.runner.cli --judge-model gpt-4o
    python -m benchmarks.runner.cli --answer-model gpt-4o
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime

from benchmarks.runner.adapter import AdapterResult, JudgeResult
from benchmarks.runner.adapters import get_adapter, list_adapters
from benchmarks.runner.config import BenchmarkConfig
from benchmarks.runner.judge import (
    LLMClient,
    generate_answer,
    judge_answer,
    judge_answer_binary,
    judge_evidence_coverage,
    judge_task_context,
    TaskJudgeResult,
)
from benchmarks.runner.loader import load_all_scenarios
from benchmarks.runner.report import (
    build_locomo_report,
    build_report,
    print_table,
    save_json,
)


async def run_benchmark(config: BenchmarkConfig) -> dict:
    """Execute the full benchmark pipeline."""
    if config.benchmark == "locomo":
        return await _run_locomo(config)
    return await _run_samb(config)


async def _run_samb(config: BenchmarkConfig) -> dict:
    """Execute the SAMB benchmark pipeline."""
    print("SAMB Benchmark Runner")
    print(f"  Adapters: {', '.join(config.adapters)}")
    print(f"  Answer model: {config.answer_model}")
    print(f"  Judge model: {config.judge_model}")
    print(f"  k = {config.k}")

    # Load dataset
    scenarios = load_all_scenarios(config.dataset_dir, config.scenarios)
    total_qa = sum(len(s.qa_pairs) for s in scenarios)
    print(f"  Scenarios: {len(scenarios)}, QA pairs: {total_qa}")

    # Initialize LLM clients
    answer_client = LLMClient(model=config.answer_model, temperature=config.answer_temperature)
    judge_client = LLMClient(model=config.judge_model, temperature=config.judge_temperature)

    # Run each adapter
    all_results: dict[str, list[AdapterResult]] = {}

    for adapter_name in config.adapters:
        print(f"\n{'='*60}")
        print(f"Adapter: {adapter_name}")
        print(f"{'='*60}")

        try:
            adapter = get_adapter(adapter_name)
        except (ValueError, RuntimeError) as e:
            print(f"  SKIP: {e}")
            continue

        await adapter.setup()
        adapter_scenario_results: list[AdapterResult] = []

        try:
            for scenario in scenarios:
                print(f"\n  Scenario: {scenario.title} ({scenario.scenario_id})")
                result = AdapterResult(
                    adapter_name=adapter_name,
                    scenario_id=scenario.scenario_id,
                )

                # Ingest all sessions
                for session in scenario.sessions:
                    metrics = await adapter.ingest_session(scenario.scenario_id, session)
                    result.ingest_metrics.append(metrics)
                    result.total_ingest_time_ms += metrics.time_ms
                    result.total_storage_bytes += metrics.storage_bytes

                print(f"    Ingested {len(scenario.sessions)} sessions "
                      f"({result.total_ingest_time_ms:.0f}ms)")

                # Evaluate each QA pair
                for i, qa in enumerate(scenario.qa_pairs):
                    # Build query — oracle needs evidence session IDs
                    if adapter_name == "oracle":
                        evidence_str = ",".join(qa.evidence_sessions)
                        query = f"EVIDENCE:{evidence_str}|QUERY:{qa.question}"
                    else:
                        query = qa.question

                    # Retrieve
                    retrieval = await adapter.retrieve(
                        scenario.scenario_id, query, k=config.k
                    )

                    if qa.qa_type == "task":
                        # Task QA: holistic 1-5 judge + evidence coverage
                        judge_result = await _evaluate_task_qa(
                            judge_client, qa, retrieval, adapter_name,
                        )
                    else:
                        # Standard QA: generate answer + 0-3 judge
                        answer = await generate_answer(
                            answer_client, qa.question, retrieval.context
                        )
                        judge_score = await judge_answer(
                            judge_client, qa.question, qa.expected_answer, answer
                        )
                        judge_result = JudgeResult(
                            qa_pair=qa,
                            adapter_name=adapter_name,
                            generated_answer=answer,
                            score=judge_score.score,
                            key_facts=judge_score.key_facts,
                            matched_facts=judge_score.matched,
                            missing_facts=judge_score.missing,
                            reasoning=judge_score.reasoning,
                            retrieval=retrieval,
                        )

                    result.judge_results.append(judge_result)

                    # Progress indicator
                    if config.verbose:
                        if qa.qa_type == "task":
                            meta = getattr(judge_result, "task_meta", {}) or {}
                            status = (
                                f"    [{i+1}/{len(scenario.qa_pairs)}] "
                                f"task={meta.get('holistic_score', '?')}/5 "
                                f"evidence={meta.get('coverage_pct', 0):.0%} "
                                f"Q: {qa.question[:50]}..."
                            )
                        else:
                            status = (
                                f"    [{i+1}/{len(scenario.qa_pairs)}] "
                                f"score={judge_result.score}/3 "
                                f"sessions={retrieval.source_sessions} "
                                f"Q: {qa.question[:60]}..."
                            )
                        print(status)
                    else:
                        print(".", end="", flush=True)

                if not config.verbose:
                    scores = [jr.score for jr in result.judge_results]
                    mean = sum(scores) / len(scores) if scores else 0
                    print(f" mean={mean:.2f}/3 ({len(scores)} QAs)")

                # Reset adapter state for next scenario
                await adapter.reset(scenario.scenario_id)

                adapter_scenario_results.append(result)

        finally:
            await adapter.teardown()

        all_results[adapter_name] = adapter_scenario_results

    # Build and return report
    report = build_report(all_results, config)
    return report


async def _evaluate_task_qa(judge_client, qa, retrieval, adapter_name):
    """Evaluate a task-type QA pair with holistic score + evidence coverage."""
    # Holistic score (1-5)
    holistic_score, holistic_reasoning = await judge_task_context(
        judge_client, qa.question, retrieval.context,
    )

    # Evidence coverage
    required_evidence = getattr(qa, "required_evidence", []) or []
    if required_evidence:
        found, missing, coverage = await judge_evidence_coverage(
            judge_client, required_evidence, retrieval.context,
        )
    else:
        found, missing, coverage = [], [], 0.0

    # Map holistic score to 0-3 scale for compatibility with existing report
    # 5->3, 4->2.4, 3->1.8, 2->1.2, 1->0.6
    mapped_score = round((holistic_score / 5.0) * 3)

    judge_result = JudgeResult(
        qa_pair=qa,
        adapter_name=adapter_name,
        generated_answer=f"[task context evaluation — holistic: {holistic_score}/5]",
        score=mapped_score,
        key_facts=required_evidence,
        matched_facts=found,
        missing_facts=missing,
        reasoning=holistic_reasoning,
        retrieval=retrieval,
    )
    # Attach task-specific metadata
    judge_result.task_meta = {
        "holistic_score": holistic_score,
        "holistic_reasoning": holistic_reasoning,
        "evidence_found": found,
        "evidence_missing": missing,
        "coverage_pct": coverage,
    }
    return judge_result


async def _run_locomo(config: BenchmarkConfig) -> dict:
    """Execute the LOCOMO benchmark pipeline."""
    from benchmarks.locomo.loader import load_all_locomo

    print("LOCOMO Benchmark Runner")
    print(f"  Adapters: {', '.join(config.adapters)}")
    print(f"  Answer model: {config.answer_model}")
    print(f"  Judge model: {config.judge_model}")
    print(f"  k = {config.k}")

    # Load LOCOMO dataset
    scenarios = load_all_locomo(config.locomo_dir, config.scenarios)
    total_qa = sum(len(s.qa_pairs) for s in scenarios)
    print(f"  Conversations: {len(scenarios)}, QA pairs: {total_qa}")

    # Initialize LLM clients
    answer_client = LLMClient(model=config.answer_model, temperature=config.answer_temperature)
    judge_client = LLMClient(model=config.judge_model, temperature=config.judge_temperature)

    all_results: dict[str, list[dict]] = {}

    for adapter_name in config.adapters:
        print(f"\n{'='*60}")
        print(f"Adapter: {adapter_name}")
        print(f"{'='*60}")

        try:
            adapter = get_adapter(adapter_name)
        except (ValueError, RuntimeError) as e:
            print(f"  SKIP: {e}")
            continue

        await adapter.setup()
        adapter_results: list[dict] = []

        try:
            for scenario in scenarios:
                print(f"\n  {scenario.title} ({len(scenario.qa_pairs)} QAs)")

                # Ingest
                for session in scenario.sessions:
                    await adapter.ingest_session(scenario.scenario_id, session)

                # Evaluate
                correct_count = 0
                for i, qa in enumerate(scenario.qa_pairs):
                    if adapter_name == "oracle":
                        evidence_str = ",".join(qa.evidence_sessions)
                        query = f"EVIDENCE:{evidence_str}|QUERY:{qa.question}"
                    else:
                        query = qa.question

                    retrieval = await adapter.retrieve(
                        scenario.scenario_id, query, k=config.k
                    )
                    answer = await generate_answer(
                        answer_client, qa.question, retrieval.context
                    )
                    binary_result = await judge_answer_binary(
                        judge_client, qa.question, qa.expected_answer, answer
                    )

                    adapter_results.append({
                        "correct": binary_result.correct,
                        "retrieval_time_ms": retrieval.retrieval_time_ms,
                        "context_tokens": retrieval.context_tokens,
                        "question": qa.question,
                        "reference": qa.expected_answer,
                        "answer": answer,
                        "reasoning": binary_result.reasoning,
                    })

                    if binary_result.correct:
                        correct_count += 1

                    if config.verbose:
                        verdict = "CORRECT" if binary_result.correct else "WRONG"
                        print(f"    [{i+1}/{len(scenario.qa_pairs)}] {verdict} "
                              f"Q: {qa.question[:50]}...")
                    else:
                        print("." if binary_result.correct else "x", end="", flush=True)

                if not config.verbose:
                    total = len(scenario.qa_pairs)
                    print(f" {correct_count}/{total} correct "
                          f"({correct_count/total*100:.1f}%)")

                await adapter.reset(scenario.scenario_id)

        finally:
            await adapter.teardown()

        all_results[adapter_name] = adapter_results

    return build_locomo_report(all_results, config)


def parse_args() -> BenchmarkConfig:
    """Parse CLI arguments into a BenchmarkConfig."""
    parser = argparse.ArgumentParser(
        description="SAMB/LOCOMO Benchmark Runner — evaluate memory systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--benchmark", choices=["samb", "locomo"], default="samb",
        help="Benchmark to run: samb (task+fact evaluation) or locomo (industry comparison). "
             "Default: samb.",
    )
    parser.add_argument(
        "--adapter", nargs="+", default=None,
        help=f"Adapters to evaluate (available: {', '.join(list_adapters())}). "
             f"Default: all available.",
    )
    parser.add_argument(
        "--scenario", nargs="+", default=None,
        help="Scenario numbers to evaluate (e.g., 01 02). Default: all.",
    )
    parser.add_argument(
        "--k", type=int, default=10,
        help="Number of retrieval results (default: 10)",
    )
    parser.add_argument(
        "--answer-model", default="gpt-4o-mini",
        help="Model for answer generation (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--judge-model", default="gpt-4o-mini",
        help="Model for judging (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--output", nargs="+", default=["json", "table"],
        choices=["json", "table"],
        help="Output formats (default: json table)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed per-QA results",
    )
    args = parser.parse_args()

    available = list_adapters()
    adapters = args.adapter or available

    # Validate adapters
    for a in adapters:
        if a not in available:
            parser.error(f"Adapter {a!r} not available. Available: {', '.join(available)}")

    return BenchmarkConfig(
        benchmark=args.benchmark,
        adapters=adapters,
        scenarios=args.scenario,
        k=args.k,
        answer_model=args.answer_model,
        judge_model=args.judge_model,
        output_formats=args.output,
        verbose=args.verbose,
    )


def main():
    config = parse_args()

    start = time.perf_counter()
    report = asyncio.run(run_benchmark(config))
    elapsed = time.perf_counter() - start

    print(f"\nTotal time: {elapsed:.1f}s")

    # Output
    if "table" in config.output_formats:
        print_table(report)

    if "json" in config.output_formats:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = config.benchmark
        output_path = config.results_dir / f"{prefix}_results_{timestamp}.json"
        save_json(report, output_path)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
