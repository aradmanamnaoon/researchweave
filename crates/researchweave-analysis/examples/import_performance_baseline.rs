use researchweave_analysis::{AnalysisService, MAX_BYTES, MAX_ROWS};
use researchweave_core::{DispatchContext, OperationHandler};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufWriter, Write},
    path::Path,
    time::Instant,
};
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

fn write_fixture(
    path: &Path,
    target_bytes: u64,
) -> Result<(u64, usize, String), Box<dyn std::error::Error>> {
    let file = fs::File::create(path)?;
    let mut writer = BufWriter::new(file);
    let mut hasher = Sha256::new();
    let header = b"id,x1,x2,group,payload\n";
    writer.write_all(header)?;
    hasher.update(header);
    let mut bytes = header.len() as u64;
    let mut rows = 0usize;
    let payload = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJ";
    while rows < MAX_ROWS {
        let i = rows + 1;
        let x1 = (i % 10_000) as f64 / 100.0;
        let x2 = ((i * 37) % 9_973) as f64 / 80.0;
        let group = match i % 4 {
            0 => "A",
            1 => "B",
            2 => "C",
            _ => "D",
        };
        let line = format!("{i},{x1:.2},{x2:.3},{group},{payload}\n");
        if bytes + line.len() as u64 > target_bytes {
            break;
        }
        writer.write_all(line.as_bytes())?;
        hasher.update(line.as_bytes());
        bytes += line.len() as u64;
        rows += 1;
    }
    writer.flush()?;
    writer.get_ref().sync_all()?;
    if rows == 0 || bytes > target_bytes || bytes > MAX_BYTES {
        return Err("fixture generation violated import bounds".into());
    }
    Ok((bytes, rows, hex::encode(hasher.finalize())))
}

fn benchmark_import(
    root: &Path,
    imports: &Path,
    filename: &str,
    expected_rows: usize,
    iterations: usize,
) -> Result<(Value, String), Box<dyn std::error::Error>> {
    let warm_store = root.join(format!("warm-{filename}"));
    let warm = AnalysisService::new(&warm_store, imports)?;
    let context = DispatchContext {
        request_id: Uuid::nil(),
        project_id: Uuid::nil(),
        actor: "performance-baseline".into(),
        expected_revision: None,
    };
    let warm_result = warm.execute("dataset.import", &json!({"filename":filename}), &context);
    if warm_result.get("status").is_some()
        || warm_result["data"]["n"].as_u64() != Some(expected_rows as u64)
    {
        return Err(format!("warm import failed: {warm_result}").into());
    }
    let source_hash = warm_result["data"]["source_hash"]
        .as_str()
        .ok_or("warm import missing source hash")?
        .to_owned();
    drop(warm);
    fs::remove_dir_all(&warm_store)?;

    let mut samples = Vec::with_capacity(iterations);
    for iteration in 0..iterations {
        let store = root.join(format!("store-{filename}-{iteration}"));
        let service = AnalysisService::new(&store, imports)?;
        let context = DispatchContext {
            request_id: Uuid::from_u128(iteration as u128 + 1),
            project_id: Uuid::nil(),
            actor: "performance-baseline".into(),
            expected_revision: None,
        };
        let started = Instant::now();
        let result = service.execute("dataset.import", &json!({"filename":filename}), &context);
        let elapsed = started.elapsed().as_secs_f64() * 1000.0;
        if result.get("status").is_some()
            || result["data"]["n"].as_u64() != Some(expected_rows as u64)
            || result["data"]["source_hash"].as_str() != Some(source_hash.as_str())
        {
            return Err(format!("timed import failed: {result}").into());
        }
        samples.push(elapsed);
        drop(service);
        fs::remove_dir_all(store)?;
    }
    Ok((distribution(&samples), source_hash))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = tempdir()?;
    let imports = root.path().join("imports");
    fs::create_dir_all(&imports)?;

    let ten_target = 10_u64 * 1024 * 1024;
    let forty_five_target = 45_u64 * 1024 * 1024;
    let ten_path = imports.join("synthetic-10mib.csv");
    let forty_five_path = imports.join("synthetic-45mib.csv");
    let (ten_bytes, ten_rows, ten_file_hash) = write_fixture(&ten_path, ten_target)?;
    let (forty_five_bytes, forty_five_rows, forty_five_file_hash) =
        write_fixture(&forty_five_path, forty_five_target)?;

    let (ten_result, ten_source_hash) =
        benchmark_import(root.path(), &imports, "synthetic-10mib.csv", ten_rows, 10)?;
    let (forty_five_result, forty_five_source_hash) = benchmark_import(
        root.path(),
        &imports,
        "synthetic-45mib.csv",
        forty_five_rows,
        5,
    )?;
    if ten_file_hash != ten_source_hash || forty_five_file_hash != forty_five_source_hash {
        return Err("service source hash did not match fixture bytes".into());
    }

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema":1,
            "limits":{
                "max_input_bytes":MAX_BYTES,
                "max_rows":MAX_ROWS,
            },
            "fixtures":{
                "10_mib":{
                    "bytes":ten_bytes,
                    "rows":ten_rows,
                    "sha256":ten_file_hash,
                },
                "45_mib":{
                    "bytes":forty_five_bytes,
                    "rows":forty_five_rows,
                    "sha256":forty_five_file_hash,
                }
            },
            "import_10_mib":ten_result,
            "import_45_mib":forty_five_result,
            "notes":[
                "Fixture generation and warm-up imports are outside timed regions",
                "Each timed run uses a fresh DatasetStore and includes parse, immutable revision construction, validation, durable JSON write, sync_all, and rename",
                "Each store is deleted only after the timed operation completes",
                "45 MiB is intentionally below the current 50 MiB import ceiling"
            ]
        }))?
    );
    Ok(())
}
