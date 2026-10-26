use researchweave_analysis::AnalysisService;
use researchweave_core::{DispatchContext, OperationHandler};
use serde_json::{json, Value};
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
    let points = 5_000usize;
    let iterations = 20usize;
    let root = tempdir()?;
    let imports = root.path().join("imports");
    let store = root.path().join("store");
    fs::create_dir_all(&imports)?;

    let mut csv = String::with_capacity(points * 32);
    csv.push_str("x,y\n");
    for i in 0..points {
        let x = i as f64 / 10.0;
        let y = 2.0 + 0.75 * x + ((i * 17) % 31) as f64 / 100.0;
        csv.push_str(&format!("{x:.1},{y:.4}\n"));
    }
    let input = imports.join("plot.csv");
    fs::write(&input, csv.as_bytes())?;

    let service = AnalysisService::new(&store, &imports)?;
    let context = DispatchContext {
        request_id: Uuid::nil(),
        project_id: Uuid::nil(),
        actor: "performance-baseline".into(),
        expected_revision: None,
    };
    let imported = service.execute("dataset.import", &json!({"filename":"plot.csv"}), &context);
    if imported.get("status").is_some() {
        return Err(format!("plot fixture import failed: {imported}").into());
    }
    let dataset_id = imported["data"]["dataset_id"]
        .as_str()
        .ok_or("missing dataset_id")?;
    let revision = imported["data"]["revision"]
        .as_str()
        .ok_or("missing revision")?;
    let source_hash = imported["data"]["source_hash"]
        .as_str()
        .ok_or("missing source_hash")?;

    let plot_args = |format: &str| {
        json!({
            "dataset_id":dataset_id,
            "revision":revision,
            "kind":"scatter",
            "format":format,
            "x":"x",
            "y":"y",
            "width":720,
            "height":480
        })
    };

    for format in ["svg", "png"] {
        let warm = service.execute("plot.render", &plot_args(format), &context);
        if warm.get("status").is_some() || warm["data"]["n_complete"] != points {
            return Err(format!("{format} warm-up failed: {warm}").into());
        }
        black_box(warm);
    }

    let mut svg_ms = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = service.execute("plot.render", &plot_args("svg"), &context);
        svg_ms.push(started.elapsed().as_secs_f64() * 1000.0);
        if result.get("status").is_some() {
            return Err(format!("SVG render failed: {result}").into());
        }
        black_box(result);
    }

    let mut png_ms = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = service.execute("plot.render", &plot_args("png"), &context);
        png_ms.push(started.elapsed().as_secs_f64() * 1000.0);
        if result.get("status").is_some() {
            return Err(format!("PNG render failed: {result}").into());
        }
        black_box(result);
    }

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema":1,
            "fixture":{
                "points":points,
                "source_sha256":source_hash,
                "csv_bytes":fs::metadata(input)?.len(),
                "kind":"scatter",
                "width":720,
                "height":480,
            },
            "iterations":iterations,
            "svg":distribution(&svg_ms),
            "png":distribution(&png_ms),
            "notes":[
                "Fixture import is outside timed regions",
                "Each timed render loads the immutable dataset revision through AnalysisService",
                "One SVG and one PNG warm-up execution are excluded",
                "5000 points is the current enforced renderer resource ceiling"
            ]
        }))?
    );
    Ok(())
}
