import math

import pytest
from scipy import stats
from statsmodels.stats.power import TTestIndPower

from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.power import (
    confidence_interval_mean,
    one_sample_t_power,
    two_proportion_power,
    two_sample_t_power,
    two_sample_t_required,
)


def test_independent_sample_power_reference_and_rounded_size():
    expected = TTestIndPower().power(effect_size=0.5, nobs1=64, alpha=0.05, ratio=1)
    measured = two_sample_t_power(effect=0.5, n_group1=64)
    assert measured.power == pytest.approx(expected)
    required = two_sample_t_required(effect=0.5, target_power=0.8)
    assert required.n_group1 == math.ceil(
        TTestIndPower().solve_power(effect_size=0.5, alpha=0.05, power=0.8, ratio=1)
    )
    assert required.power >= 0.8
    assert required.n_group1 == required.n_group2


def test_paired_power_and_proportion_constraints():
    output = one_sample_t_power(effect=0.5, n=32)
    assert 0 < output.power < 1
    proportions = two_proportion_power(p1=0.3, p2=0.5, n_group1=80)
    assert proportions.family == "two_proportion_normal_approximation"
    assert 0 < proportions.power < 1
    with pytest.raises(AnalysisError, match="Distinct"):
        two_proportion_power(p1=0.5, p2=0.5, n_group1=100)
    with pytest.raises(AnalysisError, match="Positive"):
        two_sample_t_required(effect=0)


def test_mean_interval_manual_t_oracle():
    values = [2, 4, 6, 8, 10]
    measured = confidence_interval_mean(values)
    radius = stats.t.ppf(0.975, 4) * math.sqrt(10 / 5)
    assert measured["mean"] == 6
    assert measured["sd_sample"] == pytest.approx(math.sqrt(10))
    assert measured["lower"] == pytest.approx(6 - radius)
    assert measured["upper"] == pytest.approx(6 + radius)
    with pytest.raises(AnalysisError, match="Zero-variance"):
        confidence_interval_mean([1, 1, 1])
