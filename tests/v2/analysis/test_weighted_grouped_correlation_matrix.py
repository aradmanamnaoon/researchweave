from pathlib import Path

import numpy as np
import pytest

from researchweave.analysis.data_ops import analytic_weighted_mean
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.statistics import correlation_matrix, grouped_describe


def _dataset(tmp_path: Path):
    path = tmp_path / "weighted.csv"
    path.write_text(
        "group,x,y,z,w\nA,1,2,1,1\nA,2,4,2,2\nA,3,5,4,1\nB,4,8,8,3\nB,5,10,16,2\nB,6,12,32,1\n",
        encoding="utf-8",
    )
    return import_csv(path)


def test_analytic_weighted_mean_effective_n_and_variance(tmp_path: Path):
    dataset = _dataset(tmp_path)
    result = analytic_weighted_mean(dataset, "x", "w")
    values = np.array([1, 2, 3, 4, 5, 6], dtype=float)
    weights = np.array([1, 2, 1, 3, 2, 1], dtype=float)
    expected_mean = np.average(values, weights=weights)
    expected_effective = weights.sum() ** 2 / np.square(weights).sum()
    denominator = weights.sum() - np.square(weights).sum() / weights.sum()
    expected_variance = np.sum(weights * (values - expected_mean) ** 2) / denominator
    assert result["mean"] == pytest.approx(expected_mean)
    assert result["kish_effective_n"] == pytest.approx(expected_effective)
    assert result["weighted_variance"] == pytest.approx(expected_variance)
    assert result["weight_semantics"] == "analytic_reliability"


def test_grouped_describe_reconciles_group_counts(tmp_path: Path):
    dataset = _dataset(tmp_path)
    result = grouped_describe(dataset, "x", "group")
    assert [row["level"] for row in result["groups"]] == ["A", "B"]
    assert [row["n_valid"] for row in result["groups"]] == [3, 3]
    assert result["groups"][0]["mean"] == pytest.approx(2)
    assert result["groups"][1]["mean"] == pytest.approx(5)


def test_correlation_matrix_pairwise_n_adjustment_and_symmetry(tmp_path: Path):
    dataset = _dataset(tmp_path)
    result = correlation_matrix(dataset, ["x", "y", "z"], method="pearson", adjustment="holm")
    matrix = np.asarray(result["correlation"], dtype=float)
    assert np.allclose(matrix, matrix.T)
    assert np.allclose(np.diag(matrix), 1)
    assert np.asarray(result["pairwise_n"]).tolist() == [[6, 6, 6], [6, 6, 6], [6, 6, 6]]
    assert len(result["tests"]) == 3
    assert all(0 <= row["adjusted_p_value"] <= 1 for row in result["tests"])
    assert result["family_definition"].startswith("all unique pairwise")


def test_csv_grouping_separator_normalizes_locale_numeric_string(tmp_path: Path):
    path = tmp_path / "locale.csv"
    path.write_text("value;label\n1.234,50;A\n12,75;B\n", encoding="utf-8")
    dataset = import_csv(path, delimiter=";", decimal=",", grouping=".")
    assert [row["value"] for row in dataset.records] == ["1234.50", "12.75"]
    assert dataset.operation["grouping"] == "."
