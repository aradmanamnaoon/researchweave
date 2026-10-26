use researchweave_project::{ProjectInfo, ProjectStore};
use rusqlite::params;
use sha2::{Digest, Sha256};
use std::{env, fs, path::PathBuf};

const CREATED_AT: &str = "2026-10-26T00:00:00Z";

fn sha256_hex(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let destination = env::args_os()
        .nth(1)
        .map(PathBuf::from)
        .ok_or("usage: create_performance_fixture <destination>")?;
    if destination.exists() {
        return Err(format!("destination already exists: {}", destination.display()).into());
    }

    let info = ProjectInfo {
        id: "7eeb52c0-b4df-49a4-8cc6-05ddcc713f77".into(),
        title: "Synthetic medium performance fixture".into(),
        question: "How does a deterministic synthetic workload exercise project-open performance?"
            .into(),
        design: "computational".into(),
        locale: "en".into(),
        privacy: "private".into(),
        revision: 0,
        created_at: CREATED_AT.into(),
    };
    let mut store = ProjectStore::create(&destination, &info)?;

    // Keep the fixture synthetic and deterministic. The counts are large enough
    // to exercise the SQLite schema/indexes without embedding private research data.
    for index in 0..100_u32 {
        let body = format!(
            "Synthetic source {index}. This deterministic text is repeated to provide a realistic local object and note payload. {}",
            "research evidence workload ".repeat(40)
        );
        let digest = sha256_hex(body.as_bytes());
        let object_dir = destination.join("objects").join(&digest[..2]);
        fs::create_dir_all(&object_dir)?;
        fs::write(object_dir.join(&digest), body.as_bytes())?;
    }

    {
        let tx = store.transaction()?;
        for index in 0..100_u32 {
            let body = format!(
                "Synthetic source {index}. This deterministic text is repeated to provide a realistic local object and note payload. {}",
                "research evidence workload ".repeat(40)
            );
            let digest = sha256_hex(body.as_bytes());
            let source_id = format!("source-{index:04}");
            tx.execute(
                "INSERT INTO objects(digest,size) VALUES (?1,?2)",
                params![digest, body.len() as i64],
            )?;
            tx.execute(
                "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted) VALUES (?1,?2,'text/plain',?3,?4,'synthetic-performance-fixture',0)",
                params![source_id, format!("Synthetic source {index:04}"), digest, CREATED_AT],
            )?;
            tx.execute(
                "INSERT INTO document_text(source_id,body,extraction_version,body_hash) VALUES (?1,?2,'perf-v1',?3)",
                params![source_id, body, sha256_hex(body.as_bytes())],
            )?;
            for note in 0..5_u32 {
                tx.execute(
                    "INSERT INTO notes(id,source_id,title,body,created_at) VALUES (?1,?2,?3,?4,?5)",
                    params![
                        format!("note-{index:04}-{note:02}"),
                        source_id,
                        format!("Synthetic note {index:04}/{note:02}"),
                        format!(
                            "Deterministic note body for source {index:04}, note {note:02}. {}",
                            "analysis memo ".repeat(20)
                        ),
                        CREATED_AT
                    ],
                )?;
            }
        }

        for index in 0..500_u32 {
            let reference_id = format!("ref-{index:05}");
            tx.execute(
                "INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES (?1,?2,?3,?4,?5,'article','synthetic',?6,'{}','verified',?7)",
                params![
                    reference_id,
                    format!("Synthetic reference {index:05}"),
                    serde_json::json!([format!("Author {index:05}")]).to_string(),
                    2000_i64 + (index % 25) as i64,
                    format!("10.0000/perf.{index:05}"),
                    format!("Synthetic bibliographic record {index:05}"),
                    CREATED_AT
                ],
            )?;
            tx.execute(
                "INSERT INTO review_records(id,review_id,reference_id,study_id,stage) VALUES (?1,'perf-review',?2,?3,'title_abstract')",
                params![format!("record-{index:05}"), reference_id, format!("study-{index:05}")],
            )?;
            if index < 250 {
                tx.execute(
                    "INSERT INTO votes(review_id,record_id,reviewer,stage,decision,reason,recorded_at) VALUES ('perf-review',?1,'reviewer-a','title_abstract',?2,'synthetic benchmark vote',?3)",
                    params![
                        format!("record-{index:05}"),
                        if index % 3 == 0 { "include" } else { "exclude" },
                        CREATED_AT
                    ],
                )?;
            }
        }

        for version in 1..=8_i64 {
            tx.execute(
                "INSERT INTO protocols(id,version,title,body_json,rationale,author,recorded_at) VALUES ('perf-protocol',?1,'Synthetic protocol',?2,'performance fixture','fixture-builder',?3)",
                params![
                    version,
                    serde_json::json!({"version":version,"objective":"deterministic performance fixture","eligibility":["synthetic"]}).to_string(),
                    CREATED_AT
                ],
            )?;
        }

        let sections = [
            "Title",
            "Abstract",
            "Introduction",
            "Methods",
            "Results",
            "Discussion",
        ];
        for revision in 1..=6_i64 {
            for section in sections {
                tx.execute(
                    "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at) VALUES ('perf-paper',?1,?2,?3,?4,?5)",
                    params![
                        section,
                        revision,
                        format!("{section} revision {revision}. {}", "Synthetic manuscript paragraph. ".repeat(80)),
                        serde_json::json!(["ref-00000","ref-00001","ref-00002"]).to_string(),
                        CREATED_AT
                    ],
                )?;
            }
        }
        tx.commit()?;
    }

    drop(store);
    let reopened = ProjectStore::open(&destination)?;
    let verified = reopened.info()?;
    if verified.id != info.id || verified.title != info.title {
        return Err("fixture reopen verification failed".into());
    }
    println!("{}", destination.display());
    Ok(())
}
