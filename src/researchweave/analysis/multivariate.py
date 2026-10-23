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


def _adjusted_rand(first: np.ndarray, second: np.ndarray) -> float:
    """Adjusted Rand index without an optional scikit-learn dependency."""

    require(len(first) == len(second) and len(first) >= 2, "Cluster label vectors must align")
    a_levels = np.unique(first)
    b_levels = np.unique(second)
    contingency = np.zeros((len(a_levels), len(b_levels)), dtype=np.int64)
    a_map = {value: index for index, value in enumerate(a_levels.tolist())}
    b_map = {value: index for index, value in enumerate(b_levels.tolist())}
    for a, b in zip(first.tolist(), second.tolist(), strict=True):
        contingency[a_map[a], b_map[b]] += 1

    def pairs(values: np.ndarray) -> float:
        return float(np.sum(values * (values - 1) / 2))

    nij = pairs(contingency)
    ai = pairs(contingency.sum(axis=1))
    bj = pairs(contingency.sum(axis=0))
    total = len(first) * (len(first) - 1) / 2
    expected = ai * bj / total if total else 0.0
    maximum = (ai + bj) / 2
    denominator = maximum - expected
    return 1.0 if denominator == 0 and nij == expected else (nij - expected) / denominator


def _cluster_indices(
    matrix: np.ndarray, labels: np.ndarray, centers: np.ndarray
) -> dict[str, float]:
    """Silhouette, Calinski-Harabasz and Davies-Bouldin for one partition."""

    n = len(matrix)
    groups = sorted(np.unique(labels).tolist())
    k = len(groups)
    require(2 <= k < n, "Cluster validation requires 2..n-1 groups")
    distances = cdist(matrix, matrix, metric="euclidean")
    silhouettes: list[float] = []
    for i, label in enumerate(labels):
        same = np.flatnonzero(labels == label)
        same = same[same != i]
        a = float(np.mean(distances[i, same])) if len(same) else 0.0
        other_means = [
            float(np.mean(distances[i, labels == other])) for other in groups if other != label
        ]
        b = min(other_means)
        silhouettes.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    grand = matrix.mean(axis=0)
    between = sum(
        int(np.sum(labels == group)) * float(np.sum((centers[group] - grand) ** 2))
        for group in groups
    )
    within = sum(float(np.sum((matrix[labels == group] - centers[group]) ** 2)) for group in groups)
    require(within > 0, "Within-cluster dispersion is zero")
    calinski = (between / (k - 1)) / (within / (n - k))
    scatters = np.asarray(
        [
            float(np.mean(np.linalg.norm(matrix[labels == group] - centers[group], axis=1)))
            for group in groups
        ]
    )
    center_distances = cdist(centers, centers, metric="euclidean")
    ratios = []
    for i in range(k):
        candidates = [
            (scatters[i] + scatters[j]) / center_distances[i, j]
            for j in range(k)
            if j != i and center_distances[i, j] > 0
        ]
        require(bool(candidates), "Cluster centers are not distinct")
        ratios.append(max(candidates))
    return {
        "silhouette": float(np.mean(silhouettes)),
        "calinski_harabasz": float(calinski),
        "davies_bouldin": float(np.mean(ratios)),
    }


def cluster_validation(
    dataset: Dataset,
    columns: list[str],
    *,
    k_values: list[int],
    seed: int = 0,
    stability_repeats: int = 8,
) -> dict[str, Any]:
    """Validate candidate k-means partitions and quantify seed stability."""

    require(
        bool(k_values) and len(set(k_values)) == len(k_values) and len(k_values) <= 20,
        "Distinct candidate cluster counts required",
    )
    require(2 <= stability_repeats <= 30, "Stability repeats must be 2..30")
    sample = extract_numeric_matrix(dataset, columns)
    matrix = sample.matrix
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0, ddof=1)
    require(bool(np.all(scales > 0)), "Cannot validate clustering with constant features")
    normalized = (matrix - means) / scales
    require(all(2 <= k < len(matrix) for k in k_values), "Candidate k outside 2..n-1")
    rows = []
    for k in sorted(k_values):
        runs = [
            kmeans_clusters(dataset, columns, k=k, seed=seed + repeat, n_init=4)
            for repeat in range(stability_repeats)
        ]
        base_labels = np.asarray(runs[0]["labels"], dtype=int)
        centers = np.asarray(runs[0]["centers_original_units"], dtype=float)
        centers_normalized = (centers - means) / scales
        indices = _cluster_indices(normalized, base_labels, centers_normalized)
        stability = [
            _adjusted_rand(base_labels, np.asarray(run["labels"], dtype=int)) for run in runs[1:]
        ]
        rows.append(
            {
                "k": k,
                **indices,
                "mean_adjusted_rand_vs_first": float(np.mean(stability)),
                "min_adjusted_rand_vs_first": float(np.min(stability)),
                "inertia_standardized": float(runs[0]["inertia_standardized"]),
            }
        )
    recommended = max(
        rows,
        key=lambda item: (
            item["silhouette"],
            item["mean_adjusted_rand_vs_first"],
            -item["davies_bouldin"],
        ),
    )["k"]
    return {
        "method": "kmeans_validation",
        "candidates": rows,
        "recommended_k_by_declared_rule": recommended,
        "selection_rule": "maximize silhouette, then seed stability, then minimize Davies-Bouldin",
        "seed": seed,
        "stability_repeats": stability_repeats,
        "n_used": len(matrix),
        "n_excluded": sample.n_excluded,
        "dataset_revision": dataset.revision,
        "limitations": [
            "Internal indices and seed stability do not establish substantive cluster validity",
            "Recommendation is exploratory and must not be treated as confirmatory evidence",
        ],
    }
