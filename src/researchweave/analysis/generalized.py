"""Generalized linear models with explicit outcome scales and convergence checks."""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np

from .errors import AnalysisError, require
from .models import Dataset, ScientificResult, finite_number, runtime_versions


def design_matrix(
    dataset: Dataset, outcome: str, predictors: list[str]
) -> tuple[np.ndarray, np.ndarray, int]:
    """Complete-case numeric matrix, with rank and degree-of-freedom guarantees."""
    require(
        bool(predictors) and len(set(predictors)) == len(predictors),
        "At least one distinct predictor is required",
    )
    require(
        outcome in dataset.columns and outcome not in predictors,
        "Outcome missing or duplicated among predictors",
    )
    require(all(column in dataset.columns for column in predictors), "Unknown predictor column")
    valid = [
        row
        for row in dataset.records
        if all(row[column] is not None for column in [outcome, *predictors])
    ]
    require(
        len(valid) > len(predictors) + 2, "Insufficient complete observations for requested model"
    )
    x = np.asarray(
        [
            [1.0, *[finite_number(row[column], name=column) for column in predictors]]
            for row in valid
        ],
        dtype=np.float64,
    )
    y = np.asarray([finite_number(row[outcome], name=outcome) for row in valid])
    require(np.linalg.matrix_rank(x) == x.shape[1], "Predictors are linearly dependent")
    return x, y, len(dataset.records) - len(valid)


def logistic_regression(
    dataset: Dataset, outcome: str, predictors: list[str], *, max_iterations: int = 200
) -> ScientificResult:
    """Binary logistic MLE; refuse perfect separation and non-convergence."""
    from statsmodels.discrete.discrete_model import Logit
    from statsmodels.tools.sm_exceptions import PerfectSeparationError, PerfectSeparationWarning

    require(10 <= max_iterations <= 2000, "Invalid iteration budget")
    x, y, excluded = design_matrix(dataset, outcome, predictors)
    require(
        set(y).issubset({0.0, 1.0}) and len(set(y)) == 2,
        "Binary outcome must contain both 0 and 1; no implicit recoding",
    )
    require(
        min(np.sum(y == 0), np.sum(y == 1)) >= 2,
        "At least two observations of each event class are required",
    )
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fitted = Logit(y, x).fit(disp=0, maxiter=max_iterations)
    except (PerfectSeparationError, np.linalg.LinAlgError, ValueError, OverflowError) as exc:
        raise AnalysisError(
            "INVALID_INPUT", "Logistic model could not be identified or fitted"
        ) from exc
    if any(issubclass(w.category, PerfectSeparationWarning) for w in caught):
        raise AnalysisError("INVALID_INPUT", "Perfect separation detected in logistic model")
    require(bool(fitted.mle_retvals.get("converged")), "Logistic fit did not converge")
    coefficients = np.asarray(fitted.params, dtype=float)
    require(bool(np.all(np.isfinite(coefficients))), "Model returned non-finite coefficients")
    confidence = fitted.conf_int()
    names = ["intercept", *predictors]
    probabilities = np.asarray(fitted.predict(x), dtype=float)
    require(
        bool(np.all((0 <= probabilities) & (probabilities <= 1))),
        "Invalid modeled probabilities",
        "INTEGRITY_FAILURE",
    )
    details: dict[str, Any] = {
        "coefficients": dict(zip(names, coefficients.tolist(), strict=True)),
        "odds_ratios": dict(zip(names, np.exp(coefficients).tolist(), strict=True)),
        "confidence_intervals": dict(zip(names, confidence.tolist(), strict=True)),
        "p_values": dict(zip(names, map(float, fitted.pvalues), strict=True)),
        "log_likelihood": float(fitted.llf),
        "aic": float(fitted.aic),
        "bic": float(fitted.bic),
        "predicted_probabilities": probabilities.tolist(),
        "event_count": int(np.sum(y)),
        "non_event_count": int(np.sum(1 - y)),
        "converged": True,
        "iterations": int(fitted.mle_retvals["iterations"]),
        "missing_policy": "complete_case",
    }
    return ScientificResult(
        "binary_logit",
        dataset.revision,
        len(dataset.records),
        len(y),
        excluded,
        details=details,
        assumptions=(
            "Observations independent unless modeled otherwise",
            "Logit-linearity and specification require assessment",
            "Prediction is not causal interpretation",
        ),
        warnings=tuple(
            str(w.message) for w in caught if not issubclass(w.category, PerfectSeparationWarning)
        ),
        versions=runtime_versions(),
    )


