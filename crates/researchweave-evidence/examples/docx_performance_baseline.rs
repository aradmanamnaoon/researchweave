use researchweave_core::{DispatchContext, OperationHandler};
use researchweave_evidence::EvidenceHandler;
use researchweave_project::{ProjectInfo, ProjectStore};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{hint::black_box, time::Instant};
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

fn body(paragraphs: usize) -> String {
    (0..paragraphs)
        .map(|index| {
            format!(
                "Paragraph {:04}. Deterministic synthetic manuscript content for native DOCX export performance. This paragraph preserves Unicode: پژوهش داده شواهد. Citation token [REF-{:04}].",
                index + 1,
                (index % 97) + 1
            )
        })
        .collect::<Vec<_>>()
        .join("\n\n")
}

fn benchmark(
    handler: &EvidenceHandler,
    context: &DispatchContext,
    project_id: Uuid,
    manuscript_id: &str,
    paragraphs: usize,
    iterations: usize,
) -> Result<Value, Box<dyn std::error::Error>> {
    let args = json!({
        "project_id": project_id.to_string(),
        "manuscript_id": manuscript_id,
        "format": "docx",
    });
    let warm = handler.execute("writing.manuscript_export", &args, context);
    let expected_sha = warm["data"]["sha256"]
        .as_str()
        .ok_or_else(|| format!("warm DOCX export failed: {warm}"))?
        .to_owned();
    if warm["status"] != "ok"
        || warm["data"]["format"] != "docx"
        || warm["data"]["byte_length"].as_u64().unwrap_or_default() == 0
    {
        return Err(format!("warm DOCX export returned unexpected data: {warm}").into());
    }
    black_box(warm);

    let mut samples = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = handler.execute(
            "writing.manuscript_export",
            black_box(&args),
            black_box(context),
        );
        samples.push(started.elapsed().as_secs_f64() * 1000.0);
        if result["status"] != "ok"
            || result["data"]["sha256"].as_str() != Some(expected_sha.as_str())
            || result["data"]["verified_from_persisted_revisions"] != true
        {
            return Err(format!("timed DOCX export returned unexpected data: {result}").into());
        }
        black_box(result);
    }

    Ok(json!({
        "paragraphs": paragraphs,
        "docx_sha256": expected_sha,
        "timing": distribution(&samples),
    }))
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
    let project_id = Uuid::from_u128(0x2001);
    let project_path = root.path().join("docx-performance-project");
    let store = ProjectStore::create(
        &project_path,
        &ProjectInfo {
            id: project_id.to_string(),
            title: "Synthetic DOCX performance fixture".into(),
            question: "How quickly can persisted manuscript revisions export to DOCX?".into(),
            design: "computational".into(),
            locale: "en".into(),
            privacy: "private".into(),
            revision: 0,
            created_at: "2026-10-26T00:00:00Z".into(),
        },
    )?;

    let body_400 = body(400);
    let body_2400 = body(2_400);
    store.connection().execute(
        "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at) VALUES (?1,'01-main',1,?2,'[]','2026-10-26T00:00:00Z')",
        ("paper-400", &body_400),
    )?;
    store.connection().execute(
        "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at) VALUES (?1,'01-main',1,?2,'[]','2026-10-26T00:00:00Z')",
        ("paper-2400", &body_2400),
    )?;
    let mut fixture_hasher = Sha256::new();
    fixture_hasher.update(body_400.as_bytes());
    fixture_hasher.update([0]);
    fixture_hasher.update(body_2400.as_bytes());
    let fixture_sha256 = hex::encode(fixture_hasher.finalize());
    drop(store);

    let handler = EvidenceHandler::bound(project_id, project_path.canonicalize()?)?;
    let context = DispatchContext {
        request_id: Uuid::nil(),
        project_id,
        actor: "performance-baseline".into(),
        expected_revision: Some(0),
    };
    let result_400 = benchmark(&handler, &context, project_id, "paper-400", 400, iterations)?;
    let result_2400 = benchmark(
        &handler,
        &context,
        project_id,
        "paper-2400",
        2_400,
        iterations,
    )?;

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema": 1,
            "fixture": {
                "logical_sha256": fixture_sha256,
                "documents": [
                    {"manuscript_id":"paper-400","paragraphs":400},
                    {"manuscript_id":"paper-2400","paragraphs":2400}
                ],
                "unicode": true,
                "persisted_latest_revisions": true,
            },
            "iterations_per_document": iterations,
            "docx_400_paragraphs": result_400,
            "docx_2400_paragraphs": result_2400,
            "notes": [
                "Fixture creation and one warm-up export per document are outside the timed region",
                "Timed calls execute EvidenceHandler::execute(\"writing.manuscript_export\") with format=docx and re-read persisted latest manuscript revisions",
                "The deterministic DOCX bytes are hashed and compared across every timed iteration",
                "The long fixture is described by paragraph count rather than an invented page count because the current exporter does not run a pagination/layout engine",
                "Export includes DOCX generation plus receipt/base64 generation and the live 16 MiB output guard"
            ]
        }))?
    );
    Ok(())
}
