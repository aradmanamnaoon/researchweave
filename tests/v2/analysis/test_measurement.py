from pathlib import Path

import numpy as np
import pytest
from statsmodels.multivariate.factor import Factor
from statsmodels.stats.inter_rater import fleiss_kappa

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.measurement import (
    correlation_suitability,
    exploratory_factors,
    fleiss_agreement,
    icc_two_way_absolute,
)


@pytest.fixture
def correlated(tmp_path: Path):
    rng = np.random.default_rng(72)
    latent = rng.normal(size=(120, 2))
    matrix = latent @ np.array([[0.9, 0.3, 0.2, 0.6], [0.1, 0.8, 0.7, 0.2]])
    matrix += rng.normal(size=(120, 4)) * 0.3
    source = tmp_path / "items.csv"
    source.write_text(
        "a,b,c,d\n" + "".join(",".join(str(value) for value in row) + "\n" for row in matrix),
        encoding="utf-8",
    )
    return import_csv(source), matrix


def test_kmo_and_bartlett_valid(correlated):
    dataset, values = correlated
    result = correlation_suitability(dataset, ["a", "b", "c", "d"])
    corr = np.corrcoef(values, rowvar=False)
    chi = -(len(values) - 1 - (2 * 4 + 5) / 6) * np.linalg.slogdet(corr)[1]
    assert result["bartlett_chi_square"] == pytest.approx(chi)
    assert 0 <= result["kmo_overall"] <= 1
    assert result["n_complete"] == 120


def test_factor_unrotated_matches_reference_up_to_sign(correlated):
    data, values = correlated
    result = exploratory_factors(data, ["a", "b", "c", "d"], n_factors=2, rotate="none")
    expected = Factor(values, n_factor=2, method="pa").fit(maxiter=200)
    actual = np.asarray(list(result["loadings"].values()))
    for j in range(2):
        assert np.abs(actual[:, j]) == pytest.approx(np.abs(expected.loadings[:, j]))
    assert result["n_factors"] == 2
    assert np.isfinite(result["rmsr_offdiagonal"])
    with pytest.raises(AnalysisError, match="fewer"):
        exploratory_factors(data, ["a", "b", "c", "d"], n_factors=4)


def test_factor_varimax_preserves_reproduced_covariance_and_improves_simple_structure(correlated):
    """Independent rotation invariants: orthogonality preserves L L^T and uniqueness."""
    dataset, values = correlated
    columns = ["a", "b", "c", "d"]
    raw = exploratory_factors(dataset, columns, n_factors=2, rotate="none")
    rotated = exploratory_factors(dataset, columns, n_factors=2, rotate="varimax")
    initial = np.stack([raw["loadings"][column] for column in columns])
    final = np.stack([rotated["loadings"][column] for column in columns])
    initial_reproduction = initial @ initial.T
    final_reproduction = final @ final.T
    np.testing.assert_allclose(final_reproduction, initial_reproduction, rtol=1e-6, atol=1e-6)
    for index, column in enumerate(columns):
        assert rotated["communality"][column] == pytest.approx(
            float(final_reproduction[index, index]), abs=1e-10
        )
        assert rotated["uniqueness"][column] == pytest.approx(raw["uniqueness"][column])
    assert rotated["rmsr_offdiagonal"] == pytest.approx(raw["rmsr_offdiagonal"])

    # Varimax maximizes the dispersion of squared loadings within each column.
    def varimax_objective(loadings: np.ndarray) -> float:
        squared = loadings**2
        return float(np.sum(squared**2) - np.sum(np.sum(squared, axis=0) ** 2) / len(columns))

    assert varimax_objective(final) >= varimax_objective(initial) - 1e-8
    # Reconstruct an independently calculated Pearson correlation model.
    empirical = np.corrcoef(values, rowvar=False)
    predicted = final_reproduction + np.diag([rotated["uniqueness"][column] for column in columns])
    off_diagonal = empirical - predicted
    np.fill_diagonal(off_diagonal, 0)
    expected_rmsr = np.sqrt(np.sum(off_diagonal**2) / (len(columns) * (len(columns) - 1)))
    assert rotated["rmsr_offdiagonal"] == pytest.approx(expected_rmsr, abs=1e-10)


def test_suitability_independent_partial_correlation_oracle(correlated):
    dataset, values = correlated
    result = correlation_suitability(dataset, ["a", "b", "c", "d"])
    correlation = np.corrcoef(values, rowvar=False)
    precision = np.linalg.solve(correlation, np.eye(4))
    partial = -precision / np.sqrt(np.outer(np.diag(precision), np.diag(precision)))
    np.fill_diagonal(partial, 0)
    np.fill_diagonal(correlation, 0)
    r2 = correlation**2
    p2 = partial**2
    assert result["kmo_overall"] == pytest.approx(r2.sum() / (r2.sum() + p2.sum()))
    for i, column in enumerate(["a", "b", "c", "d"]):
        assert result["kmo_per_item"][column] == pytest.approx(
            r2[i].sum() / (r2[i].sum() + p2[i].sum())
        )


def test_factor_rejects_singular_and_underpowered_samples(tmp_path: Path):
    singular = tmp_path / "singular.csv"
    singular.write_text(
        "a,b,c,d\n" + "".join(f"{i},{i},{i * 2},{i * 3}\n" for i in range(40)),
        encoding="utf-8",
    )
    with pytest.raises(AnalysisError, match="positive definite"):
        exploratory_factors(import_csv(singular), ["a", "b", "c", "d"], n_factors=2)
    small = tmp_path / "small.csv"
    small.write_text(
        "a,b,c,d\n" + "".join(f"{i},{i * i},{i % 3},{i % 5}\n" for i in range(10)),
        encoding="utf-8",
    )
    with pytest.raises(AnalysisError, match="at least"):
        exploratory_factors(import_csv(small), ["a", "b", "c", "d"], n_factors=2)


def test_fleiss_and_icc_hand_formulas():
    counts = [[3, 0], [2, 1], [1, 2], [0, 3], [2, 1]]
    observed = fleiss_agreement(counts)
    assert observed["kappa"] == pytest.approx(fleiss_kappa(np.asarray(counts)))
    ratings = [[1, 1.2, 1.1], [2, 2.3, 2.2], [3, 3.2, 3.4], [4, 4.5, 4.2], [5, 5.2, 5.1]]
    agreement = icc_two_way_absolute(ratings)
    assert 0.8 < agreement["icc"] < 1
    assert agreement["n_raters"] == 3
    with pytest.raises(AnalysisError, match="same"):
        fleiss_agreement([[2, 0], [1, 2], [2, 0]])
