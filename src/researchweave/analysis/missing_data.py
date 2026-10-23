"""Explicit missing-data policies and reproducible imputation workflows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from .datasets import revise
from .errors import require
from .models import Dataset, finite_number


def _variable_missing(dataset: Dataset, column: str, value: Any) -> bool:
    variable = next(variable for variable in dataset.variables if variable.name == column)
    return value is None or (value is not None and str(value) in set(variable.missing_values))


def complete_case(dataset: Dataset, columns: list[str]) -> tuple[Dataset, dict[str, Any]]:
    """Keep rows complete on the declared analysis columns, including user-missing codes."""

    require(
        bool(columns) and len(set(columns)) == len(columns), "Distinct analysis columns required"
    )
    require(all(column in dataset.columns for column in columns), "Unknown analysis column")
    selected = [
        dict(row)
        for row in dataset.records
        if not any(_variable_missing(dataset, column, row[column]) for column in columns)
    ]
    require(bool(selected), "No complete cases remain")
    receipt = {
        "type": "complete_case",
        "columns": columns,
        "n_total": len(dataset.records),
        "n_used": len(selected),
        "n_excluded": len(dataset.records) - len(selected),
        "missing_definition": "system missing plus declared user-missing codes",
    }
    return revise(dataset, selected, receipt), receipt


def available_case_covariance(dataset: Dataset, columns: list[str]) -> dict[str, Any]:
    """Pairwise covariance/correlation with an explicit denominator matrix."""

    require(
        len(columns) >= 2 and len(set(columns)) == len(columns), "At least two columns required"
    )
    require(all(column in dataset.columns for column in columns), "Unknown analysis column")
    p = len(columns)
    covariance = np.full((p, p), np.nan)
    correlation = np.full((p, p), np.nan)
    counts = np.zeros((p, p), dtype=int)
    for i, first in enumerate(columns):
        for j, second in enumerate(columns[i:], start=i):
            pairs: list[tuple[float, float]] = []
            for row in dataset.records:
                if _variable_missing(dataset, first, row[first]) or _variable_missing(
                    dataset, second, row[second]
                ):
                    continue
                pairs.append(
                    (
                        finite_number(row[first], name=first),
                        finite_number(row[second], name=second),
                    )
                )
            counts[i, j] = counts[j, i] = len(pairs)
            if len(pairs) < 2:
                continue
            array = np.asarray(pairs, dtype=float)
            covariance[i, j] = covariance[j, i] = float(
                np.cov(array[:, 0], array[:, 1], ddof=1)[0, 1]
            )
            if np.std(array[:, 0], ddof=1) > 0 and np.std(array[:, 1], ddof=1) > 0:
                correlation[i, j] = correlation[j, i] = float(
                    np.corrcoef(array[:, 0], array[:, 1])[0, 1]
                )
    return {
        "columns": columns,
        "covariance": [[None if np.isnan(v) else float(v) for v in row] for row in covariance],
        "correlation": [[None if np.isnan(v) else float(v) for v in row] for row in correlation],
        "pairwise_n": counts.tolist(),
        "n_total": len(dataset.records),
        "policy": "available-case pairwise; denominators may differ by cell",
        "warning": "Pairwise covariance matrices need not be positive semidefinite",
        "dataset_revision": dataset.revision,
    }


def simple_impute(
    dataset: Dataset,
    column: str,
    *,
    strategy: Literal["mean", "median", "mode"],
) -> tuple[Dataset, dict[str, Any]]:
    """Single imputation for descriptive sensitivity analysis; never labelled MI."""

    require(column in dataset.columns, "Unknown imputation column")
    require(strategy in {"mean", "median", "mode"}, "Unsupported imputation strategy")
    missing = [
        index
        for index, row in enumerate(dataset.records)
        if _variable_missing(dataset, column, row[column])
    ]
    require(bool(missing), "Column contains no missing values")
    observed_raw = [
        row[column]
        for row in dataset.records
        if not _variable_missing(dataset, column, row[column])
    ]
    require(bool(observed_raw), "Column contains no observed values")
    if strategy == "mode":
        counts: dict[str, int] = {}
        original: dict[str, Any] = {}
        for value in observed_raw:
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
            original[key] = value
        maximum = max(counts.values())
        winners = sorted(key for key, count in counts.items() if count == maximum)
        require(len(winners) == 1, "Mode imputation ambiguous because multiple modes tie")
        fill: Any = original[winners[0]]
    else:
        observed = np.asarray(
            [finite_number(value, name=column) for value in observed_raw], dtype=float
        )
        fill = float(np.mean(observed) if strategy == "mean" else np.median(observed))
        require(math.isfinite(fill), "Imputation summary is non-finite")
    rows = [dict(row) for row in dataset.records]
    for index in missing:
        rows[index][column] = fill
    operation = {
        "type": "simple_imputation",
        "column": column,
        "strategy": strategy,
        "imputed_rows": missing,
        "fill_value": fill,
        "warning": (
            "Single imputation understates uncertainty and is intended for "
            "sensitivity/descriptive use"
        ),
    }
    return revise(dataset, rows, operation), operation


@dataclass(frozen=True)
class MultipleImputation:
    datasets: tuple[Dataset, ...]
    columns: tuple[str, ...]
    seed: int
    method: str
    assumptions: tuple[str, ...]
    missing_counts: dict[str, int]


def _normal_parameters(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    means = np.nanmean(matrix, axis=0)
    require(bool(np.all(np.isfinite(means))), "Each imputation variable needs observed values")
    filled = np.where(np.isnan(matrix), means, matrix)
    require(len(filled) >= 3, "At least three rows required for normal imputation")
    covariance = np.cov(filled, rowvar=False, ddof=1)
    covariance = np.atleast_2d(np.asarray(covariance, dtype=float))
    scale = max(float(np.trace(covariance)) / max(1, covariance.shape[0]), 1.0)
    covariance = covariance + np.eye(covariance.shape[0]) * scale * 1e-8
    require(bool(np.all(np.isfinite(covariance))), "Imputation covariance is non-finite")
    require(
        bool(np.all(np.linalg.eigvalsh(covariance) > 0)),
        "Imputation covariance must be positive definite",
    )
    return means, covariance


def multiple_impute_normal(
    dataset: Dataset,
    columns: list[str],
    *,
    m: int = 5,
    seed: int,
) -> MultipleImputation:
    """Generate stochastic conditional-normal imputations with fixed estimated parameters.

    This is a transparent bounded joint-normal sensitivity workflow.  It does not
    establish MAR/MNAR and it does not draw model parameters, so inferential use
    should include sensitivity to the imputation model.
    """

    require(
        2 <= len(columns) <= 50 and len(set(columns)) == len(columns), "Use 2..50 distinct columns"
    )
    require(all(column in dataset.columns for column in columns), "Unknown imputation column")
    require(2 <= m <= 50, "Number of imputations must be 2..50")
    require(isinstance(seed, int) and 0 <= seed < 2**32, "Seed must be an unsigned 32-bit integer")
    matrix = np.full((len(dataset.records), len(columns)), np.nan, dtype=float)
    missing_counts: dict[str, int] = {}
    for j, column in enumerate(columns):
        count = 0
        for i, row in enumerate(dataset.records):
            if _variable_missing(dataset, column, row[column]):
                count += 1
            else:
                matrix[i, j] = finite_number(row[column], name=column)
        missing_counts[column] = count
        require(len(dataset.records) - count >= 3, f"{column} needs at least three observed values")
    require(any(missing_counts.values()), "Selected columns contain no missing values")
    require(
        not np.any(np.all(np.isnan(matrix), axis=1)),
        "Rows missing all imputation variables are unsupported",
    )
    means, covariance = _normal_parameters(matrix)
    rng = np.random.default_rng(seed)
    outputs: list[Dataset] = []
    for draw in range(m):
        completed = matrix.copy()
        for i in range(len(completed)):
            missing_ix = np.flatnonzero(np.isnan(completed[i]))
            if not len(missing_ix):
                continue
            observed_ix = np.flatnonzero(~np.isnan(completed[i]))
            sigma_mm = covariance[np.ix_(missing_ix, missing_ix)]
            sigma_mo = covariance[np.ix_(missing_ix, observed_ix)]
            sigma_oo = covariance[np.ix_(observed_ix, observed_ix)]
            delta = completed[i, observed_ix] - means[observed_ix]
            inverse = np.linalg.pinv(sigma_oo)
            conditional_mean = means[missing_ix] + sigma_mo @ inverse @ delta
            conditional_cov = sigma_mm - sigma_mo @ inverse @ sigma_mo.T
            conditional_cov = (conditional_cov + conditional_cov.T) / 2
            eigenvalues, eigenvectors = np.linalg.eigh(conditional_cov)
            eigenvalues = np.clip(eigenvalues, 1e-12, None)
            stable_cov = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
            completed[i, missing_ix] = rng.multivariate_normal(conditional_mean, stable_cov)
        rows = [dict(row) for row in dataset.records]
        for i, row in enumerate(rows):
            for j, column in enumerate(columns):
                if _variable_missing(dataset, column, dataset.records[i][column]):
                    row[column] = float(completed[i, j])
        operation = {
            "type": "multiple_imputation",
            "method": "conditional_multivariate_normal_fixed_parameters",
            "columns": columns,
            "m": m,
            "draw": draw,
            "seed": seed,
            "missing_counts": missing_counts,
        }
        outputs.append(revise(dataset, rows, operation))
    return MultipleImputation(
        tuple(outputs),
        tuple(columns),
        seed,
        "conditional_multivariate_normal_fixed_parameters",
        (
            "Joint multivariate-normal imputation model",
            "Missingness mechanism is not identified from observed data",
            "Model parameters are fixed across imputations; use sensitivity analysis for inference",
        ),
        missing_counts,
    )


def pool_scalar_rubin(estimates: list[float], variances: list[float]) -> dict[str, float | int]:
    """Pool scalar estimates and within-imputation variances using Rubin's rules."""

    require(
        len(estimates) == len(variances) and len(estimates) >= 2,
        "At least two aligned imputations required",
    )
    q = np.asarray([finite_number(value, name="estimate") for value in estimates], dtype=float)
    u = np.asarray([finite_number(value, name="variance") for value in variances], dtype=float)
    require(bool(np.all(u >= 0)), "Within-imputation variances must be nonnegative")
    m = len(q)
    estimate = float(np.mean(q))
    within = float(np.mean(u))
    between = float(np.var(q, ddof=1))
    total = within + (1 + 1 / m) * between
    require(total > 0, "Pooled variance must be positive")
    if between == 0:
        df = math.inf
    else:
        relative = ((1 + 1 / m) * between) / max(within, np.finfo(float).tiny)
        df = (m - 1) * (1 + 1 / relative) ** 2
    return {
        "estimate": estimate,
        "within_variance": within,
        "between_variance": between,
        "total_variance": total,
        "standard_error": math.sqrt(total),
        "degrees_freedom": float(df),
        "m": m,
    }
