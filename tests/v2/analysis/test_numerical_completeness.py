from pathlib import Path

import numpy as np
import pytest
from scipy import stats
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

from researchweave.analysis.datasets import import_csv, set_variable
from researchweave.analysis.inference import contingency
from researchweave.analysis.power import mean_precision_required, two_proportion_required
from researchweave.analysis.statistics import correlation, describe, frequency_table


def _data(tmp_path: Path):
    path = tmp_path / "data.csv"
    path.write_text(
        "group,x,y,category\nA,1,1.5,yes\nA,2,2.2,no\nA,3,2.8,yes\n"
        "B,4,4.1,no\nB,5,5.2,yes\nB,6,5.8,yes\n",
        encoding="utf-8",
    )
    return import_csv(path)


def test_describe_uncertainty_and_shape_match_scipy(tmp_path: Path):
    dataset = _data(tmp_path)
    result = describe(dataset, "x")
    values = np.arange(1, 7, dtype=float)
    sem = stats.sem(values)
    cutoff = stats.t.ppf(0.975, len(values) - 1)
    assert result["standard_error_mean"] == pytest.approx(sem)
    assert result["mean_confidence_interval_95"] == pytest.approx(
        [values.mean() - cutoff * sem, values.mean() + cutoff * sem]
    )
    assert result["skewness_bias_corrected"] == pytest.approx(stats.skew(values, bias=False))
    assert result["excess_kurtosis_bias_corrected"] == pytest.approx(
        stats.kurtosis(values, fisher=True, bias=False)
    )


def test_frequency_table_respects_category_order_and_labels(tmp_path: Path):
    dataset = _data(tmp_path)
    dataset = set_variable(
        dataset,
        "category",
        category_order=("yes", "no"),
        value_labels={"yes": "Yes", "no": "No"},
        scale="nominal",
    )
    result = frequency_table(dataset, "category")
    assert [entry["value"] for entry in result["levels"]] == ["yes", "no"]
    assert result["levels"][0]["count"] == 4
    assert result["levels"][0]["label"] == "Yes"
    assert sum(entry["percent_valid"] for entry in result["levels"]) == pytest.approx(100)


def test_contingency_percentages_effect_and_fisher_ci(tmp_path: Path):
    dataset = _data(tmp_path)
    result = contingency(dataset, "group", "category")
    counts = np.asarray(result["counts"])
    assert np.asarray(result["row_percent"]).sum(axis=1) == pytest.approx([100, 100])
    assert np.asarray(result["column_percent"]).sum(axis=0) == pytest.approx([100, 100])
    assert np.asarray(result["total_percent"]).sum() == pytest.approx(100)
    expected_v = np.sqrt(result["chi_squared"] / counts.sum())
    assert result["cramers_v"] == pytest.approx(expected_v)
    assert result["fisher_2x2"]["odds_ratio_ci_95"][0] > 0


def test_pearson_fisher_interval_matches_manual(tmp_path: Path):
    dataset = _data(tmp_path)
    result = correlation(dataset, "x", "y", "pearson").as_json()
    r = float(result["estimate"])
    z = np.arctanh(r)
    radius = stats.norm.ppf(0.975) / np.sqrt(6 - 3)
    expected = np.tanh([z - radius, z + radius])
    assert result["details"]["fisher_z_confidence_interval_95"] == pytest.approx(expected)


def test_proportion_required_n_and_precision_match_reference():
    result = two_proportion_required(p1=0.4, p2=0.6, target_power=0.8, alpha=0.05)
    effect = abs(proportion_effectsize(0.4, 0.6))
    continuous = NormalIndPower().solve_power(
        effect_size=effect, power=0.8, alpha=0.05, ratio=1, alternative="two-sided"
    )
    assert result.n_group1 == np.ceil(continuous)
    assert result.power >= 0.8
    precision = mean_precision_required(assumed_sd=10, margin=2, confidence=0.95)
    expected_n = np.ceil((stats.norm.ppf(0.975) * 10 / 2) ** 2)
    assert precision["required_n"] == expected_n
