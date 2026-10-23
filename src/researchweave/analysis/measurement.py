"""Measurement assessment: dimensionality diagnostics, EFA and rater reliability."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from .errors import AnalysisError, require
from .models import Dataset
from .multivariate import extract_numeric_matrix


def correlation_suitability(dataset: Dataset, columns: list[str]) -> dict[str, Any]:
    """Compute Bartlett's sphericity statistic and Kaiser-Meyer-Olkin measure."""
    selected = extract_numeric_matrix(dataset, columns)
    data = selected.matrix
    n, p = data.shape
    require(
        p >= 3 and n >= max(20, 5 * p),
        "At least 3 variables and max(20, 5p) complete cases required",
    )
    require(
        bool(np.all(np.std(data, axis=0, ddof=1) > 0)),
        "Constant variables prevent factor diagnostics",
    )
    corr = np.corrcoef(data, rowvar=False)
    sign, log_determinant = np.linalg.slogdet(corr)
    require(
        sign > 0 and math.isfinite(log_determinant), "Correlation matrix must be positive definite"
    )
    inverse = np.linalg.inv(corr)
    diagonal = np.sqrt(np.diag(inverse))
    partial = -inverse / np.outer(diagonal, diagonal)
    np.fill_diagonal(partial, 0)
    correlations = corr.copy()
    np.fill_diagonal(correlations, 0)
    squared_r = correlations**2
    squared_p = partial**2
    numerator = float(np.sum(squared_r))
    denominator = numerator + float(np.sum(squared_p))
    require(denominator > 0, "KMO undefined for unrelated variables")
    kmo = numerator / denominator
    kmo_variable = {}
    for index, column in enumerate(columns):
        num = float(np.sum(squared_r[index]))
        den = num + float(np.sum(squared_p[index]))
        kmo_variable[column] = num / den if den > 0 else None
    chi_sq = -(n - 1 - (2 * p + 5) / 6) * log_determinant
    df = p * (p - 1) // 2
    require(chi_sq >= 0, "Invalid Bartlett statistic")
    return {
        "method": "factor_suitability",
        "source_revision": dataset.revision,
        "n_total": selected.n_total,
        "n_complete": n,
        "n_excluded": selected.n_excluded,
        "variables": columns,
        "correlation_matrix": corr.tolist(),
        "bartlett_chi_square": float(chi_sq),
        "bartlett_df": df,
        "bartlett_p_value": float(stats.chi2.sf(chi_sq, df)),
        "kmo_overall": kmo,
        "kmo_per_item": kmo_variable,
        "assumptions": [
            "Bartlett's test uses multivariate-normality-based approximation",
            "KMO is a descriptive sampling-adequacy index, not proof of validity",
            "Complete-case correlations; no ordinal/polychoric approximation",
        ],
    }


