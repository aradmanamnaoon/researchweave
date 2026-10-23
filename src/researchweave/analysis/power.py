"""Explicit frequentist power and required-size estimators for planning.

Power is conditional on test family, assumed effect and error model; this module
never certifies a study's adequacy or substitutes for design-specific planning.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from scipy import stats
from statsmodels.stats.power import NormalIndPower, TTestIndPower, TTestPower

from .errors import AnalysisError, require
from .models import finite_number


@dataclass(frozen=True)
class PowerEstimate:
    family: str
    alternative: str
    alpha: float
    assumed_effect: float
    power: float
    n_group1: float
    n_group2: float | None
    group_ratio: float | None
    interpretation: str

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def _parameters(alpha: float, effect: float, alternative: str) -> tuple[float, float]:
    alpha = finite_number(alpha, name="alpha")
    effect = finite_number(effect, name="effect")
    require(0 < alpha < 1, "alpha must lie strictly between zero and one")
    require(effect > 0, "Positive absolute standardized effect required")
    require(
        alternative in ("two-sided", "larger", "smaller"), "Alternative must be explicitly declared"
    )
    return alpha, effect


def two_sample_t_power(
    *,
    effect: float,
    n_group1: int,
    ratio: float = 1,
    alpha: float = 0.05,
    alternative: str = "two-sided",
) -> PowerEstimate:
    """Equal-variance independent two-sample t power, ratio=n2/n1."""
    alpha, effect = _parameters(alpha, effect, alternative)
    ratio = finite_number(ratio, name="allocation ratio")
    require(ratio > 0, "Allocation ratio must be positive")
    require(
        isinstance(n_group1, int) and n_group1 >= 2 and n_group1 * ratio >= 2,
        "Each group must have at least two observations",
    )
    require(n_group1 <= 10_000_000, "Sample size budget exceeded", "RESOURCE_LIMIT")
    power = float(
        TTestIndPower().power(
            effect_size=effect, nobs1=n_group1, alpha=alpha, ratio=ratio, alternative=alternative
        )
    )
    require(
        math.isfinite(power) and 0 <= power <= 1,
        "Numerical power failed to converge",
        "INTERNAL_ERROR",
    )
    return PowerEstimate(
        "independent_equal_variance_t",
        alternative,
        alpha,
        effect,
        power,
        float(n_group1),
        n_group1 * ratio,
        ratio,
        "Conditional on equal variances, normal errors and independent sampling",
    )


def two_sample_t_required(
    *,
    effect: float,
    target_power: float = 0.8,
    ratio: float = 1,
    alpha: float = 0.05,
    alternative: str = "two-sided",
) -> PowerEstimate:
    """Solve for n1, round up, and recompute actual achievable power."""
    alpha, effect = _parameters(alpha, effect, alternative)
    target_power = finite_number(target_power, name="target power")
    ratio = finite_number(ratio, name="allocation ratio")
    require(
        0 < target_power < 1 and ratio > 0, "Power must be in (0,1) and allocation ratio positive"
    )
    try:
        continuous = float(
            TTestIndPower().solve_power(
                effect_size=effect,
                alpha=alpha,
                power=target_power,
                ratio=ratio,
                alternative=alternative,
            )
        )
    except (ValueError, OverflowError) as exc:
        raise AnalysisError("INVALID_INPUT", "Cannot solve t-test sample size") from exc
    require(
        math.isfinite(continuous) and continuous <= 10_000_000,
        "Required sample exceeds planning budget",
        "RESOURCE_LIMIT",
    )
    n1 = max(2, math.ceil(continuous))
    n2 = max(2, math.ceil(n1 * ratio))
    power = float(
        TTestIndPower().power(
            effect_size=effect, nobs1=n1, alpha=alpha, ratio=n2 / n1, alternative=alternative
        )
    )
    require(
        power + 1e-10 >= target_power, "Rounded allocation failed target power", "INTEGRITY_FAILURE"
    )
    return PowerEstimate(
        "independent_equal_variance_t",
        alternative,
        alpha,
        effect,
        power,
        float(n1),
        float(n2),
        n2 / n1,
        "Prospective planning only; effect assumption must be justified",
    )


def one_sample_t_power(
    *, effect: float, n: int, alpha: float = 0.05, alternative: str = "two-sided"
) -> PowerEstimate:
    alpha, effect = _parameters(alpha, effect, alternative)
    require(isinstance(n, int) and 2 <= n <= 10_000_000, "Sample size outside range")
    result = float(
        TTestPower().power(effect_size=effect, nobs=n, alpha=alpha, alternative=alternative)
    )
    require(math.isfinite(result), "Numerical power undefined")
    return PowerEstimate(
        "one_sample_or_paired_t",
        alternative,
        alpha,
        effect,
        result,
        float(n),
        None,
        None,
        "Paired effect assumes standard deviation of within-pair differences",
    )


def two_proportion_power(
    *, p1: float, p2: float, n_group1: int, ratio: float = 1, alpha: float = 0.05
) -> PowerEstimate:
    """Normal approximation to unpooled alternative proportion test power."""
    from statsmodels.stats.proportion import proportion_effectsize

    require(
        0 < alpha < 1 and isinstance(n_group1, int) and n_group1 >= 2,
        "Invalid sample size or alpha",
    )
    p1 = finite_number(p1, name="p1")
    p2 = finite_number(p2, name="p2")
    ratio = finite_number(ratio, name="ratio")
    require(
        0 <= p1 <= 1 and 0 <= p2 <= 1 and p1 != p2, "Distinct proportions in [0,1] are required"
    )
    require(ratio > 0 and n_group1 * ratio >= 2, "Invalid allocation ratio")
    effect = abs(float(proportion_effectsize(p1, p2)))
    output = float(
        NormalIndPower().power(
            effect_size=effect, nobs1=n_group1, alpha=alpha, ratio=ratio, alternative="two-sided"
        )
    )
    return PowerEstimate(
        "two_proportion_normal_approximation",
        "two-sided",
        alpha,
        effect,
        output,
        float(n_group1),
        n_group1 * ratio,
        ratio,
        "Approximate power; sparse or rare events may require exact simulation",
    )


def confidence_interval_mean(values: list[float], *, alpha: float = 0.05) -> dict[str, float | int]:
    """Two-sided Student t interval from raw IID numeric observations."""
    require(0 < alpha < 1, "Alpha outside range")
    samples = [finite_number(value) for value in values]
    require(len(samples) >= 2, "At least two numeric observations required")
    n = len(samples)
    mean = math.fsum(samples) / n
    variance = math.fsum((v - mean) ** 2 for v in samples) / (n - 1)
    require(variance > 0, "Zero-variance interval needs an explicit degenerate policy")
    radius = float(stats.t.ppf(1 - alpha / 2, n - 1)) * math.sqrt(variance / n)
    return {
        "n": n,
        "mean": mean,
        "sd_sample": math.sqrt(variance),
        "confidence": 1 - alpha,
        "lower": mean - radius,
        "upper": mean + radius,
        "df": n - 1,
    }
