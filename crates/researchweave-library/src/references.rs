//! Schema-native references: validated registration and lossless raw export.
use super::{bounded, bounded_offset, required};
use chrono::{SecondsFormat, Utc};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use uuid::Uuid;

fn hash(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

pub(super) fn run(
    store: &mut ProjectStore,
    op: &str,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    if op == "library.reference_add" {
        let title = required(args, "title", 300)?;
        let format = required(args, "format", 32)?;
        if !["bibtex", "ris", "csl-json"].contains(&format) {
            return Err("unsupported reference format".into());
        }
        let raw = required(args, "raw", 256_000)?;
        let authors = args
            .get("authors")
            .and_then(Value::as_array)
            .ok_or("authors array required")?;
        if authors.len() > 100
            || authors.iter().any(|a| {
                a.as_str()
                    .is_none_or(|s| s.trim().is_empty() || s.len() > 300)
            })
        {
            return Err("invalid authors".into());
        }
        let year = match args.get("year") {
            None | Some(Value::Null) => None,
            Some(v) => Some(
                v.as_i64()
                    .filter(|y| (1000..=3000).contains(y))
                    .ok_or("invalid year")?,
            ),
        };
        let doi = args
            .get("doi")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|s| !s.is_empty());
        if doi.is_some_and(|s| s.len() > 300 || s.chars().any(char::is_whitespace)) {
            return Err("invalid DOI".into());
        }
        let kind = required(args, "kind", 64)?;
        let metadata = args.get("metadata").cloned().unwrap_or_else(|| json!({}));
        if !metadata.is_object() || metadata.to_string().len() > 32768 {
            return Err("invalid reference metadata".into());
        }
        let info = store.info().map_err(|_| "project unavailable")?;
        if ctx.expected_revision != u64::try_from(info.revision).ok() {
            return Err("expected_revision required and must match current revision".into());
        }
        let id = Uuid::new_v4().to_string();
        let content_hash = hash(raw.as_bytes());
        let payload =
            json!({"reference_id":id,"title":title,"format":format,"raw_sha256":content_hash});
        if preview {
            return Ok(
                json!({"preview":true,"would_register":{"title":title,"format":format,"raw_sha256":content_hash},"revision":info.revision}),
            );
        }
        let tx = store.transaction().map_err(|_| "transaction failed")?;
        let current: i64 = tx
            .query_row("SELECT revision FROM project", [], |r| r.get(0))
            .map_err(|_| "revision unavailable")?;
        if current != info.revision {
            return Err("stale project revision".into());
        }
        let request_id = ctx.request_id.to_string();
        let seen: i64 = tx
            .query_row(
                "SELECT count(*) FROM events WHERE request_id=?",
                [&request_id],
                |r| r.get(0),
            )
            .map_err(|_| "replay check failed")?;
        if seen != 0 {
            return Err("request already applied".into());
        }
        let now = Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true);
        tx.execute("INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES (?,?,?,?,?,?,?,?,?,'unverified',?)",
          params![id,title,serde_json::to_string(authors).map_err(|_|"authors encode failed")?,year,doi,kind,format,raw,metadata.to_string(),now]).map_err(|_|"reference insert failed")?;
        let payload_json = payload.to_string();
        let payload_hash = hash(payload_json.as_bytes());
        let predecessor: String = tx
            .query_row(
                "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1",
                [],
                |r| r.get(0),
            )
            .optional()
            .map_err(|_| "event query failed")?
            .unwrap_or_else(|| "0".repeat(64));
        let next = current.checked_add(1).ok_or("revision overflow")?;
        let event_hash = hash(
            &serde_json::to_vec(&json!([
                next,
                request_id,
                op,
                ctx.actor,
                payload_hash,
                predecessor,
                now
            ]))
            .map_err(|_| "event encode failed")?,
        );
        tx.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
            params![
                next,
                request_id,
                op,
                ctx.actor,
                payload_json,
                payload_hash,
                predecessor,
                event_hash,
                now
            ],
        )
        .map_err(|_| "event insert failed")?;
        if tx
            .execute(
                "UPDATE project SET revision=? WHERE revision=?",
                params![next, current],
            )
            .map_err(|_| "revision update failed")?
            != 1
        {
            return Err("revision changed".into());
        }
        tx.commit().map_err(|_| "commit failed")?;
        Ok(
            json!({"reference_id":id,"project_revision":next,"raw_sha256":content_hash,"status":"unverified"}),
        )
    } else if op == "library.references" {
        let limit = bounded(args, "limit", 50, 200)?;
        let offset = bounded_offset(args)?;
        let mut stmt=store.connection().prepare("SELECT id,title,authors_json,year,doi,kind,format,status,imported_at FROM reference ORDER BY imported_at,id LIMIT ? OFFSET ?").map_err(|_|"reference query failed")?;
        let rows = stmt
            .query_map(params![limit, offset], |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, Option<i64>>(3)?,
                    r.get::<_, Option<String>>(4)?,
                    r.get::<_, String>(5)?,
                    r.get::<_, String>(6)?,
                    r.get::<_, String>(7)?,
                    r.get::<_, String>(8)?,
                ))
            })
            .map_err(|_| "reference query failed")?;
        let mut references = Vec::new();
        for row in rows {
            let (id, title, authors, year, doi, kind, format, status, imported_at) =
                row.map_err(|_| "reference row corrupt")?;
            let authors: Value = serde_json::from_str(&authors).map_err(|_| "authors corrupt")?;
            references.push(json!({"reference_id":id,"title":title,"authors":authors,"year":year,"doi":doi,"kind":kind,"format":format,"status":status,"imported_at":imported_at}));
        }
        Ok(json!({"references":references,"count":references.len(),"limit":limit,"offset":offset}))
    } else {
        let id = required(args, "reference_id", 128)?;
        let result: Option<(String, String, String, String)> = store
            .connection()
            .query_row(
                "SELECT title,format,raw,status FROM reference WHERE id=?",
                [id],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
            )
            .optional()
            .map_err(|_| "reference query failed")?;
        let (title, format, raw, status) = result.ok_or("reference not found")?;
        Ok(
            json!({"reference_id":id,"title":title,"format":format,"raw":raw,"raw_sha256":hash(raw.as_bytes()),"status":status}),
        )
    }
}