def exploratory_factors(
    dataset: Dataset,
    columns: list[str],
    *,
    n_factors: int,
    rotate: str = "varimax",
    maximum_iterations: int = 200,
) -> dict[str, Any]:
    """Principal-axis extraction with optional orthogonal varimax rotation.

    Factor sign and permutation are mathematically nonunique. This output
    fixes signs using the highest-magnitude loading and preserves factor order.
    """
    from statsmodels.multivariate.factor import Factor

    require(rotate in {"varimax", "none"}, "Only varimax or no rotation supported")
    selected = extract_numeric_matrix(dataset, columns)
    matrix = selected.matrix
    n, p = matrix.shape
    require(
        3 <= p <= 80 and n >= max(20, 5 * p),
        "EFA requires 3..80 variables and at least max(20, 5p) cases",
    )
    require(1 <= n_factors < p, "Factors must be fewer than observed variables")
    require(20 <= maximum_iterations <= 500, "Iteration budget must be 20..500")
    suitability = correlation_suitability(dataset, columns)
    try:
        model = Factor(matrix, n_factor=n_factors, method="pa", smc=True)
        fitted = model.fit(maxiter=maximum_iterations)
        if rotate == "varimax":
            fitted.rotate("varimax")
    except (ValueError, np.linalg.LinAlgError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", "Principal-axis EFA could not be estimated") from exc
    loadings = np.asarray(fitted.loadings, dtype=float)
    uniqueness = np.asarray(fitted.uniqueness, dtype=float)
    require(
        loadings.shape == (p, n_factors) and bool(np.all(np.isfinite(loadings))),
        "Factor solution contains invalid loadings",
        "INTEGRITY_FAILURE",
    )
    require(bool(np.all(np.isfinite(uniqueness))), "Factor uniqueness estimates are non-finite")
    for factor in range(n_factors):
        strongest = int(np.argmax(abs(loadings[:, factor])))
        if loadings[strongest, factor] < 0:
            loadings[:, factor] *= -1
    communalities = np.sum(loadings**2, axis=1)
    residual_matrix = np.asarray(suitability["correlation_matrix"]) - (
        loadings @ loadings.T + np.diag(uniqueness)
    )
    residual_offdiag = residual_matrix - np.diag(np.diag(residual_matrix))
    rmsr = float(np.sqrt(np.sum(residual_offdiag**2) / (p * (p - 1))))
    warnings = []
    if bool(np.any(uniqueness < 0)) or bool(np.any(communalities > 1 + 1e-8)):
        warnings.append("Heywood/improper solution: inspect uniqueness and model")
    if suitability["kmo_overall"] < 0.5:
        warnings.append("Overall KMO below 0.5 indicates poor factor suitability")
    return {
        "method": "principal_axis_factor",
        "source_revision": dataset.revision,
        "n_total": selected.n_total,
        "n_complete": n,
        "n_excluded": selected.n_excluded,
        "columns": columns,
        "n_factors": n_factors,
        "rotation": rotate,
        "loadings": {name: loadings[index].tolist() for index, name in enumerate(columns)},
        "uniqueness": dict(zip(columns, uniqueness.tolist(), strict=True)),
        "communality": dict(zip(columns, communalities.tolist(), strict=True)),
        "rmsr_offdiagonal": rmsr,
        "kmo_overall": suitability["kmo_overall"],
        "warnings": warnings,
        "limitations": [
            "Exploratory structure only; cross-validation on independent sample recommended",
            "Continuous Pearson correlations; ordered categorical items need polychoric EFA",
            "Rotated factors are orthogonal under varimax",
        ],
    }


def fleiss_agreement(rating_counts: list[list[int]]) -> dict[str, Any]:
    """Fleiss nominal kappa for identically sized categorical rating groups."""
    from statsmodels.stats.inter_rater import fleiss_kappa

    require(len(rating_counts) >= 3, "Three or more units required")
    matrix = np.asarray(rating_counts, dtype=float)
    require(
        matrix.ndim == 2 and matrix.shape[1] >= 2,
        "Two or more categorical response options required",
    )
    require(
        bool(np.all(matrix >= 0)) and bool(np.all(np.floor(matrix) == matrix)),
        "Rating counts must be nonnegative integers",
    )
    totals = np.sum(matrix, axis=1)
    require(
        bool(np.all(totals == totals[0])) and totals[0] >= 2,
        "Each unit requires the same number of at least two raters",
    )
    require(
        bool(np.count_nonzero(matrix.sum(axis=0)) >= 2),
        "At least two observed response categories required",
    )
    kappa = float(fleiss_kappa(matrix, method="fleiss"))
    require(math.isfinite(kappa), "Fleiss kappa undefined for these ratings")
    return {
        "method": "fleiss_nominal_kappa",
        "kappa": kappa,
        "n_units": int(matrix.shape[0]),
        "n_raters_per_unit": int(totals[0]),
        "n_categories": int(matrix.shape[1]),
        "assumption": "Nominal ratings; each unit receives the same rater count",
    }


def icc_two_way_absolute(ratings: list[list[float]]) -> dict[str, Any]:
    """Shrout-Fleiss ICC(2,1), two-way random absolute agreement, balanced data."""
    matrix = np.asarray(ratings, dtype=float)
    require(
        matrix.ndim == 2 and matrix.shape[0] >= 3 and matrix.shape[1] >= 2,
        "At least 3 targets each rated by at least 2 raters required",
    )
    require(bool(np.all(np.isfinite(matrix))), "ICC ratings must be complete and finite")
    n, k = matrix.shape
    grand = float(np.mean(matrix))
    target_means = matrix.mean(axis=1)
    rater_means = matrix.mean(axis=0)
    ss_targets = k * float(np.sum((target_means - grand) ** 2))
    ss_raters = n * float(np.sum((rater_means - grand) ** 2))
    residual = matrix - target_means[:, None] - rater_means[None, :] + grand
    ss_error = float(np.sum(residual**2))
    ms_targets = ss_targets / (n - 1)
    ms_raters = ss_raters / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))
    denominator = ms_targets + (k - 1) * ms_error + k * (ms_raters - ms_error) / n
    require(denominator > 0, "ICC denominator is not positive")
    icc = (ms_targets - ms_error) / denominator
    return {
        "method": "icc_2_1_absolute_agreement",
        "icc": icc,
        "n_targets": n,
        "n_raters": k,
        "ms_targets": ms_targets,
        "ms_raters": ms_raters,
        "ms_error": ms_error,
        "assumptions": [
            "Balanced ratings on independent targets and shared random raters",
            "Absolute agreement: systematic rater differences reduce agreement",
            "ICC may be negative when inter-target variance is small",
        ],
    }
