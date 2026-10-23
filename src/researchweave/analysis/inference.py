"""Categorical inference, nonparametric procedures and deterministic resampling."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np
from scipy import stats

from .errors import require
from .models import Dataset, ScientificResult, digest, finite_number, runtime_versions


def contingency(
    dataset: Dataset, first: str, second: str, *, correction: bool = False
) -> dict[str, Any]:
    """Contingency table, chi-square warning flags, optional 2x2 exact test."""
    require(
        first in dataset.columns and second in dataset.columns and first != second,
        "Two distinct categorical variables required",
    )
    rows = [
        (row[first], row[second])
        for row in dataset.records
        if row[first] is not None and row[second] is not None
    ]
    require(bool(rows), "No complete rows")
    labels_a = sorted({str(a) for a, _ in rows})
    labels_b = sorted({str(b) for _, b in rows})
    require(len(labels_a) >= 2 and len(labels_b) >= 2, "At least two levels per variable")
    require(len(labels_a) * len(labels_b) <= 10000, "Too many contingency cells", "RESOURCE_LIMIT")
    first_ix = {label: i for i, label in enumerate(labels_a)}
    second_ix = {label: i for i, label in enumerate(labels_b)}
    counts = np.zeros((len(labels_a), len(labels_b)), dtype=np.int64)
    for a, b in rows:
        counts[first_ix[str(a)], second_ix[str(b)]] += 1
    require(
        bool(np.all(counts.sum(axis=0) > 0)) and bool(np.all(counts.sum(axis=1) > 0)),
        "Empty margin",
    )
    chi = stats.chi2_contingency(counts, correction=correction)
    warning = "Expected count below five; chi-square approximation may be unsuitable"
    warnings = [warning] if bool(np.any(chi.expected_freq < 5)) else []
    fisher: dict[str, Any] | None = None
    if counts.shape == (2, 2):
        odds, exact_p = stats.fisher_exact(counts)
        corrected = counts.astype(float)
        used_correction = bool(np.any(corrected == 0))
        if used_correction:
            corrected += 0.5
        log_odds = float(
            np.log((corrected[0, 0] * corrected[1, 1]) / (corrected[0, 1] * corrected[1, 0]))
        )
        log_se = float(np.sqrt(np.sum(1 / corrected)))
        cutoff = float(stats.norm.ppf(0.975))
        fisher = {
            "odds_ratio": float(odds),
            "two_sided_p": float(exact_p),
            "odds_ratio_ci_95": [
                float(np.exp(log_odds - cutoff * log_se)),
                float(np.exp(log_odds + cutoff * log_se)),
            ],
            "zero_cell_correction_for_ci": used_correction,
        }
    n = counts.sum()
    row_totals = counts.sum(axis=1, keepdims=True)
    column_totals = counts.sum(axis=0, keepdims=True)
    phi2 = float(chi.statistic / n)
    cramer_v = math.sqrt(phi2 / max(1, min(counts.shape[0] - 1, counts.shape[1] - 1)))
    return {
        "variables": [first, second],
        "row_levels": labels_a,
        "column_levels": labels_b,
        "counts": counts.tolist(),
        "expected": chi.expected_freq.tolist(),
        "row_percent": (counts / row_totals * 100).tolist(),
        "column_percent": (counts / column_totals * 100).tolist(),
        "total_percent": (counts / n * 100).tolist(),
        "chi_squared": float(chi.statistic),
        "df": int(chi.dof),
        "p_value": float(chi.pvalue),
        "cramers_v": cramer_v,
        "fisher_2x2": fisher,
        "n_total": len(dataset.records),
        "n_used": len(rows),
        "n_excluded": len(dataset.records) - len(rows),
        "warnings": warnings,
        "assumptions": ["Independent sampling units", "Adequate expected count rule"],
        "dataset_revision": dataset.revision,
    }


def independent_rank_test(
    dataset: Dataset,
    outcome: str,
    group: str,
    levels: tuple[str, str],
    *,
    alternative: str = "two-sided",
) -> ScientificResult:
    """Mann-Whitney rank test with explicit tie-aware asymptotic behavior."""
    require(outcome in dataset.columns and group in dataset.columns, "Unknown columns")
    require(len(levels) == 2 and levels[0] != levels[1], "Two distinct levels required")
    require(alternative in ("two-sided", "less", "greater"), "Invalid alternative")
    values = [
        [
            finite_number(row[outcome])
            for row in dataset.records
            if row[group] == label and row[outcome] is not None
        ]
        for label in levels
    ]
    require(bool(values[0]) and bool(values[1]), "Both groups must have observations")
    tested = stats.mannwhitneyu(values[0], values[1], alternative=alternative, method="asymptotic")
    n = len(values[0]) + len(values[1])
    rank_biserial = 2 * float(tested.statistic) / (len(values[0]) * len(values[1])) - 1
    return ScientificResult(
        "mann_whitney_u",
        dataset.revision,
        len(dataset.records),
        n,
        len(dataset.records) - n,
        statistic=float(tested.statistic),
        p_value=float(tested.pvalue),
        effect={"rank_biserial": rank_biserial},
        details={
            "levels": levels,
            "alternative": alternative,
            "tie_handling": "scipy asymptotic tie correction",
            "n_per_group": list(map(len, values)),
        },
        assumptions=(
            "Observations independent across groups",
            "Rank interpretation requires distribution review",
        ),
        versions=runtime_versions(),
    )


def one_way_anova(
    dataset: Dataset, outcome: str, group: str, *, levels: list[str]
) -> ScientificResult:
    require(outcome in dataset.columns and group in dataset.columns, "Unknown columns")
    require(
        len(levels) >= 2 and len(set(levels)) == len(levels),
        "Two or more distinct explicitly selected levels required",
    )
    values = [
        [
            finite_number(row[outcome])
            for row in dataset.records
            if row[group] == label and row[outcome] is not None
        ]
        for label in levels
    ]
    require(min(map(len, values)) >= 2, "Each group needs at least two observations")
    require(
        sum(len(group_values) for group_values in values) > len(values),
        "Insufficient residual degrees of freedom",
    )
    tested = stats.f_oneway(*values)
    require(np.isfinite(tested.statistic), "ANOVA undefined for degenerate observations")
    total_n = sum(len(group_values) for group_values in values)
    grand_mean = sum(sum(v) for v in values) / total_n
    between = sum(len(v) * (float(np.mean(v)) - grand_mean) ** 2 for v in values)
    total = sum((item - grand_mean) ** 2 for v in values for item in v)
    require(total > 0, "Outcome has no variance")
    return ScientificResult(
        "one_way_anova",
        dataset.revision,
        len(dataset.records),
        total_n,
        len(dataset.records) - total_n,
        statistic=float(tested.statistic),
        p_value=float(tested.pvalue),
        degrees_freedom=float(len(values) - 1),
        effect={"eta_squared": between / total},
        details={
            "df_between": len(values) - 1,
            "df_within": total_n - len(values),
            "levels": levels,
            "n_per_group": list(map(len, values)),
        },
        assumptions=(
            "Independent units",
            "Homogeneous residual variances",
            "Residual distribution warrants review",
        ),
        versions=runtime_versions(),
    )


@dataclass(frozen=True)
class IntervalEstimate:
    estimate: float
    lower: float
    upper: float
    n: int
    iterations: int
    seed: int
    method: str
    distribution_hash: str


def bootstrap_mean(
    values: list[float], *, seed: int, iterations: int = 2000, confidence: float = 0.95
) -> IntervalEstimate:
    """Individual IID percentile bootstrap; clustering requires another method."""
    require(100 <= iterations <= 100_000, "Bootstrap budget outside supported range")
    require(0 < confidence < 1, "Confidence must lie within (0,1)")
    samples = np.asarray([finite_number(v) for v in values], dtype=float)
    require(len(samples) >= 3, "At least three values required")
    require(samples.nbytes <= 50_000_000, "Input exceeds memory budget", "RESOURCE_LIMIT")
    rng = np.random.default_rng(seed)
    means = np.empty(iterations)
    for i in range(iterations):
        means[i] = float(np.mean(samples[rng.integers(0, len(samples), size=len(samples))]))
    tail = (1 - confidence) / 2
    lower, upper = np.quantile(means, [tail, 1 - tail])
    return IntervalEstimate(
        float(np.mean(samples)),
        float(lower),
        float(upper),
        len(samples),
        iterations,
        seed,
        "iid_percentile",
        digest(means.tolist()),
    )


def exact_permutation_mean_difference(
    first: list[float], second: list[float], *, alternative: str = "two-sided"
) -> dict[str, float | int | str]:
    """Exhaustive two-independent-group exact randomization null with fixed group sizes."""
    require(alternative in ("two-sided", "less", "greater"), "Invalid alternative")
    require(len(first) >= 1 and len(second) >= 1, "Nonempty groups required")
    pool = [finite_number(v) for v in [*first, *second]]
    require(len(pool) <= 16, "Exact combinatorial budget exceeded", "RESOURCE_LIMIT")
    observed = float(np.mean(first) - np.mean(second))
    total = 0
    extreme = 0
    for ix in combinations(range(len(pool)), len(first)):
        selected = set(ix)
        a = [v for i, v in enumerate(pool) if i in selected]
        b = [v for i, v in enumerate(pool) if i not in selected]
        difference = float(np.mean(a) - np.mean(b))
        extreme += (
            bool(abs(difference) >= abs(observed) - 1e-12)
            if alternative == "two-sided"
            else (
                difference >= observed - 1e-12
                if alternative == "greater"
                else difference <= observed + 1e-12
            )
        )
        total += 1
    return {
        "estimate": observed,
        "p_value": extreme / total,
        "permutations": total,
        "alternative": alternative,
        "assumption": "Independent exchangeable observations under sharp null",
    }
