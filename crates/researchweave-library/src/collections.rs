//! Project-scoped reference collections and tags backed by the shared project schema.
use super::{bounded, required};
use chrono::{SecondsFormat, Utc};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension, Transaction};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use uuid::Uuid;

const MAX_BATCH: usize = 500;

fn hash(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn strings(
    args: &Value,
    key: &str,
    max_items: usize,
    max_len: usize,
) -> Result<Vec<String>, String> {
    let values = args
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{key} array required"))?;
    if values.is_empty() || values.len() > max_items {
        return Err(format!("{key} batch outside bounds"));
    }
    let mut output = Vec::with_capacity(values.len());
    let mut seen = HashSet::new();
    for value in values {
        let value = value
            .as_str()
            .map(str::trim)
            .filter(|value| !value.is_empty() && value.len() <= max_len && !value.contains('\0'))
            .ok_or_else(|| format!("invalid {key} entry"))?;
        if !seen.insert(value.to_owned()) {
            return Err(format!("duplicate {key} entry"));
        }
        output.push(value.to_owned());
    }
    Ok(output)
}

pub(super) fn current_revision(store: &ProjectStore, ctx: &DispatchContext) -> Result<i64, String> {
    let revision = store.info().map_err(|_| "project unavailable")?.revision;
    if ctx.expected_revision != u64::try_from(revision).ok() {
        return Err("expected_revision required and must match current revision".into());
    }
    Ok(revision)
}

pub(super) fn mutate<T>(
    store: &mut ProjectStore,
    op: &str,
    payload: &Value,
    ctx: &DispatchContext,
    apply: impl FnOnce(&Transaction<'_>, &str) -> Result<T, String>,
) -> Result<(T, i64), String> {
    let expected = current_revision(store, ctx)?;
    let tx = store.transaction().map_err(|_| "transaction failed")?;
    let current: i64 = tx
        .query_row("SELECT revision FROM project", [], |row| row.get(0))
        .map_err(|_| "revision unavailable")?;
    if current != expected {
        return Err("stale project revision".into());
    }
    let request_id = ctx.request_id.to_string();
    let seen: i64 = tx
        .query_row(
            "SELECT count(*) FROM events WHERE request_id=?1",
            [&request_id],
            |row| row.get(0),
        )
        .map_err(|_| "replay check failed")?;
    if seen != 0 {
        return Err("request already applied".into());
    }
    let now = Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true);
    let value = apply(&tx, &now)?;
    let payload_json = serde_json::to_string(payload).map_err(|_| "payload encode failed")?;
    let payload_hash = hash(payload_json.as_bytes());
    let predecessor: String = tx
        .query_row(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1",
            [],
            |row| row.get(0),
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
        "INSERT INTO events VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
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
    .map_err(|_| "event insertion failed")?;
    if tx
        .execute(
            "UPDATE project SET revision=?1 WHERE revision=?2",
            params![next, current],
        )
        .map_err(|_| "revision update failed")?
        != 1
    {
        return Err("revision changed".into());
    }
    tx.commit().map_err(|_| "commit failed")?;
    Ok((value, next))
}

pub(super) fn exists(
    store: &ProjectStore,
    table: &str,
    id_column: &str,
    id: &str,
) -> Result<bool, String> {
    let sql = format!("SELECT count(*) FROM {table} WHERE {id_column}=?1");
    store
        .connection()
        .query_row(&sql, [id], |row| row.get::<_, i64>(0))
        .map(|count| count == 1)
        .map_err(|_| "lookup failed".into())
}

fn collection_tree(store: &ProjectStore) -> Result<Value, String> {
    type Row = (String, Option<String>, String, String, i64);
    let mut statement = store
        .connection()
        .prepare(
            "SELECT c.id,c.parent_id,c.name,c.created_at,COUNT(m.reference_id)
             FROM library_collections c
             LEFT JOIN collection_members m ON m.collection_id=c.id
             GROUP BY c.id,c.parent_id,c.name,c.created_at
             ORDER BY c.name,c.id",
        )
        .map_err(|_| "collection tree unavailable")?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, i64>(4)?,
            ))
        })
        .map_err(|_| "collection tree unavailable")?
        .collect::<Result<Vec<Row>, _>>()
        .map_err(|_| "collection tree unavailable")?;
    let by_id: HashMap<String, Row> = rows
        .iter()
        .cloned()
        .map(|row| (row.0.clone(), row))
        .collect();
    for row in &rows {
        let mut cursor = row.1.clone();
        let mut seen = HashSet::from([row.0.clone()]);
        while let Some(parent) = cursor {
            if !seen.insert(parent.clone()) {
                return Err("collection tree contains cycle".into());
            }
            let parent_row = by_id
                .get(&parent)
                .ok_or("collection tree contains orphan")?;
            cursor = parent_row.1.clone();
        }
    }
    let mut children: HashMap<Option<String>, Vec<String>> = HashMap::new();
    for row in &rows {
        children
            .entry(row.1.clone())
            .or_default()
            .push(row.0.clone());
    }
    fn build(
        id: &str,
        by_id: &HashMap<String, Row>,
        children: &HashMap<Option<String>, Vec<String>>,
    ) -> Result<Value, String> {
        let row = by_id.get(id).ok_or("collection missing")?;
        let mut nested = Vec::new();
        if let Some(ids) = children.get(&Some(id.to_owned())) {
            for child in ids {
                nested.push(build(child, by_id, children)?);
            }
        }
        Ok(json!({
            "id":row.0,
            "parent_id":row.1,
            "name":row.2,
            "created_at":row.3,
            "member_count":row.4,
            "children":nested
        }))
    }
    let mut roots = Vec::new();
    for id in children.get(&None).into_iter().flatten() {
        roots.push(build(id, &by_id, &children)?);
    }
    if !rows.is_empty() && roots.is_empty() {
        return Err("collection tree has no root".into());
    }
    Ok(json!({"collections":roots}))
}

