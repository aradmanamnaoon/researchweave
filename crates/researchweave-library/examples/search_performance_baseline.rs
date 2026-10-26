use researchweave_core::{DispatchContext, OperationHandler};
use researchweave_library::LibraryHandler;
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
    let project_id = Uuid::from_u128(0x1001);
    let project_path = root.path().join("library-search-project");
    let mut store = ProjectStore::create(
        &project_path,
        &ProjectInfo {
            id: project_id.to_string(),
            title: "Synthetic library search performance fixture".into(),
            question: "How quickly does bounded literal search scan the local library?".into(),
            design: "computational".into(),
            locale: "en".into(),
            privacy: "private".into(),
            revision: 0,
            created_at: "2026-10-26T00:00:00Z".into(),
        },
    )?;

    let mut fixture_hasher = Sha256::new();
    {
        let tx = store.transaction()?;
        {
            let mut insert_object =
                tx.prepare("INSERT INTO objects(digest,size) VALUES (?1,?2)")?;
            let mut insert_source = tx.prepare(
                "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted) VALUES (?1,?2,'text/plain',?3,'2026-10-26T00:00:00Z','synthetic-performance',0)",
            )?;
            let mut insert_text = tx.prepare(
                "INSERT INTO document_text(source_id,body,extraction_version,body_hash) VALUES (?1,?2,'performance-v1',?3)",
            )?;
            for index in 0..10_000usize {
                let source_id = format!("source-{index:05}");
                let title = format!("Synthetic source {index:05}");
                let marker = if index == 9_999 {
                    " needle-final-9999"
                } else {
                    ""
                };
                let body = format!(
                    "Deterministic local research passage {index:05}. Persian-safe literal matching baseline. alpha beta gamma delta epsilon.{marker}"
                );
                let digest = hex::encode(Sha256::digest(body.as_bytes()));
                fixture_hasher.update(source_id.as_bytes());
                fixture_hasher.update([0]);
                fixture_hasher.update(title.as_bytes());
                fixture_hasher.update([0]);
                fixture_hasher.update(body.as_bytes());
                insert_object.execute((&digest, body.len() as i64))?;
                insert_source.execute((&source_id, &title, &digest))?;
                insert_text.execute((&source_id, &body, &digest))?;
            }
        }
        tx.commit()?;
    }
    drop(store);

    let canonical_project = project_path.canonicalize()?;
    let handler = LibraryHandler::bound(project_id, &canonical_project)?;
    let context = DispatchContext {
        request_id: Uuid::nil(),
        project_id,
        actor: "performance-baseline".into(),
        expected_revision: Some(0),
    };
    let args = json!({
        "project_id": project_id.to_string(),
        "query": "needle-final-9999",
        "limit": 20,
    });

    let warm = handler.execute("search.query", &args, &context);
    if warm["status"] != "ok"
        || warm["data"]["count"].as_u64() != Some(1)
        || warm["data"]["records"][0]["source_id"] != "source-09999"
    {
        return Err(format!("warm search returned unexpected data: {warm}").into());
    }
    black_box(warm);

    let mut samples = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = handler.execute("search.query", black_box(&args), black_box(&context));
        samples.push(started.elapsed().as_secs_f64() * 1000.0);
        if result["status"] != "ok"
            || result["data"]["count"].as_u64() != Some(1)
            || result["data"]["records"][0]["source_id"] != "source-09999"
        {
            return Err(format!("timed search returned unexpected data: {result}").into());
        }
        black_box(result);
    }

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema": 1,
            "fixture": {
                "sources": 10_000,
                "logical_sha256": hex::encode(fixture_hasher.finalize()),
                "query": "needle-final-9999",
                "expected_match": "source-09999",
                "placement": "single match in lexicographically final source; forces full bounded 10000-source scan",
            },
            "iterations": iterations,
            "search_query": distribution(&samples),
            "notes": [
                "Fixture construction and one warm-up search are outside the timed region",
                "Timed calls use LibraryHandler::execute(\"search.query\") and therefore reopen/validate the project and verify the event chain before scanning",
                "Search is literal Unicode lowercase substring matching, not semantic ranking or SQLite FTS",
                "The benchmark preserves the live 10000-source scan cap"
            ]
        }))?
    );
    Ok(())
}
