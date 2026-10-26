use researchweave_ai::grounding::GroundingStore;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, hint::black_box, io::Write, path::PathBuf, time::Instant};

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

fn fixture_path() -> PathBuf {
    env::temp_dir().join(format!(
        "researchweave-retrieval-performance-{}",
        std::process::id()
    ))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let iterations = env::args()
        .nth(1)
        .map(|value| value.parse::<usize>())
        .transpose()?
        .unwrap_or(20);
    if iterations < 5 {
        return Err("iterations must be >= 5".into());
    }

    let root = fixture_path();
    if root.exists() {
        fs::remove_dir_all(&root)?;
    }
    fs::create_dir_all(&root)?;
    let file = root.join("grounding.json");

    let mut passages = Map::new();
    for index in 0..2_048usize {
        let citation_id = format!("cite-{index:04}");
        let marker = if index % 97 == 0 {
            " target resonance"
        } else {
            ""
        };
        let content = format!(
            "Deterministic host-indexed passage {index:04}. local lexical grounding alpha beta gamma delta epsilon zeta eta theta.{marker}"
        );
        passages.insert(
            citation_id.clone(),
            json!({
                "citation_id": citation_id,
                "source_id": format!("source-{index:04}"),
                "revision": "rev-0001",
                "content": content,
            }),
        );
    }
    let snapshot = json!({"projects":{"benchmark":Value::Object(passages)}});
    let bytes = serde_json::to_vec(&snapshot)?;
    let fixture_sha256 = hex::encode(Sha256::digest(&bytes));
    {
        let mut handle = fs::File::create(&file)?;
        handle.write_all(&bytes)?;
        handle.sync_all()?;
    }

    let store = GroundingStore::open(&file)?;
    let warm = store.search("benchmark", "target resonance", 20, 32_000)?;
    if warm["results"].as_array().map(Vec::len) != Some(20)
        || warm["policy"] != "lexical_host_indexed_project_only"
    {
        return Err(format!("warm retrieval returned unexpected data: {warm}").into());
    }
    black_box(warm);

    let mut samples = Vec::with_capacity(iterations);
    for _ in 0..iterations {
        let started = Instant::now();
        let result = store.search(
            black_box("benchmark"),
            black_box("target resonance"),
            20,
            32_000,
        )?;
        samples.push(started.elapsed().as_secs_f64() * 1000.0);
        if result["results"].as_array().map(Vec::len) != Some(20)
            || result["policy"] != "lexical_host_indexed_project_only"
        {
            return Err(format!("timed retrieval returned unexpected data: {result}").into());
        }
        black_box(result);
    }

    let output = serde_json::to_string_pretty(&json!({
        "schema": 1,
        "fixture": {
            "passages": 2_048,
            "snapshot_bytes": bytes.len(),
            "snapshot_sha256": fixture_sha256,
            "query": "target resonance",
            "matching_passages": 22,
            "returned_limit": 20,
        },
        "iterations": iterations,
        "grounding_search": distribution(&samples),
        "notes": [
            "The 2048-passage fixture is the current enforced per-project capacity; the previous 10k/100k target would contradict the live resource guard",
            "Fixture serialization, fsync, GroundingStore::open, and one warm-up query are outside the timed region",
            "Timed calls execute the live deterministic local lexical GroundingStore::search path; this is not semantic/vector RAG",
            "The byte budget remains at the live 32000-byte maximum"
        ]
    }))?;
    println!("{output}");
    fs::remove_dir_all(root)?;
    Ok(())
}
