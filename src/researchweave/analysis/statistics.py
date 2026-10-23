"""Scientific methods with explicit denominators, designs, and error conditions."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from .errors import AnalysisError, require
from .models import Dataset, ScientificResult, finite_number, runtime_versions


def numeric(dataset: Dataset, column: str) -> tuple[np.ndarray, int]:
    require(column in dataset.columns, "Unknown variable", "NOT_FOUND")
    values = [
        finite_number(row[column], name=column)
        for row in dataset.records
        if row[column] is not None
    ]
    return np.asarray(values, dtype=np.float64), len(dataset.records) - len(values)


def describe(dataset: Dataset, column: str) -> dict[str, Any]:
    values, missing = numeric(dataset, column)
    n = len(values)
    require(n > 0, "No valid observations")
    mean = float(np.mean(values))
    median = float(np.median(values))
    sd = float(np.std(values, ddof=1)) if n > 1 else None
    sem = sd / math.sqrt(n) if sd is not None else None
    mean_ci = None
    if sem is not None:
        cutoff = float(stats.t.ppf(0.975, n - 1))
        mean_ci = [mean - cutoff * sem, mean + cutoff * sem]
    mad = float(np.median(np.abs(values - median)))
    skewness = float(stats.skew(values, bias=False)) if n >= 3 and np.ptp(values) > 0 else None
    kurtosis = (
        float(stats.kurtosis(values, fisher=True, bias=False))
        if n >= 4 and np.ptp(values) > 0
        else None
    )
    return {
        "column": column,
        "n_total": len(dataset.records),
        "n_valid": n,
        "n_missing": missing,
        "mean": mean,
        "median": median,
        "sd_sample": sd,
        "standard_error_mean": sem,
        "mean_confidence_interval_95": mean_ci,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "q1": float(np.percentile(values, 25)),
        "q3": float(np.percentile(values, 75)),
        "iqr": float(np.percentile(values, 75) - np.percentile(values, 25)),
        "median_absolute_deviation": mad,
        "skewness_bias_corrected": skewness,
        "excess_kurtosis_bias_corrected": kurtosis,
        "ddof": 1,
        "dataset_revision": dataset.revision,
    }


def frequency_table(dataset: Dataset, column: str) -> dict[str, Any]:
    """Categorical counts and percentages with explicit missing denominator."""

    require(column in dataset.columns, "Unknown variable", "NOT_FOUND")
    variable = next(value for value in dataset.variables if value.name == column)
    missing_codes = set(variable.missing_values)
    counts: dict[str, int] = {}
    missing = 0
    for row in dataset.records:
        value = row[column]
        if value is None or str(value) in missing_codes:
            missing += 1
            continue
        label = str(value)
        counts[label] = counts.get(label, 0) + 1
    valid = sum(counts.values())
    require(valid > 0, "No valid categorical observations")
    order = list(variable.category_order)
    observed = sorted(set(counts) - set(order))
    levels = [*order, *observed]
    return {
        "column": column,
        "n_total": len(dataset.records),
        "n_valid": valid,
        "n_missing": missing,
        "levels": [
            {
                "value": level,
                "label": variable.value_labels.get(level, level),
                "count": counts.get(level, 0),
                "percent_valid": counts.get(level, 0) / valid * 100,
                "percent_total": counts.get(level, 0) / len(dataset.records) * 100,
            }
            for level in levels
            if counts.get(level, 0) > 0 or level in order
        ],
        "dataset_revision": dataset.revision,
    }


def grouped_describe(dataset: Dataset, column: str, group: str) -> dict[str, Any]:
    """Numeric descriptives by explicit observed group with denominator accounting."""

    require(column in dataset.columns and group in dataset.columns, "Unknown grouped variable")
    require(column != group, "Group and outcome must differ")
    levels = sorted({str(row[group]) for row in dataset.records if row[group] is not None})
    require(1 <= len(levels) <= 1000, "Invalid group count", "RESOURCE_LIMIT")
    output = []
    for level in levels:
        values = [
            finite_number(row[column], name=column)
            for row in dataset.records
            if row[group] is not None and str(row[group]) == level and row[column] is not None
        ]
        if not values:
            output.append({"level": level, "n_valid": 0, "mean": None, "sd_sample": None})
            continue
        array = np.asarray(values, dtype=float)
        output.append(
            {
                "level": level,
                "n_valid": len(values),
                "mean": float(np.mean(array)),
                "median": float(np.median(array)),
                "sd_sample": float(np.std(array, ddof=1)) if len(values) > 1 else None,
                "q1": float(np.percentile(array, 25)),
                "q3": float(np.percentile(array, 75)),
            }
        )
    return {
        "column": column,
        "group": group,
        "groups": output,
        "n_total": len(dataset.records),
        "dataset_revision": dataset.revision,
    }


def correlation_matrix(
    dataset: Dataset,
    columns: list[str],
    *,
    method: str = "pearson",
    adjustment: str = "holm",
) -> dict[str, Any]:
    """Pairwise correlation matrix with corrected p-values and per-cell denominators."""

    from .modeling import adjust_pvalues

    require(
        2 <= len(columns) <= 100 and len(set(columns)) == len(columns),
        "Use 2..100 distinct columns",
    )
    require(all(column in dataset.columns for column in columns), "Unknown correlation column")
    require(method in {"pearson", "spearman", "kendall"}, "Unsupported correlation")
    raw_p: list[float] = []
    cells: list[tuple[int, int, ScientificResult]] = []
    matrix: list[list[float | None]] = [[None for _ in columns] for _ in columns]
    denominators: list[list[int]] = [[0 for _ in columns] for _ in columns]
    for index in range(len(columns)):
        matrix[index][index] = 1.0
        denominators[index][index] = sum(row[columns[index]] is not None for row in dataset.records)
        for other in range(index + 1, len(columns)):
            result = correlation(dataset, columns[index], columns[other], method)
            if result.estimate is None or result.p_value is None:
                raise AnalysisError("INTEGRITY_FAILURE", "Correlation result is incomplete")
            value = float(result.estimate)
            matrix[index][other] = matrix[other][index] = value
            denominators[index][other] = denominators[other][index] = result.n_used
            raw_p.append(float(result.p_value))
            cells.append((index, other, result))
    adjusted = adjust_pvalues(raw_p, method=adjustment) if raw_p else []
    tests = []
    for (index, other, result), adjusted_p in zip(cells, adjusted, strict=True):
        tests.append(
            {
                "first": columns[index],
                "second": columns[other],
                "estimate": result.estimate,
                "p_value": result.p_value,
                "adjusted_p_value": adjusted_p,
                "n_used": result.n_used,
                "details": result.details,
            }
        )
    return {
        "method": method,
        "columns": columns,
        "correlation": matrix,
        "pairwise_n": denominators,
        "tests": tests,
        "multiplicity_method": adjustment,
        "family_definition": "all unique pairwise correlations among declared columns",
        "dataset_revision": dataset.revision,
    }


def t_test(
    dataset: Dataset,
    outcome: str,
    *,
    group: str | None = None,
    groups: tuple[str, str] | None = None,
    paired: str | None = None,
    alternative: str = "two-sided",
    equal_variance: bool = False,
    null_mean: float = 0,
    alpha: float = 0.05,
) -> ScientificResult:
    require(alternative in ("two-sided", "less", "greater"), "Invalid alternative")
    require(0 < alpha < 1, "alpha must be between zero and one")
    require(not (group and paired), "Paired and independent designs are different")
    warnings: list[str] = []
    if paired:
        require(paired in dataset.columns and outcome in dataset.columns, "Unknown paired columns")
        pairs = [
            (finite_number(row[outcome]), finite_number(row[paired]))
            for row in dataset.records
            if row[outcome] is not None and row[paired] is not None
        ]
        require(len(pairs) >= 2, "At least two complete pairs required")
        differences = np.asarray([a - b for a, b in pairs])
        require(bool(np.var(differences, ddof=1) > 0), "Constant paired differences")
        tested = stats.ttest_1samp(differences, popmean=null_mean, alternative=alternative)
        estimate = float(np.mean(differences) - null_mean)
        se = float(stats.sem(differences))
        df = float(len(pairs) - 1)
        effect = {"cohen_dz": estimate / float(np.std(differences, ddof=1))}
        used = len(pairs)
        method = "paired_t"
    elif group:
        require(
            group in dataset.columns and outcome in dataset.columns,
            "Unknown grouping/outcome column",
        )
        require(
            groups is not None and len(groups) == 2 and groups[0] != groups[1],
            "Exactly two explicitly ordered groups required",
        )
        if groups is None:
            raise AnalysisError("INVALID_INPUT", "Exactly two explicitly ordered groups required")
        values = [
            [
                finite_number(row[outcome])
                for row in dataset.records
                if row[group] == level and row[outcome] is not None
            ]
            for level in groups
        ]
        require(min(map(len, values)) >= 2, "Each group needs at least two valid observations")
        x, y = map(lambda v: np.asarray(v, dtype=float), values)
        vx, vy = float(np.var(x, ddof=1)), float(np.var(y, ddof=1))
        require(vx + vy > 0, "Both groups have constant values")
        tested = stats.ttest_ind(x, y, equal_var=equal_variance, alternative=alternative)
        estimate = float(np.mean(x) - np.mean(y))
        df = (
            float(len(x) + len(y) - 2)
            if equal_variance
            else float(
                (vx / len(x) + vy / len(y)) ** 2
                / ((vx / len(x)) ** 2 / (len(x) - 1) + (vy / len(y)) ** 2 / (len(y) - 1))
            )
        )
        se = (
            math.sqrt(vx / len(x) + vy / len(y))
            if not equal_variance
            else math.sqrt(((len(x) - 1) * vx + (len(y) - 1) * vy) / df * (1 / len(x) + 1 / len(y)))
        )
        pooled = math.sqrt(((len(x) - 1) * vx + (len(y) - 1) * vy) / (len(x) + len(y) - 2))
        effect = {"cohen_d": estimate / pooled} if pooled else {}
        used = len(x) + len(y)
        method = "student_t" if equal_variance else "welch_t"
        if any(row[group] not in groups and row[group] is not None for row in dataset.records):
            warnings.append("Other group levels excluded by explicit selection")
    else:
        sample, _ = numeric(dataset, outcome)
        require(
            len(sample) >= 2 and bool(np.var(sample, ddof=1) > 0),
            "At least two nonconstant observations required",
        )
        tested = stats.ttest_1samp(sample, popmean=null_mean, alternative=alternative)
        estimate = float(np.mean(sample) - null_mean)
        df = float(len(sample) - 1)
        se = float(stats.sem(sample))
        effect = {"cohen_d": estimate / float(np.std(sample, ddof=1))}
        used = len(sample)
        method = "one_sample_t"
    cutoff = stats.t.ppf(1 - alpha / 2, df)
    ci = (estimate - cutoff * se, estimate + cutoff * se)
    if alternative == "less":
        ci = (-math.inf, estimate + stats.t.ppf(1 - alpha, df) * se)
    elif alternative == "greater":
        ci = (estimate - stats.t.ppf(1 - alpha, df) * se, math.inf)
    return ScientificResult(
        method,
        dataset.revision,
        len(dataset.records),
        used,
        len(dataset.records) - used,
        estimate,
        float(tested.statistic),
        float(tested.pvalue),
        df,
        ci,
        effect,
        {
            "alternative": alternative,
            "alpha": alpha,
            "outcome": outcome,
            "group": group,
            "levels": groups,
            "paired": paired,
        },
        tuple(warnings),
        (
            "Observations independent within chosen design",
            "Sampling and residual assumptions require researcher review",
        ),
        runtime_versions(),
    )


def correlation(dataset: Dataset, x: str, y: str, method: str = "pearson") -> ScientificResult:
    require(x != y and x in dataset.columns and y in dataset.columns, "Invalid variables")
    require(method in ("pearson", "spearman", "kendall"), "Unsupported correlation")
    pairs = [
        (finite_number(row[x]), finite_number(row[y]))
        for row in dataset.records
        if row[x] is not None and row[y] is not None
    ]
    require(len(pairs) >= 3, "At least three complete pairs required")
    a, b = np.asarray(pairs, dtype=float).T
    require(np.std(a) > 0 and np.std(b) > 0, "Constant column")
    function = {
        "pearson": stats.pearsonr,
        "spearman": stats.spearmanr,
        "kendall": stats.kendalltau,
    }[method]
    output = function(a, b)
    details: dict[str, Any] = {"variables": [x, y], "missing_policy": "pairwise"}
    if method == "pearson" and len(pairs) >= 4 and abs(float(output.statistic)) < 1:
        fisher = math.atanh(float(output.statistic))
        se = 1 / math.sqrt(len(pairs) - 3)
        cutoff = float(stats.norm.ppf(0.975))
        details["fisher_z_confidence_interval_95"] = [
            math.tanh(fisher - cutoff * se),
            math.tanh(fisher + cutoff * se),
        ]
    else:
        details["confidence_interval"] = None
    return ScientificResult(
        method,
        dataset.revision,
        len(dataset.records),
        len(pairs),
        len(dataset.records) - len(pairs),
        float(output.statistic),
        float(output.statistic),
        float(output.pvalue),
        details=details,
        assumptions=("Independence and sampling design must be reviewed",),
        versions=runtime_versions(),
    )


def reliability(
    dataset: Dataset,
    columns: list[str],
    *,
    reverse: list[str] | None = None,
    scale_min: float | None = None,
    scale_max: float | None = None,
) -> ScientificResult:
    require(len(columns) >= 2 and len(set(columns)) == len(columns), "At least two distinct items")
    require(all(column in dataset.columns for column in columns), "Unknown scale item")
    reverse = reverse or []
    require(set(reverse) <= set(columns), "Reverse item missing from scale")
    require(
        not reverse or (scale_min is not None and scale_max is not None and scale_min < scale_max),
        "Reverse coding needs explicit valid scale endpoints",
    )
    if reverse and (scale_min is None or scale_max is None):
        raise AnalysisError("INVALID_INPUT", "Reverse coding needs explicit valid scale endpoints")
    rows: list[list[float]] = []
    if reverse and (scale_min is None or scale_max is None):
        raise AnalysisError("INVALID_INPUT", "Reverse coding needs explicit valid scale endpoints")
    for row in dataset.records:
        if any(row[c] is None for c in columns):
            continue
        values = [finite_number(row[c], name=c) for c in columns]
        if reverse:
            for i, column in enumerate(columns):
                if column in reverse:
                    if scale_min is None or scale_max is None:
                        raise AnalysisError(
                            "INVALID_INPUT", "Reverse coding needs explicit valid scale endpoints"
                        )
                    require(
                        scale_min <= values[i] <= scale_max, "Item outside declared reverse scale"
                    )
                    values[i] = scale_min + scale_max - values[i]
        rows.append(values)
    require(len(rows) >= 3, "At least three complete scale cases required")
    matrix = np.asarray(rows)
    variances = matrix.var(axis=0, ddof=1)
    total_variance = matrix.sum(axis=1).var(ddof=1)
    require(bool(total_variance > 0), "Zero total score variance")
    alpha = len(columns) / (len(columns) - 1) * (1 - sum(variances) / total_variance)
    return ScientificResult(
        "cronbach_alpha",
        dataset.revision,
        len(dataset.records),
        len(rows),
        len(dataset.records) - len(rows),
        float(alpha),
        details={
            "items": columns,
            "reverse": reverse,
            "scale_min": scale_min,
            "scale_max": scale_max,
            "missing_policy": "listwise",
        },
        warnings=("Alpha alone does not establish unidimensionality",),
        versions=runtime_versions(),
    )
