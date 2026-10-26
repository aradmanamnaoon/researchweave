//! Deterministic multivariate analysis over immutable dataset revisions.
use super::{finite_value, AnalysisError, Dataset};
use nalgebra::{DMatrix, SymmetricEigen};
use serde_json::{json, Value};
use std::collections::BTreeSet;

type ClusterMatrix = (Vec<Vec<f64>>, Vec<f64>, Vec<f64>, usize);
type KmeansCandidate = (Vec<Vec<f64>>, Vec<usize>, f64, usize);

fn cluster_matrix(
    dataset: &Dataset,
    columns: &[String],
    standardize: bool,
    limit: usize,
) -> Result<ClusterMatrix, AnalysisError> {
    if columns.len() < 2
        || columns.len() > 1000
        || columns.iter().collect::<BTreeSet<_>>().len() != columns.len()
        || columns.iter().any(|c| !dataset.columns.contains(c))
    {
        return Err(AnalysisError::InvalidInput(
            "two or more distinct known columns required".into(),
        ));
    }
    if dataset.records.len().saturating_mul(columns.len()) > 5_000_000 {
        return Err(AnalysisError::ResourceLimit(
            "clustering matrix budget".into(),
        ));
    }
    let mut rows = Vec::new();
    for record in &dataset.records {
        if columns
            .iter()
            .any(|c| record.get(c).is_none_or(Value::is_null))
        {
            continue;
        }
        rows.push(
            columns
                .iter()
                .map(|c| finite_value(&record[c], c))
                .collect::<Result<Vec<_>, _>>()?,
        );
        if rows.len() > limit {
            return Err(AnalysisError::ResourceLimit("clustering row budget".into()));
        }
    }
    if rows.len() < 3 {
        return Err(AnalysisError::InvalidInput(
            "at least three complete observations required".into(),
        ));
    }
    let n = rows.len();
    let p = columns.len();
    let means = (0..p)
        .map(|j| rows.iter().map(|r| r[j]).sum::<f64>() / n as f64)
        .collect::<Vec<_>>();
    let scales = (0..p)
        .map(|j| {
            if standardize {
                (rows.iter().map(|r| (r[j] - means[j]).powi(2)).sum::<f64>() / (n - 1) as f64)
                    .sqrt()
            } else {
                1.0
            }
        })
        .collect::<Vec<_>>();
    if scales.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return Err(AnalysisError::InvalidInput(
            "constant or unstable feature".into(),
        ));
    }
    for row in &mut rows {
        for j in 0..p {
            row[j] = (row[j] - means[j]) / scales[j];
        }
    }
    if rows
        .iter()
        .flatten()
        .any(|v| !v.is_finite() || v.abs() > 1e100)
    {
        return Err(AnalysisError::InvalidInput(
            "non-finite standardized feature".into(),
        ));
    }
    Ok((rows, means, scales, dataset.records.len() - n))
}

fn squared(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| (x - y) * (x - y)).sum()
}

