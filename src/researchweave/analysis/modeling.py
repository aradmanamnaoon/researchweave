"""Regression, diagnostics and heterogeneity-aware effect pooling."""

from __future__ import annotations

import math
from typing import Any, cast

import numpy as np

from .errors import require
from .models import Dataset, ScientificResult, finite_number, runtime_versions


def linear_regression(
    dataset: Dataset,
    outcome: str,
    predictors: list[str],
    *,
    robust: str = "nonrobust",
    cluster_group: str | None = None,
) -> ScientificResult:
    """Fit OLS with explicit complete-case accounting and singularity rejection."""
    import statsmodels.api as sm

    require(
        robust in ("nonrobust", "HC0", "HC1", "HC2", "HC3", "cluster"),
        "Unknown covariance type",
    )
    require(
        (robust == "cluster") == (cluster_group is not None),
        "Cluster covariance requires exactly one cluster_group",
    )
    require(
        outcome in dataset.columns and bool(predictors) and len(set(predictors)) == len(predictors),
        "Outcome and distinct predictors required",
    )
    require(
        outcome not in predictors and all(c in dataset.columns for c in predictors),
        "Predictor selection invalid",
    )
    columns = [outcome, *predictors, *([cluster_group] if cluster_group else [])]
    require(cluster_group is None or cluster_group in dataset.columns, "Unknown cluster group")
    complete = [row for row in dataset.records if all(row[c] is not None for c in columns)]
    require(len(complete) > len(predictors) + 1, "Insufficient residual degrees of freedom")
    y = np.asarray([finite_number(row[outcome]) for row in complete])
    x = np.asarray([[1.0, *[finite_number(row[c]) for c in predictors]] for row in complete])
    require(np.linalg.matrix_rank(x) == x.shape[1], "Singular design matrix")
    if robust == "cluster":
        cluster_column = cast(str, cluster_group)
        groups = np.asarray([str(row[cluster_column]) for row in complete], dtype=object)
        require(len(np.unique(groups)) >= 2, "Cluster covariance requires at least two clusters")
        fit = sm.OLS(y, x).fit(cov_type="cluster", cov_kwds={"groups": groups})
    else:
        fit = sm.OLS(y, x).fit(cov_type=robust)
    coefficients = {
        name: float(value)
        for name, value in zip(["intercept", *predictors], fit.params, strict=True)
    }
    conf = {
        name: [float(v) for v in interval]
        for name, interval in zip(["intercept", *predictors], fit.conf_int(), strict=True)
    }
    leverage = fit.get_influence().hat_matrix_diag
    warnings = []
    if max(leverage) > 2 * x.shape[1] / len(y):
        warnings.append("Potential high leverage observations; review design")
    if np.ptp(y) == 0:
        warnings.append("Constant outcome; R squared undefined")
    details: dict[str, Any] = {
        "coefficients": coefficients,
        "intervals": conf,
        "p_values": dict(zip(["intercept", *predictors], map(float, fit.pvalues), strict=True)),
        "r_squared": float(fit.rsquared) if math.isfinite(fit.rsquared) else None,
        "residuals": fit.resid.tolist(),
        "fitted": fit.fittedvalues.tolist(),
        "leverage": leverage.tolist(),
        "covariance": robust,
        "cluster_group": cluster_group,
        "missing_policy": "complete_case",
    }
    return ScientificResult(
        "ols",
        dataset.revision,
        len(dataset.records),
        len(y),
        len(dataset.records) - len(y),
        details=details,
        warnings=tuple(warnings),
        assumptions=(
            "Independent units and correctly specified conditional mean",
            "Residual/variance assumptions require design review",
        ),
        versions=runtime_versions(),
    )


def pooled_effects(studies: list[dict[str, Any]], *, model: str = "fixed") -> dict[str, Any]:
    """Inverse-variance fixed or DerSimonian-Laird random effects on one declared scale."""
    require(model in ("fixed", "random_dl"), "Unknown pooling model")
    require(len(studies) >= 2 and len(studies) <= 10000, "Two or more studies required")
    identifiers = [study.get("id") for study in studies]
    require(
        all(isinstance(v, str) and v for v in identifiers)
        and len(set(identifiers)) == len(identifiers),
        "Study identifiers must be distinct",
    )
    scales = {study.get("scale") for study in studies}
    require(
        len(scales) == 1 and next(iter(scales)) in ("mean_difference", "log_or", "fisher_z"),
        "Explicit compatible effect scale required",
    )
    estimates = np.asarray([finite_number(s["estimate"]) for s in studies])
    se = np.asarray([finite_number(s["se"]) for s in studies])
    require(bool(np.all(se > 0)), "Standard errors must be positive")
    weights = 1 / np.square(se)
    fixed_mean = float(np.average(estimates, weights=weights))
    q = float(np.sum(weights * np.square(estimates - fixed_mean)))
    df = len(studies) - 1
    c = float(weights.sum() - np.sum(weights**2) / weights.sum())
    tau2 = max(0.0, (q - df) / c) if model == "random_dl" else 0.0
    pooled_weights = 1 / (se**2 + tau2)
    estimate = float(np.average(estimates, weights=pooled_weights))
    standard_error = math.sqrt(1 / float(pooled_weights.sum()))
    return {
        "model": model,
        "scale": next(iter(scales)),
        "estimate": estimate,
        "standard_error": standard_error,
        "ci_95": [estimate - 1.96 * standard_error, estimate + 1.96 * standard_error],
        "q": q,
        "q_df": df,
        "i_squared": max(0.0, (q - df) / q) if q else 0.0,
        "tau_squared": tau2,
        "n_studies": len(studies),
        "study_ids": identifiers,
        "limitation": "Study independence and effect comparability must be verified",
    }


def adjust_pvalues(pvalues: list[float], *, method: str = "holm") -> list[float]:
    """Correct a declared family of raw p-values, preserving original order."""
    require(method in ("holm", "bonferroni", "bh"), "Unknown multiplicity method")
    require(1 <= len(pvalues) <= 100_000, "Invalid hypothesis family size")
    values = np.asarray([finite_number(v) for v in pvalues])
    require(bool(np.all((values >= 0) & (values <= 1))), "p-values must lie in [0,1]")
    n = len(values)
    if method == "bonferroni":
        return [float(value) for value in np.minimum(values * n, 1)]
    order = np.argsort(values)
    sorted_values = values[order]
    if method == "holm":
        adjusted = np.maximum.accumulate(sorted_values * np.arange(n, 0, -1))
    else:
        adjusted = np.minimum.accumulate((sorted_values * n / np.arange(1, n + 1))[::-1])[::-1]
    result = np.empty(n)
    result[order] = np.minimum(adjusted, 1)
    return [float(value) for value in result]
