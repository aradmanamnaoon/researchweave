"""Reusable effect-size estimators with explicit designs and denominators."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import stats

from .errors import require
from .models import finite_number


def independent_standardized_mean_difference(
    first: list[float], second: list[float]
) -> dict[str, Any]:
    """Cohen's d and small-sample corrected Hedges' g for independent groups."""

    x = np.asarray([finite_number(value) for value in first], dtype=float)
    y = np.asarray([finite_number(value) for value in second], dtype=float)
    require(len(x) >= 2 and len(y) >= 2, "Each group needs at least two observations")
    vx = float(np.var(x, ddof=1))
    vy = float(np.var(y, ddof=1))
    df = len(x) + len(y) - 2
    pooled = math.sqrt(((len(x) - 1) * vx + (len(y) - 1) * vy) / df)
    require(pooled > 0, "Pooled standard deviation is zero")
    d = float((np.mean(x) - np.mean(y)) / pooled)
    correction = 1 - 3 / (4 * df - 1) if df > 1 else 1.0
    g = correction * d
    # Hedges & Olkin large-sample variance; useful for meta-analysis inputs.
    variance_g = (len(x) + len(y)) / (len(x) * len(y)) + g**2 / (2 * df)
    return {
        "cohen_d": d,
        "hedges_g": g,
        "small_sample_correction": correction,
        "variance_hedges_g": float(variance_g),
        "standard_error_hedges_g": math.sqrt(variance_g),
        "n_first": len(x),
        "n_second": len(y),
        "df": df,
        "orientation": "first minus second",
    }


def paired_standardized_mean_difference(first: list[float], second: list[float]) -> dict[str, Any]:
    """Paired Cohen's dz using the SD of within-pair differences."""

    require(len(first) == len(second) and len(first) >= 2, "Paired inputs must align")
    difference = np.asarray(
        [finite_number(a) - finite_number(b) for a, b in zip(first, second, strict=True)],
        dtype=float,
    )
    sd = float(np.std(difference, ddof=1))
    require(sd > 0, "Paired differences have zero variance")
    dz = float(np.mean(difference) / sd)
    return {
        "cohen_dz": dz,
        "mean_difference": float(np.mean(difference)),
        "sd_difference": sd,
        "n_pairs": len(difference),
        "orientation": "first minus second",
    }


def rank_biserial_from_mann_whitney(
    statistic_u: float, n_first: int, n_second: int
) -> dict[str, Any]:
    """Rank-biserial effect oriented to the first group."""

    u = finite_number(statistic_u, name="Mann-Whitney U")
    require(n_first >= 1 and n_second >= 1, "Positive group sizes required")
    maximum = n_first * n_second
    require(0 <= u <= maximum, "Mann-Whitney U outside its possible range")
    return {
        "rank_biserial": 2 * u / maximum - 1,
        "u": u,
        "n_first": n_first,
        "n_second": n_second,
        "orientation": "positive values favor first group",
    }


def anova_effect_sizes(
    *,
    ss_effect: float,
    ss_error: float,
    df_effect: float,
    df_error: float,
    ss_total: float | None = None,
) -> dict[str, float]:
    """Eta-squared, partial eta-squared and omega-squared for an ANOVA effect."""

    effect = finite_number(ss_effect, name="effect sum of squares")
    error = finite_number(ss_error, name="error sum of squares")
    df_e = finite_number(df_effect, name="effect degrees of freedom")
    df_r = finite_number(df_error, name="error degrees of freedom")
    require(effect >= 0 and error >= 0 and df_e > 0 and df_r > 0, "Invalid ANOVA components")
    total = (
        effect + error if ss_total is None else finite_number(ss_total, name="total sum of squares")
    )
    require(total > 0 and total + 1e-12 >= effect + error, "Invalid total sum of squares")
    mse = error / df_r
    eta = effect / total
    partial_eta = effect / (effect + error) if effect + error > 0 else 0.0
    omega = max(0.0, (effect - df_e * mse) / (total + mse))
    return {
        "eta_squared": eta,
        "partial_eta_squared": partial_eta,
        "omega_squared": omega,
    }


def correlation_effect(r: float, *, n: int) -> dict[str, float | int]:
    """Correlation effect with Fisher-z confidence interval."""

    value = finite_number(r, name="correlation")
    require(-1 < value < 1, "Fisher interval requires correlation strictly inside (-1,1)")
    require(n >= 4, "Fisher interval requires at least four observations")
    z = math.atanh(value)
    se = 1 / math.sqrt(n - 3)
    cutoff = float(stats.norm.ppf(0.975))
    return {
        "r": value,
        "r_squared": value**2,
        "fisher_z": z,
        "ci_lower": math.tanh(z - cutoff * se),
        "ci_upper": math.tanh(z + cutoff * se),
        "n": n,
    }
