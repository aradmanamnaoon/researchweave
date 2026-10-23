"""PCA, deterministic k-means, hierarchical clusters and matrix validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.cluster import hierarchy
from scipy.spatial.distance import cdist

from .errors import AnalysisError, require
from .models import Dataset, finite_number


@dataclass(frozen=True)
class MatrixSample:
    columns: tuple[str, ...]
    matrix: np.ndarray
    n_total: int
    n_excluded: int
    source_revision: str


def extract_numeric_matrix(dataset: Dataset, columns: list[str]) -> MatrixSample:
    """Extract complete-case rows in source order without coercing missing sentinels."""
    require(
        len(columns) >= 2 and len(set(columns)) == len(columns),
        "At least two distinct numeric columns required",
    )
    require(all(column in dataset.columns for column in columns), "Unknown matrix variable")
    require(
        len(columns) <= 1000 and len(dataset.records) * len(columns) <= 5_000_000,
        "Numeric matrix exceeds resource budget",
        "RESOURCE_LIMIT",
    )
    complete = [
        row for row in dataset.records if all(row[column] is not None for column in columns)
    ]
    require(len(complete) >= 3, "At least three complete observations required")
    array = np.asarray(
        [[finite_number(row[column], name=column) for column in columns] for row in complete],
        dtype=np.float64,
    )
    require(bool(np.all(np.isfinite(array))), "Non-finite matrix value")
    return MatrixSample(
        tuple(columns),
        array,
        len(dataset.records),
        len(dataset.records) - len(complete),
        dataset.revision,
    )


def principal_components(
    dataset: Dataset, columns: list[str], *, n_components: int = 2, standardize: bool = True
) -> dict[str, Any]:
    """SVD PCA with deterministic component sign and sample variance denominator."""
    sample = extract_numeric_matrix(dataset, columns)
    values = sample.matrix
    n, p = values.shape
    require(1 <= n_components <= min(n - 1, p), "Invalid component count")
    means = values.mean(axis=0)
    centered = values - means
    scales = np.std(centered, axis=0, ddof=1) if standardize else np.ones(p)
    require(bool(np.all(scales > 0)), "Cannot apply PCA to constant-valued columns")
    normalized = centered / scales
    u, singular, vt = np.linalg.svd(normalized, full_matrices=False)
    eigenvalues = singular**2 / (n - 1)
    total_variance = float(np.sum(eigenvalues))
    require(total_variance > 0, "No variance to explain")
    scores = u[:, :n_components] * singular[:n_components]
    loadings = vt[:n_components].copy()
    for component in range(n_components):
        anchor = int(np.argmax(np.abs(loadings[component])))
        if loadings[component, anchor] < 0:
            loadings[component] *= -1
            scores[:, component] *= -1
    projections = scores @ loadings
    reconstructed = projections * scales + means
    root_mean_squared_error = float(np.sqrt(np.mean((values - reconstructed) ** 2)))
    components = []
    for i in range(n_components):
        components.append(
            {
                "component": i + 1,
                "loadings": dict(zip(columns, loadings[i].tolist(), strict=True)),
                "eigenvalue": float(eigenvalues[i]),
                "explained_variance_ratio": float(eigenvalues[i] / total_variance),
            }
        )
    return {
        "method": "pca_svd",
        "dataset_revision": dataset.revision,
        "n_total": sample.n_total,
        "n_used": n,
        "n_excluded": sample.n_excluded,
        "variables": columns,
        "standardize": standardize,
        "ddof": 1,
        "means": means.tolist(),
        "scales": scales.tolist(),
        "components": components,
        "scores": scores.tolist(),
        "rmse_reconstruction": root_mean_squared_error,
        "limitations": [
            "Components are descriptive; causal interpretation unsupported",
            "Imputation is not performed; complete-case observations only",
        ],
    }


def _kmeans_single(
    data: np.ndarray, k: int, rng: np.random.Generator, max_iterations: int, tolerance: float
) -> tuple[np.ndarray, np.ndarray, float, int]:
    n = len(data)
    centers = np.empty((k, data.shape[1]), dtype=float)
    centers[0] = data[int(rng.integers(n))]
    for j in range(1, k):
        distances = np.min(cdist(data, centers[:j], metric="sqeuclidean"), axis=1)
        total = float(distances.sum())
        if total == 0:
            raise AnalysisError("INVALID_INPUT", "Too few distinct observations")
        centers[j] = data[int(rng.choice(n, p=distances / total))]
    iteration = 0
    for _ in range(max_iterations):
        iteration += 1
        squared = cdist(data, centers, metric="sqeuclidean")
        labels = np.argmin(squared, axis=1)
        new_centers = centers.copy()
        for group in range(k):
            members = data[labels == group]
            if len(members):
                new_centers[group] = members.mean(axis=0)
            else:
                # Re-seed empty cluster at the observation farthest from its current center.
                new_centers[group] = data[int(np.argmax(squared.min(axis=1)))]
        shift = float(np.max(np.linalg.norm(new_centers - centers, axis=1)))
        centers = new_centers
        if shift <= tolerance:
            break
    squared = cdist(data, centers, metric="sqeuclidean")
    labels = np.argmin(squared, axis=1)
    require(len(np.unique(labels)) == k, "Clustering returned an empty group")
    inertia = float(np.sum((data - centers[labels]) ** 2))
    return centers, labels, inertia, iteration


def kmeans_clusters(
    dataset: Dataset,
    columns: list[str],
    *,
    k: int,
    seed: int = 0,
    n_init: int = 8,
    max_iterations: int = 250,
    tolerance: float = 1e-7,
    standardize: bool = True,
) -> dict[str, Any]:
    """Seeded Lloyd k-means with k-means++ seeding and sorted output labels."""
    sample = extract_numeric_matrix(dataset, columns)
    matrix = sample.matrix
    n, p = matrix.shape
    require(
        2 <= k < n and len(np.unique(matrix, axis=0)) >= k,
        "Cluster count exceeds distinct observed cases",
    )
    require(1 <= n_init <= 50 and 1 <= max_iterations <= 2000, "Iteration/restart budget exceeded")
    require(0 < tolerance < 1, "Invalid convergence tolerance")
    means = matrix.mean(axis=0)
    scale = matrix.std(axis=0, ddof=1) if standardize else np.ones(p)
    require(bool(np.all(scale > 0)), "Cannot standardize constant predictor")
    standardized = (matrix - means) / scale
    rng = np.random.default_rng(seed)
    candidates = [
        _kmeans_single(standardized, k, rng, max_iterations, tolerance) for _ in range(n_init)
    ]
    centers, labels, inertia, iterations = min(candidates, key=lambda value: value[2])
    center_data_units = centers * scale + means
    order = sorted(range(k), key=lambda index: tuple(center_data_units[index].tolist()))
    remap = {old: new for new, old in enumerate(order)}
    labels = np.asarray([remap[int(v)] for v in labels])
    center_data_units = center_data_units[order]
    counts = [int(np.sum(labels == group)) for group in range(k)]
    require(sum(counts) == n and all(counts), "Cluster assignments failed reconciliation")
    return {
        "method": "kmeans_lloyd",
        "dataset_revision": dataset.revision,
        "n_total": sample.n_total,
        "n_used": n,
        "n_excluded": sample.n_excluded,
        "columns": columns,
        "k": k,
        "n_init": n_init,
        "max_iterations": max_iterations,
        "iterations_best": iterations,
        "seed": seed,
        "standardize": standardize,
        "inertia_standardized": inertia,
        "centers_original_units": center_data_units.tolist(),
        "labels": labels.tolist(),
        "group_sizes": counts,
        "limitations": [
            "Exploratory grouping; labels are nominal",
            "Cluster count chosen by researcher",
        ],
    }


def hierarchical_clusters(
    dataset: Dataset, columns: list[str], *, k: int, linkage: str = "ward", standardize: bool = True
) -> dict[str, Any]:
    require(linkage in ("ward", "complete", "average", "single"), "Invalid linkage")
    sample = extract_numeric_matrix(dataset, columns)
    values = sample.matrix
    require(
        2 <= k < len(values) and len(values) <= 10000,
        "Hierarchical cluster count/input outside resource budget",
    )
    scales = np.std(values, axis=0, ddof=1) if standardize else np.ones(values.shape[1])
    require(bool(np.all(scales > 0)), "Constant feature in clustering")
    normalized = (values - values.mean(axis=0)) / scales
    tree = hierarchy.linkage(normalized, method=linkage, metric="euclidean")
    labels = hierarchy.cut_tree(tree, n_clusters=k).ravel()
    counts = np.bincount(labels, minlength=k).tolist()
    require(all(counts) and sum(counts) == len(values), "Clustering partition invalid")
    return {
        "method": "hierarchical",
        "linkage": linkage,
        "k": k,
        "columns": columns,
        "labels": labels.tolist(),
        "group_sizes": counts,
        "linkage_matrix": tree.tolist(),
        "n_used": len(values),
        "n_excluded": sample.n_excluded,
        "dataset_revision": dataset.revision,
        "standardize": standardize,
        "limitation": "Exploratory partitions; distance and scaling are analyst-selected",
    }
