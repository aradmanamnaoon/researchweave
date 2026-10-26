use researchweave_analysis::AnalysisService;
use researchweave_core::{DispatchContext, OperationHandler};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{fs, hint::black_box, time::Instant};
use tempfile::tempdir;
use uuid::Uuid;

fn percentile(values: &[f64], p: f64) -> f64 {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let index = ((p * sorted.len() as f64).ceil() as usize)
        .saturating_sub(1)
        .min(sorted.len() - 1);
    sorted[index]
}

fn distribution(values: &[f64]) -> Value {
    json!({
        "n": values.len(),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "min_ms": values.iter().copied().fold(f64::INFINITY, f64::min),
        "max_ms": values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
        "samples_ms": values,
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let iterations = std::env::args()
        .nth(1)
        .map(|value| value.parse::<usize>())
        .transpose()?
        .unwrap_or(20);
    if iterations < 5 {
        return Err("iterations must be >= 5".into());
    }

    let root = tempdir()?;
    let imports = root.path().join("imports");
    fs::create_dir(&imports)?;
    let fixture_path = imports.join("clusters-350.csv");
    let mut csv = String::from("x,y,z\n");
    for index in 0..350usize {
        let cluster = index % 5;
        let within = index / 5;
        let x = cluster as f64 * 10.0 + (within % 7) as f64 * 0.07;
        let y = cluster as f64 * 5.0 + (within % 11) as f64 * 0.05;
        let z = cluster as f64 * 2.0 + (within % 13) as f64 * 0.03;
        csv.push_str(&format!("{x:.4},{y:.4},{z:.4}\n"));
    }
    fs::write(&fixture_path, csv.as_bytes())?;
    let fixture_sha256 = hex::encode(Sha256::digest(csv.as_bytes()));

    let store = root.path().join("analysis-store");
    let service = AnalysisService::new(&store, &imports)?;
    let context = DispatchContext {
        request_id: Uuid::nil(),
        project_id: Uuid::nil(),
        actor: "performance-baseline".into(),
        expected_revision: None,
    };
    let imported = service.execute(
        "dataset.import",
        &json!({"filename":"clusters-350.csv"}),
        &context,
    );
    if imported.get("status").is_some() || imported["data"]["n"].as_u64() != Some(350) {
        return Err(format!("fixture import failed: {imported}").into());
    }
    if imported["data"]["source_hash"].as_str() != Some(fixture_sha256.as_str()) {
        return Err("fixture source hash mismatch".into());
    }
    let dataset_id = imported["data"]["dataset_id"]
        .as_str()
        .ok_or("missing dataset id")?
        .to_owned();
    let revision = imported["data"]["revision"]
        .as_str()
        .ok_or("missing revision")?
        .to_owned();

    let hierarchical_args = json!({
        "dataset_id": dataset_id,
        "revision": revision,
        "columns": ["x","y","z"],
        "k": 5,
        "linkage": "ward",
        "standardize": true,
    });
    let kmeans_args = json!({
        "dataset_id": hierarchical_args["dataset_id"],
        "revision": hierarchical_args["revision"],
        "columns": ["x","y","z"],
        "k": 5,
        "seed": 42,
        "n_init": 8,
        "max_iterations": 250,
        "tolerance": 1e-7,
        "standardize": true,
    });

    for (operation, args) in [
        ("statistics.hierarchical", &hierarchical_args),
        ("statistics.kmeans", &kmeans_args),
    ] {
        let warm = service.execute(operation, args, &context);
        if warm.get("status").is_some() || warm["data"]["n_used"].as_u64() != Some(350) {
            return Err(format!("warm {operation} failed: {warm}").into());
        }
        black_box(warm);
    }

    let mut hierarchical_ms = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = service.execute(
            "statistics.hierarchical",
            black_box(&hierarchical_args),
            black_box(&context),
        );
        hierarchical_ms.push(started.elapsed().as_secs_f64() * 1000.0);
        if result.get("status").is_some()
            || result["data"]["n_used"].as_u64() != Some(350)
            || result["data"]["linkage_matrix"].as_array().map(Vec::len) != Some(349)
        {
            return Err(format!("timed hierarchical clustering failed: {result}").into());
        }
        black_box(result);
    }

    let mut kmeans_ms = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = service.execute(
            "statistics.kmeans",
            black_box(&kmeans_args),
            black_box(&context),
        );
        kmeans_ms.push(started.elapsed().as_secs_f64() * 1000.0);
        if result.get("status").is_some()
            || result["data"]["n_used"].as_u64() != Some(350)
            || result["data"]["seed"].as_u64() != Some(42)
        {
            return Err(format!("timed k-means failed: {result}").into());
        }
        black_box(result);
    }

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema": 1,
            "fixture": {
                "rows": 350,
                "columns": 3,
                "groups": 5,
                "source_sha256": fixture_sha256,
                "dataset_id": hierarchical_args["dataset_id"],
                "revision": hierarchical_args["revision"],
            },
            "iterations": iterations,
            "hierarchical_ward": distribution(&hierarchical_ms),
            "kmeans_seed_42": distribution(&kmeans_ms),
            "notes": [
                "Fixture generation/import and one warm-up execution per operation are outside timed regions",
                "Timed calls go through AnalysisService and reload the immutable dataset revision",
                "Hierarchical clustering runs at the live 350-row O(n^3) resource ceiling",
                "K-means uses deterministic SplitMix64 seed 42, n_init=8 and the live convergence controls"
            ]
        }))?
    );
    Ok(())
}
