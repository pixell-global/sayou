"""Statistical analysis — bootstrap CIs and significance tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ConfidenceInterval:
    """Bootstrap confidence interval."""

    mean: float
    lower: float
    upper: float
    n: int
    n_bootstrap: int


@dataclass
class SignificanceResult:
    """Paired bootstrap significance test result."""

    system_a: str
    system_b: str
    mean_diff: float  # system_a - system_b
    p_value: float
    significant: bool  # after Bonferroni correction
    ci_lower: float
    ci_upper: float


def bootstrap_ci(
    scores: list[float],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    rng: np.random.Generator | None = None,
) -> ConfidenceInterval:
    """Compute bootstrap confidence interval for the mean.

    Args:
        scores: List of scores to bootstrap.
        n_bootstrap: Number of bootstrap samples.
        ci: Confidence level (e.g., 0.95 for 95% CI).
        rng: Optional numpy random generator for reproducibility.
    """
    if not scores:
        return ConfidenceInterval(mean=0.0, lower=0.0, upper=0.0, n=0, n_bootstrap=0)

    rng = rng or np.random.default_rng(42)
    arr = np.array(scores)
    n = len(arr)

    boot_means = np.array([
        np.mean(rng.choice(arr, size=n, replace=True))
        for _ in range(n_bootstrap)
    ])

    alpha = 1 - ci
    lower = float(np.percentile(boot_means, alpha / 2 * 100))
    upper = float(np.percentile(boot_means, (1 - alpha / 2) * 100))

    return ConfidenceInterval(
        mean=float(np.mean(arr)),
        lower=lower,
        upper=upper,
        n=n,
        n_bootstrap=n_bootstrap,
    )


def paired_bootstrap_test(
    scores_a: list[float],
    scores_b: list[float],
    system_a: str,
    system_b: str,
    n_bootstrap: int = 1000,
    n_comparisons: int = 6,
    alpha: float = 0.05,
    rng: np.random.Generator | None = None,
) -> SignificanceResult:
    """Paired bootstrap significance test with Bonferroni correction.

    Tests whether system_a is significantly different from system_b.

    Args:
        scores_a: Scores for system A (one per QA pair).
        scores_b: Scores for system B (same ordering as A).
        system_a: Name of system A.
        system_b: Name of system B.
        n_bootstrap: Number of bootstrap samples.
        n_comparisons: Number of pairwise comparisons (for Bonferroni).
        alpha: Significance level before correction.
        rng: Optional random generator for reproducibility.
    """
    assert len(scores_a) == len(scores_b), "Score lists must have equal length"

    rng = rng or np.random.default_rng(42)
    arr_a = np.array(scores_a)
    arr_b = np.array(scores_b)
    diffs = arr_a - arr_b
    n = len(diffs)

    observed_diff = float(np.mean(diffs))

    boot_diffs = np.array([
        np.mean(rng.choice(diffs, size=n, replace=True))
        for _ in range(n_bootstrap)
    ])

    # Two-sided p-value: proportion of bootstrap diffs on the opposite side of 0
    if observed_diff >= 0:
        p_value = float(np.mean(boot_diffs <= 0)) * 2
    else:
        p_value = float(np.mean(boot_diffs >= 0)) * 2
    p_value = min(p_value, 1.0)

    # Bonferroni correction
    corrected_alpha = alpha / n_comparisons

    ci_lower = float(np.percentile(boot_diffs, 2.5))
    ci_upper = float(np.percentile(boot_diffs, 97.5))

    return SignificanceResult(
        system_a=system_a,
        system_b=system_b,
        mean_diff=observed_diff,
        p_value=p_value,
        significant=p_value < corrected_alpha,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
    )


def compute_all_pairwise(
    system_scores: dict[str, list[float]],
    n_bootstrap: int = 1000,
    rng: np.random.Generator | None = None,
) -> list[SignificanceResult]:
    """Run paired bootstrap tests for all system pairs.

    Args:
        system_scores: Dict mapping system name -> list of scores.
            All lists must have the same length and ordering.
    """
    names = sorted(system_scores.keys())
    n_comparisons = len(names) * (len(names) - 1) // 2
    if n_comparisons == 0:
        return []

    results = []
    for i, name_a in enumerate(names):
        for name_b in names[i + 1:]:
            result = paired_bootstrap_test(
                system_scores[name_a],
                system_scores[name_b],
                name_a,
                name_b,
                n_bootstrap=n_bootstrap,
                n_comparisons=n_comparisons,
                rng=rng,
            )
            results.append(result)

    return results
