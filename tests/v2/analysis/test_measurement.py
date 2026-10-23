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
