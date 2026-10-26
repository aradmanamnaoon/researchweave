use researchweave_analysis::{describe, linear_regression, Dataset, Variable};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, env, hint::black_box, time::Instant};

fn variable(name: &str) -> Variable {
    Variable {
        name: name.to_owned(),
        dtype: "float64".into(),
        label: String::new(),
        units: String::new(),
        scale: "continuous".into(),
        missing_values: Vec::new(),
        value_labels: BTreeMap::new(),
        category_order: Vec::new(),
        allowed_min: None,
        allowed_max: None,
        privacy_class: "public".into(),
        private: false,
    }
}

fn fixture(rows: usize) -> Dataset {
    let columns = vec![
        "outcome".to_owned(),
        "x1".to_owned(),
        "x2".to_owned(),
        "x3".to_owned(),
        "x4".to_owned(),
        "x5".to_owned(),
    ];
    let variables = columns.iter().map(|name| variable(name)).collect();
    let mut records = Vec::with_capacity(rows);
    let mut fixture_hasher = Sha256::new();
    for i in 0..rows {
        let x1 = (i % 1000) as f64 / 100.0;
        let x2 = ((i * 37) % 997) as f64 / 50.0;
        let x3 = ((i * 73) % 991) as f64 / 80.0;
        let x4 = ((i * 13) % 101) as f64 / 10.0;
        let x5 = (i % 2) as f64;
        let deterministic_residual = ((i * 17) % 23) as f64 / 100.0 - 0.11;
        let outcome =
            1.5 + 0.4 * x1 - 0.2 * x2 + 0.05 * x3 + 0.1 * x4 + 0.7 * x5 + deterministic_residual;
        for value in [outcome, x1, x2, x3, x4, x5] {
            fixture_hasher.update(value.to_le_bytes());
        }
        let mut row = BTreeMap::new();
        row.insert("outcome".into(), Value::from(outcome));
        row.insert("x1".into(), Value::from(x1));
        row.insert("x2".into(), Value::from(x2));
        row.insert("x3".into(), Value::from(x3));
        row.insert("x4".into(), Value::from(x4));
        row.insert("x5".into(), Value::from(x5));
        records.push(row);
    }
    Dataset {
        dataset_id: "000000000000000000000001".into(),
        revision: "0000000000000000000000000000000000000000000000000000000000000001".into(),
        parent_revision: None,
        source_hash: hex::encode(fixture_hasher.finalize()),
        created_at: "2026-10-26T00:00:00Z".into(),
        columns,
        variables,
        records,
        operation: json!({"type":"synthetic_performance_fixture","rows":rows,"seed":"deterministic-formula-v1"}),
    }
}

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
    let rows = env::args()
        .nth(1)
        .map(|value| value.parse::<usize>())
        .transpose()?
        .unwrap_or(100_000);
    let iterations = env::args()
        .nth(2)
        .map(|value| value.parse::<usize>())
        .transpose()?
        .unwrap_or(20);
    if rows < 1_000 || iterations < 5 {
        return Err("rows must be >= 1000 and iterations >= 5".into());
    }

    let dataset = fixture(rows);
    let predictors = vec![
        "x1".to_owned(),
        "x2".to_owned(),
        "x3".to_owned(),
        "x4".to_owned(),
        "x5".to_owned(),
    ];

    let warm_describe = describe(&dataset, "outcome")?;
    let warm_model = linear_regression(&dataset, "outcome", &predictors, "HC3", None)?;
    if warm_describe["n_valid"] != rows || warm_model["n_used"] != rows {
        return Err("benchmark warm-up returned an unexpected sample count".into());
    }
    if warm_model.pointer("/details/covariance") != Some(&Value::String("HC3".into())) {
        return Err("benchmark warm-up did not use HC3 covariance".into());
    }
    black_box(warm_describe);
    black_box(warm_model);

    let mut describe_ms = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = describe(black_box(&dataset), "outcome")?;
        describe_ms.push(started.elapsed().as_secs_f64() * 1000.0);
        black_box(result);
    }

    let mut regression_ms = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = linear_regression(black_box(&dataset), "outcome", &predictors, "HC3", None)?;
        regression_ms.push(started.elapsed().as_secs_f64() * 1000.0);
        black_box(result);
    }

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema": 1,
            "fixture": {
                "rows": rows,
                "predictors": predictors.len(),
                "generation": "deterministic-formula-v1",
                "missing": 0,
                "source_sha256": dataset.source_hash,
            },
            "iterations": iterations,
            "describe": distribution(&describe_ms),
            "linear_regression_hc3": distribution(&regression_ms),
            "notes": [
                "Dataset construction is outside timed regions",
                "One warm-up execution per operation is excluded",
                "Regression uses five predictors plus intercept and HC3 robust covariance",
            ],
        }))?
    );
    Ok(())
}