def poisson_regression(
    dataset: Dataset, outcome: str, predictors: list[str], *, offset: str | None = None
) -> ScientificResult:
    """Log-link Poisson GLM; detect nonintegral outcomes and overdispersion."""
    import statsmodels.api as sm

    x, y, excluded = design_matrix(dataset, outcome, predictors)
    require(
        bool(np.all(y >= 0)) and bool(np.all(np.floor(y) == y)),
        "Poisson outcome must be a nonnegative integer count",
    )
    require(bool(np.any(y > 0)), "All-zero counts do not identify a meaningful model")
    log_offset = None
    if offset is not None:
        require(
            offset in dataset.columns and offset != outcome and offset not in predictors,
            "Invalid exposure column",
        )
        columns = [outcome, *predictors, offset]
        complete = [row for row in dataset.records if all(row[col] is not None for col in columns)]
        require(
            len(complete) > len(predictors) + 2, "Insufficient cases after exposure missingness"
        )
        x = np.asarray([[1.0, *[finite_number(row[c]) for c in predictors]] for row in complete])
        y = np.asarray([finite_number(row[outcome]) for row in complete])
        exposure = np.asarray([finite_number(row[offset]) for row in complete])
        require(bool(np.all(exposure > 0)), "Exposures must be positive")
        require(np.linalg.matrix_rank(x) == x.shape[1], "Design matrix is singular")
        log_offset = np.log(exposure)
        excluded = len(dataset.records) - len(complete)
    try:
        fitted = sm.GLM(y, x, family=sm.families.Poisson(), offset=log_offset).fit(maxiter=200)
    except (np.linalg.LinAlgError, ValueError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", "Poisson GLM fitting failed") from exc
    require(bool(fitted.converged), "Poisson GLM failed to converge")
    require(bool(np.all(np.isfinite(fitted.params))), "Poisson coefficients non-finite")
    names = ["intercept", *predictors]
    dispersion = float(fitted.pearson_chi2 / fitted.df_resid) if fitted.df_resid else math.nan
    warnings_list = []
    if dispersion > 1.5:
        warnings_list.append("Pearson dispersion exceeds 1.5; consider overdispersion model")
    if bool(np.mean(y == 0) > np.mean(np.exp(-fitted.predict(x, offset=log_offset))) + 0.15):
        warnings_list.append("Possible excess zeros; zero-inflation is not modeled")
    details = {
        "coefficients": dict(zip(names, map(float, fitted.params), strict=True)),
        "rate_ratios": dict(zip(names, np.exp(fitted.params).tolist(), strict=True)),
        "confidence_intervals": dict(zip(names, fitted.conf_int().tolist(), strict=True)),
        "p_values": dict(zip(names, map(float, fitted.pvalues), strict=True)),
        "deviance": float(fitted.deviance),
        "aic": float(fitted.aic),
        "pearson_dispersion": dispersion,
        "exposure_column": offset,
        "converged": bool(fitted.converged),
        "missing_policy": "complete_case",
    }
    return ScientificResult(
        "poisson_glm",
        dataset.revision,
        len(dataset.records),
        len(y),
        excluded,
        details=details,
        warnings=tuple(warnings_list),
        assumptions=(
            "Poisson conditional mean/variance and independent units",
            "Exposure represented by a log offset when provided",
        ),
        versions=runtime_versions(),
    )