fn collection_search(store: &ProjectStore, args: &Value) -> Result<Vec<Value>, String> {
    let collection_id = args.get("collection_id").and_then(Value::as_str);
    let tag = args
        .get("tag")
        .and_then(Value::as_str)
        .map(|value| value.trim().to_lowercase());
    let year_from = args.get("year_from").and_then(Value::as_i64);
    let year_to = args.get("year_to").and_then(Value::as_i64);
    if year_from.is_some_and(|year| !(1..=9999).contains(&year))
        || year_to.is_some_and(|year| !(1..=9999).contains(&year))
        || year_from.zip(year_to).is_some_and(|(from, to)| from > to)
    {
        return Err("invalid year range".into());
    }
    if collection_id.is_some_and(|id| id.is_empty() || id.len() > 128)
        || tag
            .as_deref()
            .is_some_and(|value| value.is_empty() || value.len() > 80)
    {
        return Err("invalid collection filter".into());
    }
    let text = args.get("text").and_then(Value::as_str);
    if text.is_some_and(|value| value.trim().is_empty() || value.len() > 200) {
        return Err("invalid search text".into());
    }
    let pattern = text.map(|value| {
        let escaped = value
            .replace('\\', "\\\\")
            .replace('%', "\\%")
            .replace('_', "\\_");
        format!("%{escaped}%")
    });
    let limit = bounded(args, "limit", 200, 500)?;
    let mut statement = store
        .connection()
        .prepare(
            "SELECT DISTINCT r.id,r.title,r.authors_json,r.year,r.doi,r.kind,r.status,
                    ra.canonical_id,ra.reason
             FROM reference r
             LEFT JOIN reference_alias ra ON ra.original_id=r.id
             LEFT JOIN collection_members cm ON cm.reference_id=r.id
             LEFT JOIN reference_tags rt ON rt.reference_id=r.id
             WHERE (?1 IS NULL OR cm.collection_id=?1)
               AND (?2 IS NULL OR rt.tag=?2)
               AND (?3 IS NULL OR r.year>=?3)
               AND (?4 IS NULL OR r.year<=?4)
               AND (?5 IS NULL OR r.title LIKE ?5 ESCAPE '\\' OR r.authors_json LIKE ?5 ESCAPE '\\')
             ORDER BY r.year DESC,r.title,r.id LIMIT ?6",
        )
        .map_err(|_| "collection search unavailable")?;
    let rows = statement
        .query_map(
            params![collection_id, tag, year_from, year_to, pattern, limit],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<i64>>(3)?,
                    row.get::<_, Option<String>>(4)?,
                    row.get::<_, String>(5)?,
                    row.get::<_, String>(6)?,
                    row.get::<_, Option<String>>(7)?,
                    row.get::<_, Option<String>>(8)?,
                ))
            },
        )
        .map_err(|_| "collection search unavailable")?;
    let mut records = Vec::new();
    for row in rows {
        let (id, title, authors, year, doi, kind, status, canonical, alias_reason) =
            row.map_err(|_| "collection search row invalid")?;
        let authors: Value =
            serde_json::from_str(&authors).map_err(|_| "reference authors invalid")?;
        records.push(json!({
            "id":id,
            "canonical_id":canonical.clone().unwrap_or_else(|| id.clone()),
            "is_alias":canonical.is_some(),
            "alias_reason":alias_reason,
            "title":title,
            "authors":authors,
            "year":year,
            "doi":doi,
            "kind":kind,
            "status":status
        }));
    }
    Ok(records)
}