// Fixed, portable PRNG. The seed is a documented Rust algorithm seed; NumPy PCG64
// seeds produce equivalent semantics but deliberately different initializations.
struct ClusterRng(u64);
impl ClusterRng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^ (z >> 31)
    }
    fn fraction(&mut self) -> f64 {
        (self.next() >> 11) as f64 / ((1u64 << 53) as f64)
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn kmeans_clusters(
    dataset: &Dataset,
    columns: &[String],
    k: usize,
    seed: u64,
    n_init: usize,
    max_iterations: usize,
    tolerance: f64,
    standardize: bool,
) -> Result<Value, AnalysisError> {
    if !(1..=50).contains(&n_init)
        || !(1..=2000).contains(&max_iterations)
        || !(0.0..1.0).contains(&tolerance)
    {
        return Err(AnalysisError::InvalidInput(
            "invalid k-means iteration/tolerance budget".into(),
        ));
    }
    let (rows, means, scales, excluded) = cluster_matrix(dataset, columns, standardize, 20_000)?;
    let n = rows.len();
    if k < 2
        || k >= n
        || k > 128
        || n.saturating_mul(k)
            .saturating_mul(columns.len())
            .saturating_mul(n_init)
            .saturating_mul(max_iterations)
            > 150_000_000
    {
        return Err(AnalysisError::ResourceLimit(
            "k-means cluster/computation budget".into(),
        ));
    }
    let distinct = rows
        .iter()
        .map(|r| r.iter().map(|v| v.to_bits()).collect::<Vec<_>>())
        .collect::<BTreeSet<_>>()
        .len();
    if distinct < k {
        return Err(AnalysisError::InvalidInput("too few distinct cases".into()));
    }
    let mut rng = ClusterRng(seed);
    let mut best: Option<KmeansCandidate> = None;
    for _ in 0..n_init {
        let mut centers = vec![rows[(rng.next() % n as u64) as usize].clone()];
        while centers.len() < k {
            let distances = rows
                .iter()
                .map(|r| {
                    centers
                        .iter()
                        .map(|c| squared(r, c))
                        .fold(f64::INFINITY, f64::min)
                })
                .collect::<Vec<_>>();
            let sum = distances.iter().sum::<f64>();
            if !sum.is_finite() || sum <= 0.0 {
                return Err(AnalysisError::InvalidInput("degenerate seeding".into()));
            }
            let target = rng.fraction() * sum;
            let mut cumulative = 0.0;
            let next = distances
                .iter()
                .position(|d| {
                    cumulative += d;
                    cumulative > target
                })
                .unwrap_or(n - 1);
            centers.push(rows[next].clone());
        }
        let mut iterations = 0;
        for _ in 0..max_iterations {
            iterations += 1;
            let labels = assign(&rows, &centers);
            let mut sums = vec![vec![0.0; columns.len()]; k];
            let mut counts = vec![0usize; k];
            for (row, &label) in rows.iter().zip(&labels) {
                counts[label] += 1;
                for (s, x) in sums[label].iter_mut().zip(row) {
                    *s += x;
                }
            }
            for j in 0..k {
                if counts[j] > 0 {
                    for value in &mut sums[j] {
                        *value /= counts[j] as f64;
                    }
                } else {
                    let farthest = rows
                        .iter()
                        .enumerate()
                        .max_by(|(ia, a), (ib, b)| {
                            squared(a, &centers[labels[*ia]])
                                .total_cmp(&squared(b, &centers[labels[*ib]]))
                                .then_with(|| ib.cmp(ia))
                        })
                        .map(|(i, _)| i)
                        .unwrap_or(0);
                    sums[j] = rows[farthest].clone();
                }
            }
            let shift = sums
                .iter()
                .zip(&centers)
                .map(|(a, b)| squared(a, b).sqrt())
                .fold(0.0, f64::max);
            centers = sums;
            if shift <= tolerance {
                break;
            }
        }
        let labels = assign(&rows, &centers);
        if (0..k).any(|j| !labels.contains(&j)) {
            continue;
        }
        let inertia = rows
            .iter()
            .zip(&labels)
            .map(|(row, &j)| squared(row, &centers[j]))
            .sum::<f64>();
        if !inertia.is_finite() {
            return Err(AnalysisError::InvalidInput("non-finite inertia".into()));
        }
        if best.as_ref().is_none_or(|b| inertia < b.2) {
            best = Some((centers, labels, inertia, iterations));
        }
    }
    let (centers, labels, inertia, iterations) =
        best.ok_or_else(|| AnalysisError::InvalidInput("empty cluster assignment".into()))?;
    let original = centers
        .iter()
        .map(|r| {
            r.iter()
                .enumerate()
                .map(|(j, v)| v * scales[j] + means[j])
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    let mut order: Vec<_> = (0..k).collect();
    order.sort_by(|a, b| {
        original[*a]
            .iter()
            .zip(&original[*b])
            .map(|(x, y)| x.total_cmp(y))
            .find(|o| !o.is_eq())
            .unwrap_or(a.cmp(b))
    });
    let mut remap = vec![0; k];
    for (new, &old) in order.iter().enumerate() {
        remap[old] = new;
    }
    let labels = labels.into_iter().map(|l| remap[l]).collect::<Vec<_>>();
    let group_sizes = (0..k)
        .map(|j| labels.iter().filter(|&&v| v == j).count())
        .collect::<Vec<_>>();
    Ok(
        json!({"method":"kmeans_lloyd","dataset_revision":dataset.revision,"source_hash":dataset.source_hash,
        "n_total":dataset.records.len(),"n_used":n,"n_excluded":excluded,"columns":columns,
        "k":k,"seed":seed,"prng":"splitmix64","n_init":n_init,"max_iterations":max_iterations,
        "iterations_best":iterations,"standardize":standardize,"inertia_standardized":inertia,
        "centers_original_units":order.iter().map(|&i| &original[i]).collect::<Vec<_>>(),
        "labels":labels,"group_sizes":group_sizes,
        "limitations":["Exploratory grouping; labels are nominal","Cluster count chosen by researcher"]}),
    )
}

fn assign(rows: &[Vec<f64>], centers: &[Vec<f64>]) -> Vec<usize> {
    rows.iter()
        .map(|r| {
            (0..centers.len())
                .min_by(|&a, &b| {
                    squared(r, &centers[a])
                        .total_cmp(&squared(r, &centers[b]))
                        .then_with(|| a.cmp(&b))
                })
                .unwrap_or(0)
        })
        .collect()
}

pub(super) fn hierarchical_clusters(
    dataset: &Dataset,
    columns: &[String],
    k: usize,
    linkage: &str,
    standardize: bool,
) -> Result<Value, AnalysisError> {
    if !matches!(linkage, "ward" | "single" | "complete" | "average") {
        return Err(AnalysisError::InvalidInput("unsupported linkage".into()));
    }
    // O(n^3) direct algorithm: stricter budget than SciPy's optimized implementation.
    let (rows, _, _, excluded) = cluster_matrix(dataset, columns, standardize, 350)?;
    let n = rows.len();
    if k < 2 || k >= n {
        return Err(AnalysisError::InvalidInput("invalid cluster count".into()));
    }
    let leaves = rows.clone();
    let mut active: Vec<(usize, Vec<usize>, Vec<f64>)> = rows
        .into_iter()
        .enumerate()
        .map(|(i, row)| (i, vec![i], row))
        .collect();
    let mut history: Vec<[f64; 4]> = Vec::with_capacity(n - 1);
    let mut partition = Vec::new();
    for step in 0..n - 1 {
        if active.len() == k {
            partition = active.iter().map(|c| c.1.clone()).collect();
        }
        let mut best = (0, 1, f64::INFINITY);
        for i in 0..active.len() {
            for j in i + 1..active.len() {
                let a = &active[i];
                let b = &active[j];
                let d = if linkage == "ward" {
                    (2.0 * a.1.len() as f64 * b.1.len() as f64 / (a.1.len() + b.1.len()) as f64
                        * squared(&a.2, &b.2))
                    .sqrt()
                } else {
                    let mut ds = Vec::new();
                    for &x in &a.1 {
                        for &y in &b.1 {
                            // Original standardized observations kept via leaf centroids.
                            ds.push(squared(&leaves[x], &leaves[y]).sqrt());
                        }
                    }
                    match linkage {
                        "single" => ds.into_iter().fold(f64::INFINITY, f64::min),
                        "complete" => ds.into_iter().fold(0.0, f64::max),
                        _ => ds.iter().sum::<f64>() / ds.len() as f64,
                    }
                };
                if d.total_cmp(&best.2).is_lt() {
                    best = (i, j, d);
                }
            }
        }
        let (i, j, d) = best;
        let b = active.remove(j);
        let a = active.remove(i);
        let size = a.1.len() + b.1.len();
        let center =
            a.2.iter()
                .zip(&b.2)
                .map(|(x, y)| (x * a.1.len() as f64 + y * b.1.len() as f64) / size as f64)
                .collect();
        let mut members = a.1;
        members.extend(b.1);
        history.push([a.0 as f64, b.0 as f64, d, size as f64]);
        active.push((n + step, members, center));
    }
    partition.sort_by_key(|members| *members.iter().min().unwrap_or(&usize::MAX));
    let mut labels = vec![0usize; n];
    for (label, members) in partition.iter().enumerate() {
        for &i in members {
            labels[i] = label;
        }
    }
    let group_sizes = partition.iter().map(Vec::len).collect::<Vec<_>>();
    Ok(
        json!({"method":"hierarchical","linkage":linkage,"dataset_revision":dataset.revision,
        "source_hash":dataset.source_hash,"n_total":dataset.records.len(),"n_used":n,
        "n_excluded":excluded,"columns":columns,"k":k,"standardize":standardize,
        "labels":labels,"group_sizes":group_sizes,"linkage_matrix":history,
        "limitation":"Exploratory partitions; distance and scaling are analyst-selected"}),
    )
}

pub(super) fn principal_components(
    dataset: &Dataset,
    columns: &[String],
    n_components: usize,
    standardize: bool,
) -> Result<Value, AnalysisError> {
    if columns.len() < 2
        || columns.len() > 1_000
        || columns
            .iter()
            .collect::<std::collections::BTreeSet<_>>()
            .len()
            != columns.len()
        || columns
            .iter()
            .any(|column| !dataset.columns.iter().any(|candidate| candidate == column))
    {
        return Err(AnalysisError::InvalidInput(
            "PCA requires 2 to 1000 distinct known columns".into(),
        ));
    }
    if dataset.records.len().saturating_mul(columns.len()) > 5_000_000 {
        return Err(AnalysisError::ResourceLimit(
            "PCA numeric matrix exceeds resource budget".into(),
        ));
    }

    let mut rows = Vec::new();
    let mut excluded = 0usize;
    for row in &dataset.records {
        if columns
            .iter()
            .any(|column| row.get(column).is_none_or(Value::is_null))
        {
            excluded += 1;
            continue;
        }
        let values = columns
            .iter()
            .map(|column| finite_value(row.get(column).expect("checked above"), column))
            .collect::<Result<Vec<_>, _>>()?;
        rows.push(values);
    }
    let n = rows.len();
    let p = columns.len();
    if n < 3 {
        return Err(AnalysisError::InvalidInput(
            "PCA requires at least three complete observations".into(),
        ));
    }
    let max_components = (n - 1).min(p);
    if !(1..=max_components).contains(&n_components) {
        return Err(AnalysisError::InvalidInput(
            "invalid PCA component count".into(),
        ));
    }

    let mut matrix = DMatrix::<f64>::zeros(n, p);
    for (row_index, row) in rows.iter().enumerate() {
        for (column_index, value) in row.iter().enumerate() {
            matrix[(row_index, column_index)] = *value;
        }
    }
    let means: Vec<f64> = (0..p)
        .map(|column| (0..n).map(|row| matrix[(row, column)]).sum::<f64>() / n as f64)
        .collect();
    let scales: Vec<f64> = (0..p)
        .map(|column| {
            if !standardize {
                return 1.0;
            }
            let variance = (0..n)
                .map(|row| {
                    let centered = matrix[(row, column)] - means[column];
                    centered * centered
                })
                .sum::<f64>()
                / (n - 1) as f64;
            variance.sqrt()
        })
        .collect();
    if scales
        .iter()
        .any(|scale| !scale.is_finite() || *scale <= 0.0)
    {
        return Err(AnalysisError::InvalidInput(
            "cannot apply PCA to constant-valued columns".into(),
        ));
    }

    let mut normalized = DMatrix::<f64>::zeros(n, p);
    for row in 0..n {
        for column in 0..p {
            normalized[(row, column)] = (matrix[(row, column)] - means[column]) / scales[column];
        }
    }
    let covariance = (&normalized.transpose() * &normalized) / (n - 1) as f64;
    let decomposition = SymmetricEigen::new(covariance);
    let mut order: Vec<usize> = (0..p).collect();
    order.sort_by(|left, right| {
        decomposition.eigenvalues[*right]
            .total_cmp(&decomposition.eigenvalues[*left])
            .then_with(|| left.cmp(right))
    });
    let eigenvalues: Vec<f64> = order
        .iter()
        .map(|index| decomposition.eigenvalues[*index].max(0.0))
        .collect();
    let total_variance = eigenvalues.iter().sum::<f64>();
    if !total_variance.is_finite() || total_variance <= 0.0 {
        return Err(AnalysisError::InvalidInput(
            "PCA has no variance to explain".into(),
        ));
    }

    let mut selected_loadings = DMatrix::<f64>::zeros(n_components, p);
    let mut scores = DMatrix::<f64>::zeros(n, n_components);
    let mut components = Vec::with_capacity(n_components);
    for component in 0..n_components {
        let eigen_index = order[component];
        let mut loadings: Vec<f64> = (0..p)
            .map(|row| decomposition.eigenvectors[(row, eigen_index)])
            .collect();
        let anchor = loadings
            .iter()
            .enumerate()
            .max_by(|(left_index, left), (right_index, right)| {
                left.abs()
                    .total_cmp(&right.abs())
                    .then_with(|| right_index.cmp(left_index))
            })
            .map(|(index, _)| index)
            .ok_or_else(|| AnalysisError::Integrity("PCA loading vector missing".into()))?;
        if loadings[anchor] < 0.0 {
            for loading in &mut loadings {
                *loading = -*loading;
            }
        }
        for column in 0..p {
            selected_loadings[(component, column)] = loadings[column];
        }
        for row in 0..n {
            scores[(row, component)] = (0..p)
                .map(|column| normalized[(row, column)] * loadings[column])
                .sum::<f64>();
        }
        let loading_map = columns
            .iter()
            .cloned()
            .zip(loadings.into_iter().map(Value::from))
            .collect::<serde_json::Map<String, Value>>();
        components.push(json!({
            "component":component + 1,
            "loadings":loading_map,
            "eigenvalue":eigenvalues[component],
            "explained_variance_ratio":eigenvalues[component] / total_variance
        }));
    }

    let reconstructed_normalized = &scores * &selected_loadings;
    let mut squared_error = 0.0;
    for row in 0..n {
        for column in 0..p {
            let reconstructed =
                reconstructed_normalized[(row, column)] * scales[column] + means[column];
            let difference = matrix[(row, column)] - reconstructed;
            squared_error += difference * difference;
        }
    }
    let rmse = (squared_error / (n * p) as f64).sqrt();
    let score_rows: Vec<Vec<f64>> = (0..n)
        .map(|row| {
            (0..n_components)
                .map(|column| scores[(row, column)])
                .collect()
        })
        .collect();

    Ok(json!({
        "method":"pca_symmetric_eigen",
        "dataset_revision":dataset.revision,
        "source_hash":dataset.source_hash,
        "n_total":dataset.records.len(),
        "n_used":n,
        "n_excluded":excluded,
        "variables":columns,
        "standardize":standardize,
        "ddof":1,
        "means":means,
        "scales":scales,
        "components":components,
        "scores":score_rows,
        "rmse_reconstruction":rmse,
        "limitations":[
            "Components are descriptive; causal interpretation unsupported",
            "Imputation is not performed; complete-case observations only"
        ]
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::AnalysisService;
    use researchweave_core::{DispatchContext, OperationHandler};
    use std::fs;
    use uuid::Uuid;

    #[test]
    fn clustering_python_partition_golden_provenance_restart_and_invalid_inputs() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("clusters.csv"),
            "x,y\n0,0\n0,1\n1,0\n1,1\n10,10\n10,11\n11,10\n11,11\n,5\n",
        )
        .unwrap();
        let db = root.path().join("db");
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let service = AnalysisService::new(&db, &imports).unwrap();
        let imported = service.execute(
            "dataset.import",
            &json!({"filename":"clusters.csv"}),
            &context,
        );
        let arguments = json!({"dataset_id": imported["data"]["dataset_id"],
            "revision": imported["data"]["revision"], "columns":["x","y"],
            "k":2,"seed":42,"n_init":4,"standardize":false});
        let result = service.execute("statistics.kmeans", &arguments, &context);
        assert!(result.get("status").is_none(), "{result}");
        assert_eq!(result["data"]["labels"], json!([0, 0, 0, 0, 1, 1, 1, 1]));
        assert_eq!(result["data"]["group_sizes"], json!([4, 4]));
        assert_eq!(
            result["data"]["centers_original_units"],
            json!([[0.5, 0.5], [10.5, 10.5]])
        );
        assert!((result["data"]["inertia_standardized"].as_f64().unwrap() - 4.0).abs() < 1e-10);
        assert_eq!(result["data"]["n_excluded"], 1);
        assert_eq!(
            result["data"]["source_hash"],
            imported["data"]["source_hash"]
        );
        let rerun = AnalysisService::new(&db, &imports).unwrap().execute(
            "statistics.kmeans",
            &arguments,
            &context,
        );
        assert_eq!(result, rerun);
        for linkage in ["ward", "single", "complete", "average"] {
            let mut args = arguments.clone();
            args["linkage"] = json!(linkage);
            let h = service.execute("statistics.hierarchical", &args, &context);
            assert!(h.get("status").is_none(), "{h}");
            assert_eq!(h["data"]["labels"], json!([0, 0, 0, 0, 1, 1, 1, 1]));
            assert_eq!(h["data"]["group_sizes"], json!([4, 4]));
            assert_eq!(h["data"]["linkage_matrix"].as_array().unwrap().len(), 7);
        }
        let mut invalid = arguments;
        invalid["k"] = json!(20);
        assert_eq!(
            service.execute("statistics.kmeans", &invalid, &context)["status"],
            "failed"
        );
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|c| c.operation == "statistics.kmeans"));
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|c| c.operation == "statistics.hierarchical"));
    }

    #[test]
    fn pca_matches_python_covariance_oracle_restart_and_fail_closed() {
        let root = tempfile::tempdir().unwrap();
        let imports = root.path().join("imports");
        fs::create_dir(&imports).unwrap();
        fs::write(
            imports.join("coordinates.csv"),
            "x,y\n0,0\n0,1\n1,0\n1,1\n10,10\n10,11\n11,10\n11,11\n",
        )
        .unwrap();
        let db = root.path().join("db");
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let service = AnalysisService::new(&db, &imports).unwrap();
        let imported = service.execute(
            "dataset.import",
            &json!({"filename":"coordinates.csv"}),
            &context,
        );
        let arguments = json!({
            "dataset_id":imported["data"]["dataset_id"],
            "revision":imported["data"]["revision"],
            "columns":["x","y"],
            "n_components":2,
            "standardize":false
        });
        let first = service.execute("statistics.pca", &arguments, &context);
        assert!(first.get("status").is_none(), "{first}");
        let components = first["data"]["components"].as_array().unwrap();
        assert!((components[0]["eigenvalue"].as_f64().unwrap() - 57.42857142857143).abs() < 1e-10);
        assert!((components[1]["eigenvalue"].as_f64().unwrap() - 0.2857142857142857).abs() < 1e-10);
        assert!(
            (components
                .iter()
                .map(|value| value["explained_variance_ratio"].as_f64().unwrap())
                .sum::<f64>()
                - 1.0)
                .abs()
                < 1e-12
        );
        assert!(first["data"]["rmse_reconstruction"].as_f64().unwrap() < 1e-10);
        assert_eq!(first["data"]["n_used"], 8);
        assert_eq!(
            first["data"]["dataset_revision"],
            imported["data"]["revision"]
        );
        assert_eq!(
            first["data"]["source_hash"],
            imported["data"]["source_hash"]
        );
        let restarted = AnalysisService::new(&db, &imports).unwrap().execute(
            "statistics.pca",
            &arguments,
            &context,
        );
        assert_eq!(first, restarted);

        fs::write(imports.join("constant.csv"), "x,y\n1,3\n1,4\n1,5\n1,6\n").unwrap();
        let constant = service.execute(
            "dataset.import",
            &json!({"filename":"constant.csv"}),
            &context,
        );
        let rejected = service.execute(
            "statistics.pca",
            &json!({
                "dataset_id":constant["data"]["dataset_id"],
                "revision":constant["data"]["revision"],
                "columns":["x","y"],
                "n_components":2
            }),
            &context,
        );
        assert_eq!(rejected["status"], "failed");
        assert!(AnalysisService::capabilities()
            .iter()
            .any(|capability| capability.operation == "statistics.pca"));
    }
}
