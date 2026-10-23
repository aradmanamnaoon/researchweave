"""Reliability diagnostics beyond a single coefficient."""

from __future__ import annotations

from typing import Any

import numpy as np

from .errors import AnalysisError, require
from .models import Dataset
from .multivariate import extract_numeric_matrix


def _cronbach_alpha(matrix: np.ndarray) -> float:
    require(
        matrix.ndim == 2 and matrix.shape[0] >= 3 and matrix.shape[1] >= 2,
        "Alpha needs >=3 cases and >=2 items",
    )
    item_variance = matrix.var(axis=0, ddof=1)
    total_variance = matrix.sum(axis=1).var(ddof=1)
    require(bool(total_variance > 0), "Total score variance is zero")
    k = matrix.shape[1]
    return float(k / (k - 1) * (1 - item_variance.sum() / total_variance))


def _standardized_alpha(matrix: np.ndarray) -> float:
    require(
        bool(np.all(matrix.std(axis=0, ddof=1) > 0)),
        "Standardized alpha undefined for constant item",
    )
    correlation = np.corrcoef(matrix, rowvar=False)
    k = correlation.shape[0]
    mean_r = float((correlation.sum() - k) / (k * (k - 1)))
    denominator = 1 + (k - 1) * mean_r
    require(denominator != 0, "Standardized alpha denominator is zero")
    return float(k * mean_r / denominator)


