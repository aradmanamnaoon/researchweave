from pathlib import Path

import numpy as np
import pytest

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.multivariate import (
    hierarchical_clusters,
    kmeans_clusters,
    principal_components,
)


@pytest.fixture
def cloud(tmp_path: Path):
    path = tmp_path / "coordinates.csv"
    path.write_text("x,y\n0,0\n0,1\n1,0\n1,1\n10,10\n10,11\n11,10\n11,11\n", encoding="utf-8")
    return import_csv(path)


def test_pca_covariance_oracle_and_reconstruction(cloud):
    result = principal_components(cloud, ["x", "y"], n_components=2, standardize=False)
    matrix = np.asarray([[0, 0], [0, 1], [1, 0], [1, 1], [10, 10], [10, 11], [11, 10], [11, 11]])
    eigenvalues = np.linalg.eigvalsh(np.cov(matrix, rowvar=False))[::-1]
    observed = [c["eigenvalue"] for c in result["components"]]
    assert observed == pytest.approx(eigenvalues)
    assert sum(c["explained_variance_ratio"] for c in result["components"]) == pytest.approx(1)
    assert result["rmse_reconstruction"] < 1e-10
    assert result["n_used"] == 8


def test_kmeans_seeded_cluster_contract(cloud):
    first = kmeans_clusters(cloud, ["x", "y"], k=2, seed=42, n_init=4)
    second = kmeans_clusters(cloud, ["x", "y"], k=2, seed=42, n_init=4)
    assert first == second
    assert sorted(first["group_sizes"]) == [4, 4]
    assert np.allclose(first["centers_original_units"], [[0.5, 0.5], [10.5, 10.5]])
    assert first["inertia_standardized"] >= 0


def test_hierarchical_and_degenerate_errors(cloud, tmp_path):
    result = hierarchical_clusters(cloud, ["x", "y"], k=2)
    assert sorted(result["group_sizes"]) == [4, 4]
    with pytest.raises(AnalysisError, match="count"):
        kmeans_clusters(cloud, ["x", "y"], k=20)
    constant = tmp_path / "constant.csv"
    constant.write_text("x,y\n1,3\n1,4\n1,5\n1,6\n", encoding="utf-8")
    frame = import_csv(constant)
    with pytest.raises(AnalysisError, match="constant"):
        principal_components(frame, ["x", "y"])
