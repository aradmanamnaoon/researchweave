"""Strictly chronological exploratory time series without future leakage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from scipy import stats

from .errors import AnalysisError, require
from .models import Dataset, finite_number


@dataclass(frozen=True)
class Chronology:
    timestamps: tuple[str, ...]
    values: np.ndarray
    interval_seconds: float
    n_total: int
    n_used: int
    n_excluded: int


def parse_chronology(
    dataset: Dataset, time_column: str, value_column: str, *, allow_irregular: bool = False
) -> Chronology:
    """Require timezone-aware ISO-8601 timestamps and unique strictly rising instants."""
    require(
        time_column in dataset.columns and value_column in dataset.columns,
        "Unknown timestamp/value column",
    )
    require(time_column != value_column, "Timestamp and outcome cannot be the same variable")
    observed: list[tuple[datetime, float, str]] = []
    for row in dataset.records:
        if row[time_column] is None or row[value_column] is None:
            continue
        raw = str(row[time_column])
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AnalysisError("INVALID_INPUT", "Timestamp is not an ISO-8601 datetime") from exc
        require(
            value.tzinfo is not None and value.utcoffset() is not None,
            "Timestamp must specify timezone offset",
        )
        observed.append((value, finite_number(row[value_column], name=value_column), raw))
    require(len(observed) >= 4, "At least four complete chronological observations required")
    # Preserve original chronological row order; silently sorting would hide panel duplication.
    differences = [
        (observed[i + 1][0] - observed[i][0]).total_seconds() for i in range(len(observed) - 1)
    ]
    require(
        all(value > 0 for value in differences),
        "Time observations must be unique and sorted in strictly ascending UTC order",
    )
    interval = float(np.median(differences))
    if not allow_irregular:
        require(
            all(abs(delta - interval) <= max(0.001, interval * 1e-8) for delta in differences),
            "Irregular spacing; declare appropriate model or resolve missing periods",
        )
    return Chronology(
        tuple(row[2] for row in observed),
        np.asarray([row[1] for row in observed], dtype=float),
        interval,
        len(dataset.records),
        len(observed),
        len(dataset.records) - len(observed),
    )


def causal_features(
    chronology: Chronology, *, lags: list[int], rolling_window: int | None = None
) -> dict[str, Any]:
    """Predictors use only preceding observations; never target or later observations."""
    require(bool(lags) and len(set(lags)) == len(lags), "Distinct lag values required")
    require(
        all(isinstance(lag, int) and 1 <= lag <= 10000 for lag in lags),
        "Lags must be positive integers",
    )
    if rolling_window is not None:
        require(2 <= rolling_window <= 10000, "Rolling window must be 2..10000")
    prior = max([*lags, rolling_window or 0])
    require(prior < len(chronology.values), "No observations remain after lagging")
    rows = []
    for i in range(prior, len(chronology.values)):
        row: dict[str, Any] = {
            "timestamp": chronology.timestamps[i],
            "target": float(chronology.values[i]),
        }
        for lag in sorted(lags):
            row[f"lag_{lag}"] = float(chronology.values[i - lag])
        if rolling_window is not None:
            row[f"rolling_mean_{rolling_window}"] = float(
                np.mean(chronology.values[i - rolling_window : i])
            )
        rows.append(row)
    return {
        "rows": rows,
        "n_total": chronology.n_total,
        "n_chronological": chronology.n_used,
        "n_excluded_initial": chronology.n_excluded,
        "n_lagged": prior,
        "n_features": len(rows),
        "assumptions": [
            "Past-only rolling window; no future observations used",
            "Regular spacing reviewed during import",
        ],
    }


def autocorrelation(chronology: Chronology, *, max_lag: int) -> dict[str, Any]:
    """Centered sample autocorrelation with an explicit denominator."""
    require(
        1 <= max_lag <= min(1000, len(chronology.values) - 2), "Autocorrelation lag outside range"
    )
    values = chronology.values
    centered = values - np.mean(values)
    denominator = float(np.dot(centered, centered))
    require(denominator > 0, "Autocorrelation undefined for constant series")
    corr = [float(np.dot(centered[:-k], centered[k:]) / denominator) for k in range(1, max_lag + 1)]
    return {
        "lags": list(range(1, max_lag + 1)),
        "autocorrelation": corr,
        "definition": "biased sample ACF with full-sample variance denominator",
        "n": len(values),
        "interval_seconds": chronology.interval_seconds,
    }


def adf_stationarity(
    chronology: Chronology, *, regression: str = "c", autolag: str = "AIC"
) -> dict[str, Any]:
    """ADF unit-root diagnostic; reject small and degenerate series."""
    from statsmodels.tsa.stattools import adfuller

    require(regression in ("c", "ct", "n"), "Unsupported deterministic trend")
    require(autolag in ("AIC", "BIC"), "Unsupported lag criterion")
    values = chronology.values
    require(len(values) >= 12, "ADF requires at least twelve regular observations")
    require(np.ptp(values) > 0, "ADF undefined for constant series")
    try:
        result = adfuller(values, regression=regression, autolag=autolag, result_object=False)
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise AnalysisError("INVALID_INPUT", "ADF estimation failed on this sample") from exc
    return {
        "statistic": float(result[0]),
        "p_value": float(result[1]),
        "used_lags": int(result[2]),
        "n_observations": int(result[3]),
        "critical_values": {str(k): float(v) for k, v in result[4].items()},
        "autolag": autolag,
        "regression": regression,
        "null_hypothesis": "Unit root under specified deterministic components",
        "limitation": "A failure to reject does not establish nonstationarity",
    }


def trend_slope(chronology: Chronology) -> dict[str, Any]:
    """Exploratory linear trend per period, without assuming independent residuals."""
    periods = np.arange(len(chronology.values), dtype=float)
    slope = stats.linregress(periods, chronology.values)
    return {
        "slope_per_observation": float(slope.slope),
        "intercept": float(slope.intercept),
        "r_squared": float(slope.rvalue**2),
        "naive_p_value": float(slope.pvalue),
        "n_used": len(periods),
        "interval_seconds": chronology.interval_seconds,
        "warning": (
            "Naive linear-regression p-value ignores serial correlation; "
            "an appropriate error model is required for inference"
        ),
    }


def ljung_box(chronology: Chronology, *, lags: list[int]) -> dict[str, Any]:
    """Ljung-Box serial-correlation diagnostic for declared positive lags."""

    from statsmodels.stats.diagnostic import acorr_ljungbox

    require(bool(lags) and len(set(lags)) == len(lags), "Distinct Ljung-Box lags required")
    require(
        all(isinstance(lag, int) and 1 <= lag < len(chronology.values) for lag in lags),
        "Invalid Ljung-Box lag",
    )
    result = acorr_ljungbox(chronology.values, lags=sorted(lags), return_df=True)
    return {
        "lags": [int(value) for value in result.index],
        "statistics": [float(value) for value in result["lb_stat"]],
        "p_values": [float(value) for value in result["lb_pvalue"]],
        "null_hypothesis": "No autocorrelation through each declared lag",
        "n": len(chronology.values),
    }


def seasonal_decomposition(chronology: Chronology, *, period: int) -> dict[str, Any]:
    """Classical additive seasonal decomposition for regular series."""

    from statsmodels.tsa.seasonal import seasonal_decompose

    require(
        2 <= period <= len(chronology.values) // 2, "Seasonal period requires at least two cycles"
    )
    try:
        fitted = seasonal_decompose(
            chronology.values,
            model="additive",
            period=period,
            extrapolate_trend="period",
        )
    except ValueError as exc:
        raise AnalysisError("INVALID_INPUT", "Seasonal decomposition failed") from exc
    return {
        "method": "classical_additive_decomposition",
        "period": period,
        "observed": chronology.values.tolist(),
        "trend": np.asarray(fitted.trend, dtype=float).tolist(),
        "seasonal": np.asarray(fitted.seasonal, dtype=float).tolist(),
        "residual": np.asarray(fitted.resid, dtype=float).tolist(),
        "n": len(chronology.values),
        "interval_seconds": chronology.interval_seconds,
        "limitation": (
            "Classical decomposition assumes a fixed seasonal pattern and regular spacing"
        ),
    }


def arima_forecast(
    chronology: Chronology,
    *,
    order: tuple[int, int, int],
    horizon: int,
    seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0),
    validation_horizon: int = 0,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """ARIMA/SARIMA forecast with optional chronological holdout evaluation."""

    from statsmodels.tsa.statespace.sarimax import SARIMAX

    require(
        len(order) == 3 and all(isinstance(value, int) and value >= 0 for value in order),
        "Invalid ARIMA order",
    )
    require(
        len(seasonal_order) == 4
        and all(isinstance(value, int) and value >= 0 for value in seasonal_order),
        "Invalid seasonal ARIMA order",
    )
    require(1 <= horizon <= 1000, "Forecast horizon outside supported range")
    require(0 <= validation_horizon < len(chronology.values) - 5, "Invalid validation horizon")
    require(0.5 <= confidence < 1, "Forecast confidence must be in [0.5,1)")
    values = chronology.values
    require(
        len(values) >= max(12, sum(order) + sum(seasonal_order[:3]) + 6),
        "Series too short for declared ARIMA order",
    )

    def fit(data: np.ndarray):
        try:
            result = SARIMAX(
                data,
                order=order,
                seasonal_order=seasonal_order,
                trend="c" if order[1] == 0 else "n",
                enforce_stationarity=True,
                enforce_invertibility=True,
            ).fit(disp=False, maxiter=300)
        except (ValueError, np.linalg.LinAlgError) as exc:
            raise AnalysisError("INVALID_INPUT", "ARIMA model could not be estimated") from exc
        require(
            bool(result.mle_retvals.get("converged", False)),
            "ARIMA fit did not converge",
            "CONVERGENCE_FAILED",
        )
        return result

    validation: dict[str, Any] | None = None
    if validation_horizon:
        train = values[:-validation_horizon]
        held_out = values[-validation_horizon:]
        trained = fit(train)
        predicted = np.asarray(trained.forecast(validation_horizon), dtype=float)
        errors = held_out - predicted
        validation = {
            "strategy": "chronological_tail_holdout",
            "training_n": len(train),
            "holdout_n": validation_horizon,
            "actual": held_out.tolist(),
            "predicted": predicted.tolist(),
            "mae": float(np.mean(np.abs(errors))),
            "rmse": float(np.sqrt(np.mean(errors**2))),
            "no_future_leakage": True,
        }
    final = fit(values)
    forecast = final.get_forecast(horizon)
    mean = np.asarray(forecast.predicted_mean, dtype=float)
    alpha = 1 - confidence
    interval = np.asarray(forecast.conf_int(alpha=alpha), dtype=float)
    return {
        "method": "sarimax",
        "order": list(order),
        "seasonal_order": list(seasonal_order),
        "horizon": horizon,
        "confidence": confidence,
        "forecast": mean.tolist(),
        "confidence_interval": interval.tolist(),
        "aic": float(final.aic),
        "bic": float(final.bic),
        "converged": bool(final.mle_retvals.get("converged", False)),
        "validation": validation,
        "n_fit": len(values),
        "interval_seconds": chronology.interval_seconds,
        "limitations": [
            "Order is analyst-declared; automatic order search is intentionally not performed",
            "Prediction intervals are conditional on the fitted ARIMA specification",
        ],
    }