def _omega_total(matrix: np.ndarray) -> tuple[float, dict[str, float], dict[str, float]]:
    """One-factor omega total from principal-axis factor loadings."""

    from statsmodels.multivariate.factor import Factor

    z = (matrix - matrix.mean(axis=0)) / matrix.std(axis=0, ddof=1)
    try:
        fitted = Factor(z, n_factor=1, method="pa", smc=True).fit(maxiter=300)
    except (ValueError, np.linalg.LinAlgError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", "One-factor reliability model failed") from exc
    loadings = np.asarray(fitted.loadings, dtype=float).reshape(-1)
    uniqueness = np.asarray(fitted.uniqueness, dtype=float).reshape(-1)
    require(
        bool(np.all(np.isfinite(loadings))) and bool(np.all(np.isfinite(uniqueness))),
        "Invalid omega factor solution",
    )
    anchor = int(np.argmax(np.abs(loadings)))
    if loadings[anchor] < 0:
        loadings *= -1
    require(bool(np.all(uniqueness >= -1e-8)), "Improper one-factor solution for omega")
    error = float(np.clip(uniqueness, 0, None).sum())
    common = float(loadings.sum() ** 2)
    require(common + error > 0, "Omega denominator is zero")
    names = [str(index) for index in range(len(loadings))]
    return (
        common / (common + error),
        dict(zip(names, loadings.tolist(), strict=True)),
        dict(zip(names, uniqueness.tolist(), strict=True)),
    )


def reliability_diagnostics(
    dataset: Dataset,
    columns: list[str],
    *,
    reverse: list[str] | None = None,
    scale_min: float | None = None,
    scale_max: float | None = None,
    bootstrap_iterations: int = 0,
    seed: int = 0,
) -> dict[str, Any]:
    """Alpha, split-half, omega, item-total and alpha-if-deleted diagnostics."""

    reverse = reverse or []
    require(
        len(columns) >= 2 and len(set(columns)) == len(columns),
        "At least two distinct items required",
    )
    require(set(reverse) <= set(columns), "Reverse item missing from scale")
    require(
        not reverse or (scale_min is not None and scale_max is not None and scale_min < scale_max),
        "Reverse coding requires explicit scale endpoints",
    )
    selected = extract_numeric_matrix(dataset, columns)
    matrix = selected.matrix.copy()
    if reverse:
        if scale_min is None or scale_max is None:
            raise AnalysisError("INVALID_INPUT", "Reverse coding requires explicit scale endpoints")
        for index, column in enumerate(columns):
            if column not in reverse:
                continue
            require(
                bool(np.all((matrix[:, index] >= scale_min) & (matrix[:, index] <= scale_max))),
                "Reverse-keyed item outside declared endpoints",
            )
            matrix[:, index] = float(scale_min) + float(scale_max) - matrix[:, index]
    alpha = _cronbach_alpha(matrix)
    standardized = _standardized_alpha(matrix)
    split_half: dict[str, Any] | None = None
    if len(columns) >= 4:
        first_indices = np.arange(0, len(columns), 2)
        second_indices = np.arange(1, len(columns), 2)
        first_score = matrix[:, first_indices].sum(axis=1)
        second_score = matrix[:, second_indices].sum(axis=1)
        if np.std(first_score, ddof=1) > 0 and np.std(second_score, ddof=1) > 0:
            correlation = float(np.corrcoef(first_score, second_score)[0, 1])
            denominator = 1 + correlation
            spearman_brown = (
                float(2 * correlation / denominator) if abs(denominator) > 1e-12 else None
            )
            split_half = {
                "method": "deterministic_odd_even_spearman_brown",
                "first_items": [columns[index] for index in first_indices],
                "second_items": [columns[index] for index in second_indices],
                "half_score_correlation": correlation,
                "spearman_brown": spearman_brown,
            }
    diagnostics: dict[str, dict[str, float | None]] = {}
    for index, column in enumerate(columns):
        item = matrix[:, index]
        rest = np.delete(matrix, index, axis=1).sum(axis=1)
        corrected = None
        if np.std(item, ddof=1) > 0 and np.std(rest, ddof=1) > 0:
            corrected = float(np.corrcoef(item, rest)[0, 1])
        deleted = _cronbach_alpha(np.delete(matrix, index, axis=1)) if len(columns) > 2 else None
        diagnostics[column] = {
            "corrected_item_total_correlation": corrected,
            "alpha_if_deleted": deleted,
            "mean": float(np.mean(item)),
            "sd": float(np.std(item, ddof=1)),
        }
    omega: float | None = None
    loadings: dict[str, float] | None = None
    uniqueness: dict[str, float] | None = None
    warnings: list[str] = []
    if split_half is None:
        warnings.append(
            "Split-half reliability requires at least four items and nonconstant half scores"
        )
    if len(columns) >= 3 and len(matrix) >= max(20, 5 * len(columns)):
        try:
            omega, raw_loadings, raw_uniqueness = _omega_total(matrix)
            loadings = dict(zip(columns, raw_loadings.values(), strict=True))
            uniqueness = dict(zip(columns, raw_uniqueness.values(), strict=True))
        except AnalysisError as exc:
            warnings.append(f"Omega unavailable: {exc.message}")
    else:
        warnings.append("Omega requires at least 3 items and max(20, 5p) complete cases")
    interval: dict[str, float | int | str] | None = None
    if bootstrap_iterations:
        require(
            200 <= bootstrap_iterations <= 20_000, "Reliability bootstrap budget must be 200..20000"
        )
        rng = np.random.default_rng(seed)
        draws: list[float] = []
        for _ in range(bootstrap_iterations):
            sampled = matrix[rng.integers(0, len(matrix), size=len(matrix))]
            try:
                draws.append(_cronbach_alpha(sampled))
            except AnalysisError:
                continue
        require(
            len(draws) >= bootstrap_iterations * 0.9,
            "Too many invalid bootstrap reliability samples",
        )
        lower, upper = np.quantile(draws, [0.025, 0.975])
        interval = {
            "lower": float(lower),
            "upper": float(upper),
            "iterations_requested": bootstrap_iterations,
            "iterations_valid": len(draws),
            "seed": seed,
            "method": "case_percentile_bootstrap",
        }
    return {
        "method": "classical_test_theory_reliability",
        "alpha": alpha,
        "standardized_alpha": standardized,
        "split_half": split_half,
        "omega_total_one_factor": omega,
        "one_factor_loadings": loadings,
        "one_factor_uniqueness": uniqueness,
        "alpha_confidence_interval": interval,
        "items": diagnostics,
        "reverse_items": reverse,
        "scale_min": scale_min,
        "scale_max": scale_max,
        "n_total": selected.n_total,
        "n_complete": len(matrix),
        "n_excluded": selected.n_excluded,
        "warnings": warnings,
        "limitations": [
            "Reliability coefficients do not establish unidimensionality or validity",
            "Odd/even split-half reliability depends on item ordering; inspect alternative "
            "splits if justified",
            "Omega uses a one-factor continuous-item principal-axis model",
            "Complete-case analysis is used for all coefficients",
        ],
        "dataset_revision": dataset.revision,
    }
