"""Regression diagnostics preserve red flags rather than altering fitted results."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from .errors import require
from .generalized import design_matrix
from .models import Dataset


def ols_diagnostics(
    dataset: Dataset, outcome: str, predictors: list[str], *, leverage_multiplier: float = 2.0
) -> dict[str, Any]:
    """Influence/residual and BP/JB tests with correct complete-case accounting."""
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import het_breuschpagan

    require(1 <= leverage_multiplier <= 10, "Leverage threshold factor must be between 1 and 10")
    matrix, response, excluded = design_matrix(dataset, outcome, predictors)
    require(
        len(response) > len(predictors) + 5, "Diagnostics need sufficient residual observations"
    )
    fitted = sm.OLS(response, matrix).fit()
    influence = fitted.get_influence()
    leverage = np.asarray(influence.hat_matrix_diag)
    residuals = np.asarray(fitted.resid)
    stud = np.asarray(influence.resid_studentized_external)
    cooks = np.asarray(influence.cooks_distance[0])
    threshold = leverage_multiplier * matrix.shape[1] / len(response)
    high_leverage = np.flatnonzero(leverage > threshold).tolist()
    influential = np.flatnonzero(cooks > 4 / len(response)).tolist()
    bp = het_breuschpagan(residuals, matrix)
    normality = stats.jarque_bera(residuals)
    warnings: list[str] = []
    if high_leverage:
        warnings.append("High-leverage observations require inspection")
    if influential:
        warnings.append("Cook's-distance flag; influence not automatically repaired")
    if bp[1] < 0.05:
        warnings.append("Breusch–Pagan test suggests unequal residual variance")
    if normality.pvalue < 0.05:
        warnings.append("Jarque–Bera test suggests residual non-normality")
    return {
        "model": "ordinary_ols",
        "dataset_revision": dataset.revision,
        "n_total": len(dataset.records),
        "n_used": len(response),
        "n_excluded": excluded,
        "predictors": predictors,
        "residuals": residuals.tolist(),
        "fitted": fitted.fittedvalues.tolist(),
        "leverage": leverage.tolist(),
        "studentized_residuals": stud.tolist(),
        "cooks_distance": cooks.tolist(),
        "leverage_threshold": threshold,
        "high_leverage_indices": high_leverage,
        "potentially_influential_indices": influential,
        "breusch_pagan": {
            "lm_statistic": float(bp[0]),
            "lm_p_value": float(bp[1]),
            "f_statistic": float(bp[2]),
            "f_p_value": float(bp[3]),
        },
        "jarque_bera": {
            "statistic": float(normality.statistic),
            "p_value": float(normality.pvalue),
        },
        "warnings": warnings,
        "cautions": [
            "Threshold flags are heuristics, not automatic exclusions",
            "Residual tests depend on specification and sampling design",
        ],
    }


def variance_inflation(dataset: Dataset, predictors: list[str]) -> dict[str, Any]:
    """Variance inflation factors for the specified predictors with intercept."""
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    require(
        2 <= len(predictors) <= 50 and len(set(predictors)) == len(predictors),
        "At least two distinct predictors required",
    )
    require(all(column in dataset.columns for column in predictors), "Unknown predictor")
    rows = [row for row in dataset.records if all(row[col] is not None for col in predictors)]
    require(len(rows) >= len(predictors) + 3, "Insufficient complete predictor rows")
    from .models import finite_number

    matrix = np.asarray(
        [[1.0, *[finite_number(row[col]) for col in predictors]] for row in rows], dtype=float
    )
    require(
        np.linalg.matrix_rank(matrix) == matrix.shape[1],
        "Perfect collinearity prevents finite VIF estimates",
    )
    values = {
        column: float(variance_inflation_factor(matrix, index + 1))
        for index, column in enumerate(predictors)
    }
    require(
        all(math.isfinite(v) for v in values.values()),
        "Numerical VIF calculation was not finite",
        "INTEGRITY_FAILURE",
    )
    return {
        "vif": values,
        "n_total": len(dataset.records),
        "n_complete": len(rows),
        "n_excluded": len(dataset.records) - len(rows),
        "warnings": [f"{name} VIF exceeds 10" for name, value in values.items() if value > 10],
        "definition": "VIF=1/(1-R_squared) from auxiliary OLS with intercept",
    }


def residual_outlier_flags(
    dataset: Dataset, outcome: str, predictors: list[str], *, threshold: float = 3.0
) -> dict[str, Any]:
    """Return source-case offsets for large standardized residuals (no mutations)."""
    import statsmodels.api as sm

    require(1 <= threshold <= 8, "Studentized residual threshold outside range")
    matrix, response, excluded = design_matrix(dataset, outcome, predictors)
    fitted = sm.OLS(response, matrix).fit()
    influence = fitted.get_influence()
    studentized = np.asarray(influence.resid_studentized_external)
    require(
        bool(np.all(np.isfinite(studentized))), "Studentized residuals undefined for this design"
    )
    original_indices = [
        index
        for index, row in enumerate(dataset.records)
        if all(row[col] is not None for col in [outcome, *predictors])
    ]
    flagged = [
        {"row_index": original_indices[index], "studentized_residual": float(value)}
        for index, value in enumerate(studentized)
        if abs(value) > threshold
    ]
    return {
        "flagged": flagged,
        "threshold": threshold,
        "n_total": len(dataset.records),
        "n_complete": len(response),
        "n_excluded": excluded,
        "warning": "Outlier flags require researcher review; no observations removed",
    }
