"""Random-effects meta-analysis with REML, Hartung-Knapp and influence analysis."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import optimize, stats

from .errors import require
from .models import finite_number


def _inputs(studies: list[dict[str, Any]]) -> tuple[list[str], str, np.ndarray, np.ndarray]:
    require(2 <= len(studies) <= 10000, "Meta-analysis requires 2..10000 studies")
    ids = [study.get("id") for study in studies]
    require(all(isinstance(value, str) and value for value in ids), "Study IDs required")
    require(len(set(ids)) == len(ids), "Study IDs must be unique")
    scales = {study.get("scale") for study in studies}
    require(len(scales) == 1, "Studies must use one declared effect scale")
    scale = str(next(iter(scales)))
    require(
        scale in {"mean_difference", "log_or", "fisher_z", "standardized_mean_difference"},
        "Unsupported meta-analysis scale",
    )
    effects = np.asarray(
        [finite_number(study["estimate"], name="effect") for study in studies], dtype=float
    )
    variances = np.asarray(
        [finite_number(study["se"], name="standard error") ** 2 for study in studies],
        dtype=float,
    )
    require(bool(np.all(variances > 0)), "Study variances must be positive")
    return [str(value) for value in ids], scale, effects, variances


def _reml_tau_squared(effects: np.ndarray, variances: np.ndarray) -> float:
    """Minimize the intercept-only restricted negative log likelihood over tau²."""

    def objective(tau2: float) -> float:
        weights = 1 / (variances + tau2)
        mean = float(np.sum(weights * effects) / np.sum(weights))
        residual = float(np.sum(weights * (effects - mean) ** 2))
        return 0.5 * (
            float(np.sum(np.log(variances + tau2))) + math.log(float(np.sum(weights))) + residual
        )

    upper = max(float(np.var(effects, ddof=1)) * 100, float(np.max(variances)) * 100, 1.0)
    fitted = optimize.minimize_scalar(objective, bounds=(0.0, upper), method="bounded")
    require(
        bool(fitted.success) and math.isfinite(float(fitted.x)),
        "REML heterogeneity fit failed",
        "CONVERGENCE_FAILED",
    )
    return max(0.0, float(fitted.x))


def random_effects_meta(
    studies: list[dict[str, Any]],
    *,
    tau_method: str = "reml",
    hartung_knapp: bool = True,
) -> dict[str, Any]:
    """Random-effects pooling, heterogeneity, prediction and leave-one-out influence."""

    ids, scale, effects, variances = _inputs(studies)
    require(tau_method in {"reml", "dl"}, "Tau method must be reml or dl")
    fixed_weights = 1 / variances
    fixed_mean = float(np.sum(fixed_weights * effects) / np.sum(fixed_weights))
    q = float(np.sum(fixed_weights * (effects - fixed_mean) ** 2))
    df = len(effects) - 1
    c = float(np.sum(fixed_weights) - np.sum(fixed_weights**2) / np.sum(fixed_weights))
    tau2 = _reml_tau_squared(effects, variances) if tau_method == "reml" else max(0.0, (q - df) / c)
    weights = 1 / (variances + tau2)
    estimate = float(np.sum(weights * effects) / np.sum(weights))
    conventional_se = math.sqrt(1 / float(np.sum(weights)))
    qe_random = float(np.sum(weights * (effects - estimate) ** 2))
    hk_scale = qe_random / df if df > 0 else 1.0
    hk_se = math.sqrt(hk_scale / float(np.sum(weights)))
    if hartung_knapp and len(effects) >= 3:
        standard_error = hk_se
        critical = float(stats.t.ppf(0.975, df=df))
        interval_method = "hartung_knapp"
    else:
        standard_error = conventional_se
        critical = float(stats.norm.ppf(0.975))
        interval_method = "normal"
    confidence_interval = [
        estimate - critical * standard_error,
        estimate + critical * standard_error,
    ]
    prediction_critical = float(stats.t.ppf(0.975, df=max(1, len(effects) - 2)))
    prediction_se = math.sqrt(tau2 + conventional_se**2)
    prediction_interval = [
        estimate - prediction_critical * prediction_se,
        estimate + prediction_critical * prediction_se,
    ]
    influence = []
    if len(effects) >= 3:
        for index, study_id in enumerate(ids):
            mask = np.arange(len(effects)) != index
            reduced_tau = (
                _reml_tau_squared(effects[mask], variances[mask])
                if tau_method == "reml"
                else max(
                    0.0,
                    (
                        float(
                            np.sum(
                                (1 / variances[mask])
                                * (
                                    effects[mask]
                                    - np.average(effects[mask], weights=1 / variances[mask])
                                )
                                ** 2
                            )
                        )
                        - (mask.sum() - 1)
                    )
                    / max(
                        1e-12,
                        float(
                            np.sum(1 / variances[mask])
                            - np.sum((1 / variances[mask]) ** 2) / np.sum(1 / variances[mask])
                        ),
                    ),
                )
            )
            reduced_weights = 1 / (variances[mask] + reduced_tau)
            reduced_mean = float(np.average(effects[mask], weights=reduced_weights))
            influence.append(
                {
                    "omitted_study": study_id,
                    "estimate": reduced_mean,
                    "tau_squared": reduced_tau,
                    "delta_from_full": reduced_mean - estimate,
                }
            )
    return {
        "model": "random_effects",
        "tau_method": tau_method,
        "interval_method": interval_method,
        "scale": scale,
        "estimate": estimate,
        "standard_error": standard_error,
        "conventional_standard_error": conventional_se,
        "confidence_interval_95": confidence_interval,
        "prediction_interval_95": prediction_interval,
        "tau_squared": tau2,
        "q": q,
        "q_df": df,
        "q_p_value": float(stats.chi2.sf(q, df)),
        "i_squared": max(0.0, (q - df) / q) if q > 0 else 0.0,
        "h_squared": q / df if df > 0 else None,
        "n_studies": len(effects),
        "study_ids": ids,
        "leave_one_out": influence,
        "limitations": [
            "Pooling assumes independent studies and compatible effect definitions",
            "Prediction intervals can be unstable with few studies",
            "Publication-bias diagnostics are descriptive and require enough studies",
        ],
    }


def funnel_asymmetry_egger(studies: list[dict[str, Any]]) -> dict[str, Any]:
    """Egger regression intercept as an exploratory small-study-effect diagnostic."""

    ids, scale, effects, variances = _inputs(studies)
    require(len(effects) >= 10, "Egger regression requires at least ten studies")
    se = np.sqrt(variances)
    precision = 1 / se
    standardized = effects / se
    design = np.column_stack([np.ones(len(effects)), precision])
    fit = np.linalg.lstsq(design, standardized, rcond=None)
    coefficients = fit[0]
    residual = standardized - design @ coefficients
    df = len(effects) - 2
    sigma2 = float(np.sum(residual**2) / df)
    covariance = sigma2 * np.linalg.inv(design.T @ design)
    intercept_se = math.sqrt(float(covariance[0, 0]))
    statistic = float(coefficients[0] / intercept_se)
    p_value = float(2 * stats.t.sf(abs(statistic), df=df))
    return {
        "method": "egger_regression",
        "scale": scale,
        "intercept": float(coefficients[0]),
        "standard_error": intercept_se,
        "t_statistic": statistic,
        "df": df,
        "p_value": p_value,
        "n_studies": len(ids),
        "warning": (
            "Egger regression is low-powered and can reflect heterogeneity rather than "
            "publication bias"
        ),
    }
