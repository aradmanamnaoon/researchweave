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