fn csv_cell(value: &str) -> String {
    if value.contains([',', '"', '\r', '\n']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_owned()
    }
}

pub(super) fn run(
    store: &mut ProjectStore,
    op: &str,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    match op {
        "library.collection_create" => {
            let name = required(args, "name", 200)?.trim();
            let parent_id = args.get("parent_id").and_then(Value::as_str);
            if parent_id.is_some_and(|id| id.is_empty() || id.len() > 128) {
                return Err("invalid parent_id".into());
            }
            if let Some(parent_id) = parent_id {
                if !exists(store, "library_collections", "id", parent_id)? {
                    return Err("parent collection not found".into());
                }
            }
            let revision = current_revision(store, ctx)?;
            let collection_id = Uuid::new_v4().to_string();
            let payload = json!({
                "collection_id":collection_id,
                "parent_id":parent_id,
                "name":name
            });
            if preview {
                return Ok(json!({"preview":true,"would_create":payload,"revision":revision}));
            }
            let (_, next) = mutate(store, op, &payload, ctx, |tx, now| {
                tx.execute(
                    "INSERT INTO library_collections(id,parent_id,name,created_at) VALUES (?1,?2,?3,?4)",
                    params![collection_id, parent_id, name, now],
                )
                .map_err(|_| "collection name already exists under this parent")?;
                Ok(())
            })?;
            Ok(json!({
                "collection_id":collection_id,
                "parent_id":parent_id,
                "name":name,
                "revision":next
            }))
        }
        "library.collection_add" | "library.collection_remove" => {
            let collection_id = required(args, "collection_id", 128)?;
            let reference_ids = strings(args, "reference_ids", MAX_BATCH, 128)?;
            if !exists(store, "library_collections", "id", collection_id)? {
                return Err("collection not found".into());
            }
            for reference_id in &reference_ids {
                if !exists(store, "reference", "id", reference_id)? {
                    return Err("reference not found".into());
                }
            }
            let revision = current_revision(store, ctx)?;
            let payload = json!({
                "collection_id":collection_id,
                "reference_ids":reference_ids
            });
            if preview {
                return Ok(json!({
                    "preview":true,
                    "would_apply":op,
                    "payload":payload,
                    "revision":revision
                }));
            }
            let (_, next) = mutate(store, op, &payload, ctx, |tx, now| {
                for reference_id in &reference_ids {
                    if op == "library.collection_add" {
                        tx.execute(
                            "INSERT OR IGNORE INTO collection_members(collection_id,reference_id,added_at) VALUES (?1,?2,?3)",
                            params![collection_id, reference_id, now],
                        )
                        .map_err(|_| "collection membership insert failed")?;
                    } else {
                        tx.execute(
                            "DELETE FROM collection_members WHERE collection_id=?1 AND reference_id=?2",
                            params![collection_id, reference_id],
                        )
                        .map_err(|_| "collection membership removal failed")?;
                    }
                }
                Ok(())
            })?;
            Ok(json!({
                "collection_id":collection_id,
                "members_requested":reference_ids.len(),
                "revision":next
            }))
        }
        "library.reference_tag" => {
            let reference_ids = strings(args, "reference_ids", MAX_BATCH, 128)?;
            let raw_tags = strings(args, "tags", 50, 80)?;
            let tags: Vec<String> = raw_tags.into_iter().map(|tag| tag.to_lowercase()).collect();
            if tags.iter().collect::<HashSet<_>>().len() != tags.len() {
                return Err("tags must be unique after normalization".into());
            }
            for reference_id in &reference_ids {
                if !exists(store, "reference", "id", reference_id)? {
                    return Err("reference not found".into());
                }
            }
            let revision = current_revision(store, ctx)?;
            let payload = json!({"reference_ids":reference_ids,"tags":tags});
            if preview {
                return Ok(json!({"preview":true,"would_tag":payload,"revision":revision}));
            }
            let (_, next) = mutate(store, op, &payload, ctx, |tx, now| {
                for reference_id in &reference_ids {
                    for tag in &tags {
                        tx.execute(
                            "INSERT OR IGNORE INTO reference_tags(reference_id,tag,added_at) VALUES (?1,?2,?3)",
                            params![reference_id, tag, now],
                        )
                        .map_err(|_| "reference tag insert failed")?;
                    }
                }
                Ok(())
            })?;
            Ok(json!({"reference_ids":reference_ids,"tags":tags,"revision":next}))
        }
        "library.collection_tree" => collection_tree(store),
        "library.collection_search" => {
            let records = collection_search(store, args)?;
            Ok(json!({"records":records,"count":records.len()}))
        }
        "library.collection_export" => {
            let collection_id = required(args, "collection_id", 128)?;
            if !exists(store, "library_collections", "id", collection_id)? {
                return Err("collection not found".into());
            }
            let records =
                collection_search(store, &json!({"collection_id":collection_id,"limit":500}))?;
            let mut text = String::from(
                "id,canonical_id,is_alias,alias_reason,title,authors,year,doi,kind,status\r\n",
            );
            for record in &records {
                let authors = record["authors"]
                    .as_array()
                    .map(|values| {
                        values
                            .iter()
                            .filter_map(Value::as_str)
                            .collect::<Vec<_>>()
                            .join("; ")
                    })
                    .unwrap_or_default();
                let values = [
                    record["id"].as_str().unwrap_or_default().to_owned(),
                    record["canonical_id"]
                        .as_str()
                        .unwrap_or_default()
                        .to_owned(),
                    record["is_alias"].as_bool().unwrap_or(false).to_string(),
                    record["alias_reason"]
                        .as_str()
                        .unwrap_or_default()
                        .to_owned(),
                    record["title"].as_str().unwrap_or_default().to_owned(),
                    authors,
                    record["year"]
                        .as_i64()
                        .map(|value| value.to_string())
                        .unwrap_or_default(),
                    record["doi"].as_str().unwrap_or_default().to_owned(),
                    record["kind"].as_str().unwrap_or_default().to_owned(),
                    record["status"].as_str().unwrap_or_default().to_owned(),
                ];
                text.push_str(
                    &values
                        .iter()
                        .map(|value| csv_cell(value))
                        .collect::<Vec<_>>()
                        .join(","),
                );
                text.push_str("\r\n");
            }
            Ok(json!({
                "format":"csv",
                "text":text,
                "records":records.len(),
                "collection_id":collection_id
            }))
        }
        _ => Err("unsupported collection operation".into()),
    }
}
