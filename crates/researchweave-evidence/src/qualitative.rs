//! Schema-backed qualitative codebook and anchored coding operations.
use super::{digest, mutate, required_text};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashSet};

fn state(store: &ProjectStore) -> Result<(Value, String), String> {
    let mut codes_stmt = store
        .connection()
        .prepare(
            "SELECT id,name,description,parent_id,active,created_at
             FROM qualitative_codes ORDER BY id",
        )
        .map_err(|_| "qualitative codebook unavailable")?;
    let codes = codes_stmt
        .query_map([], |row| {
            Ok(json!({
                "code_id":row.get::<_,String>(0)?,
                "name":row.get::<_,String>(1)?,
                "description":row.get::<_,String>(2)?,
                "parent":row.get::<_,Option<String>>(3)?,
                "active":row.get::<_,i64>(4)? != 0,
                "created_at":row.get::<_,String>(5)?
            }))
        })
        .map_err(|_| "qualitative codebook unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "qualitative codebook corrupted")?;

    let mut annotations_stmt = store
        .connection()
        .prepare(
            "SELECT id,source_id,code_id,coder,start,end,quote,body_hash,recorded_at
             FROM qualitative_annotations ORDER BY id",
        )
        .map_err(|_| "qualitative annotations unavailable")?;
    let annotations = annotations_stmt
        .query_map([], |row| {
            Ok(json!({
                "unit_id":row.get::<_,String>(0)?,
                "source_id":row.get::<_,String>(1)?,
                "code_id":row.get::<_,String>(2)?,
                "coder":row.get::<_,String>(3)?,
                "start":row.get::<_,i64>(4)?,
                "end":row.get::<_,i64>(5)?,
                "quote":row.get::<_,String>(6)?,
                "body_hash":row.get::<_,String>(7)?,
                "recorded_at":row.get::<_,String>(8)?
            }))
        })
        .map_err(|_| "qualitative annotations unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "qualitative annotations corrupted")?;

    let mut transcript_stmt=store.connection().prepare(
        "SELECT source_id,case_id,confidential,body_hash,recorded_at FROM qualitative_transcripts ORDER BY source_id"
    ).map_err(|_|"qualitative transcripts unavailable")?;
    let transcripts = transcript_stmt
        .query_map([], |row| {
            Ok(json!({
                "source_id":row.get::<_,String>(0)?,"case_id":row.get::<_,String>(1)?,
                "confidential":row.get::<_,i64>(2)? != 0,"body_hash":row.get::<_,String>(3)?,
                "recorded_at":row.get::<_,String>(4)?
            }))
        })
        .map_err(|_| "qualitative transcripts unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "qualitative transcripts corrupted")?;
    let value = json!({"codes":codes,"annotations":annotations,"transcripts":transcripts});
    let encoded =
        serde_json::to_vec(&value).map_err(|_| "qualitative state serialization failed")?;
    let content_hash = digest(&encoded);
    Ok((value, content_hash))
}

fn expected_hash(store: &ProjectStore, args: &Value) -> Result<String, String> {
    let expected = required_text(args, "expected_content_hash")?;
    if expected.len() != 64 || !expected.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("invalid qualitative content hash".into());
    }
    let (_, actual) = state(store)?;
    if actual != expected {
        return Err("qualitative project changed since it was read".into());
    }
    Ok(actual)
}

fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .chars()
            .all(|character| character.is_alphanumeric() || "._-".contains(character))
}

fn ensure_parent_acyclic(
    store: &ProjectStore,
    code_id: &str,
    parent: Option<&str>,
) -> Result<(), String> {
    let Some(parent) = parent else {
        return Ok(());
    };
    if parent == code_id {
        return Err("qualitative code cannot parent itself".into());
    }
    let exists: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM qualitative_codes WHERE id=?1 AND active=1",
            [parent],
            |row| row.get(0),
        )
        .map_err(|_| "qualitative parent lookup failed")?;
    if exists != 1 {
        return Err("qualitative parent code not found".into());
    }
    let mut cursor = Some(parent.to_owned());
    let mut visited = HashSet::new();
    while let Some(current) = cursor {
        if current == code_id || !visited.insert(current.clone()) {
            return Err("qualitative code hierarchy would contain a cycle".into());
        }
        cursor = store
            .connection()
            .query_row(
                "SELECT parent_id FROM qualitative_codes WHERE id=?1",
                [&current],
                |row| row.get::<_, Option<String>>(0),
            )
            .optional()
            .map_err(|_| "qualitative hierarchy lookup failed")?
            .flatten();
    }
    Ok(())
}

pub(super) fn inspect(store: &ProjectStore) -> Result<Value, String> {
    let (state, content_hash) = state(store)?;
    Ok(json!({
        "project_id":store.info().map_err(|_|"project unavailable")?.id,
        "content_hash":content_hash,
        "state":state
    }))
}

pub(super) fn transcripts(store: &ProjectStore) -> Result<Value, String> {
    let (state, content_hash) = state(store)?;
    Ok(json!({
        "project_id":store.info().map_err(|_|"project unavailable")?.id,
        "content_hash":content_hash,
        "transcripts":state["transcripts"],
        "raw_source_text_disclosed":false
    }))
}

/// Read authoritative coding provenance without supplying or guessing case IDs.
/// Only a trusted host can subsequently link source IDs to quantitative cases.
pub(super) fn mixed_provenance(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    if args
        .as_object()
        .is_none_or(|object| object.keys().any(|key| key != "project_id"))
    {
        return Err("unsupported qualitative provenance arguments".into());
    }
    let (state, content_hash) = state(store)?;
    let codes = state["codes"]
        .as_array()
        .ok_or("invalid qualitative codebook")?;
    let annotations = state["annotations"]
        .as_array()
        .ok_or("invalid qualitative annotations")?;
    let transcripts = state["transcripts"]
        .as_array()
        .ok_or("invalid transcript state")?;
    let mut source_cases = BTreeMap::<&str, &str>::new();
    let mut matrix = BTreeMap::<String, BTreeSet<String>>::new();
    let mut counts = BTreeMap::<String, BTreeMap<String, u64>>::new();
    for transcript in transcripts {
        let source = transcript["source_id"]
            .as_str()
            .ok_or("invalid transcript source")?;
        let case = transcript["case_id"]
            .as_str()
            .ok_or("invalid transcript case")?;
        let (body, hash): (String, String) = store
            .connection()
            .query_row(
                "SELECT body,body_hash FROM document_text WHERE source_id=?1",
                [source],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .map_err(|_| "transcript source unavailable")?;
        if digest(body.as_bytes()) != hash
            || transcript["body_hash"].as_str() != Some(hash.as_str())
        {
            return Err("stale transcript source hash".into());
        }
        source_cases.insert(source, case);
        matrix.entry(case.to_owned()).or_default();
    }
    if codes.len() > 2_000 || annotations.len() > 50_000 {
        return Err("qualitative provenance exceeds resource limits".into());
    }
    let active: BTreeSet<&str> = codes
        .iter()
        .filter(|code| code["active"] == true)
        .map(|code| code["code_id"].as_str().ok_or("invalid code ID"))
        .collect::<Result<_, _>>()?;
    for case in matrix.keys() {
        counts.insert(
            case.clone(),
            active.iter().map(|id| ((*id).to_owned(), 0)).collect(),
        );
    }
    let mut verified = Vec::with_capacity(annotations.len());
    for annotation in annotations {
        let source_id = annotation["source_id"]
            .as_str()
            .ok_or("invalid source ID")?;
        let code_id = annotation["code_id"]
            .as_str()
            .ok_or("invalid annotation code")?;
        if !active.contains(code_id) {
            return Err("annotation references inactive or absent code".into());
        }
        if let Some(case_id) = source_cases.get(source_id) {
            matrix
                .entry((*case_id).to_owned())
                .or_default()
                .insert(code_id.to_owned());
            *counts
                .entry((*case_id).to_owned())
                .or_default()
                .entry(code_id.to_owned())
                .or_default() += 1;
        }
        let (body, stored_hash): (String, String) = store
            .connection()
            .query_row(
                "SELECT body,body_hash FROM document_text WHERE source_id=?1",
                [source_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .map_err(|_| "qualitative source missing")?;
        if digest(body.as_bytes()) != stored_hash
            || annotation["body_hash"].as_str() != Some(stored_hash.as_str())
        {
            return Err("stale or corrupted annotation source".into());
        }
        let start = annotation["start"]
            .as_u64()
            .and_then(|n| usize::try_from(n).ok())
            .ok_or("invalid annotation start")?;
        let end = annotation["end"]
            .as_u64()
            .and_then(|n| usize::try_from(n).ok())
            .ok_or("invalid annotation end")?;
        let quote = annotation["quote"]
            .as_str()
            .ok_or("invalid annotation quote")?;
        if start >= end
            || end > body.chars().count()
            || body
                .chars()
                .skip(start)
                .take(end - start)
                .collect::<String>()
                != quote
        {
            return Err("stale or corrupted annotation anchor".into());
        }
        verified.push(json!({
            "unit_id":annotation["unit_id"],"source_id":source_id,"code_id":code_id,
            "body_hash":stored_hash,"start":start,"end":end,
            "quote_sha256":digest(quote.as_bytes())
        }));
    }
    let complete = !transcripts.is_empty()
        && annotations.iter().all(|a| {
            a["source_id"]
                .as_str()
                .is_some_and(|s| source_cases.contains_key(s))
        });
    Ok(json!({
        "project_id":store.info().map_err(|_|"project unavailable")?.id,
        "coding_hash":content_hash,"codebook_ids":active,
        "verified_annotations":verified,
        "qualitative_cases":if complete {matrix.iter().map(|(case,codes)|json!({"case_id":case,"code_ids":codes})).collect::<Vec<_>>()} else {Vec::new()},
        "case_counts":if complete {json!(counts)} else {json!({})},
        "assumption":"Coding occurrences are events, not independent statistical units",
        "case_mapping_available":complete,
        "limitation":"Persisted transcript case IDs are authoritative for qualitative coding only; dataset case IDs must be validated independently by a trusted host",
        "quotes_disclosed":false
    }))
}

pub(super) fn write(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    expected_hash(store, args)?;
    match operation {
        "qualitative.transcript_register" | "qualitative.transcript_update" => {
            let source_id = required_text(args, "source_id")?.trim();
            let case_id = required_text(args, "case_id")?.trim();
            let confidential = args
                .get("confidential")
                .and_then(Value::as_bool)
                .ok_or("confidential boolean required")?;
            if !valid_identifier(source_id)
                || case_id.is_empty()
                || case_id.len() > 128
                || case_id.chars().any(char::is_control)
            {
                return Err("invalid transcript identifiers".into());
            }
            let (body, body_hash): (String, String) = store
                .connection()
                .query_row(
                    "SELECT body,body_hash FROM document_text WHERE source_id=?1",
                    [source_id],
                    |row| Ok((row.get(0)?, row.get(1)?)),
                )
                .map_err(|_| "transcript source not found")?;
            if digest(body.as_bytes()) != body_hash {
                return Err("transcript source hash mismatch".into());
            }
            if args.get("expected_body_hash").and_then(Value::as_str) != Some(body_hash.as_str()) {
                return Err("stale expected transcript body hash".into());
            }
            let update = operation == "qualitative.transcript_update";
            let present: i64 = store
                .connection()
                .query_row(
                    "SELECT count(*) FROM qualitative_transcripts WHERE source_id=?1",
                    [source_id],
                    |r| r.get(0),
                )
                .map_err(|_| "transcript lookup failed")?;
            if (present == 1) != update {
                return Err("duplicate or absent transcript mapping".into());
            }
            let payload = json!({"source_id_sha256":digest(source_id.as_bytes()),"case_id_sha256":digest(case_id.as_bytes()),"confidential":confidential,"body_hash":body_hash});
            let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
                if update {
                    tx.execute("UPDATE qualitative_transcripts SET case_id=?1,confidential=?2,body_hash=?3,recorded_at=?4 WHERE source_id=?5",
                        params![case_id,confidential as i64,body_hash,now,source_id])
                } else {
                    tx.execute("INSERT INTO qualitative_transcripts(source_id,case_id,confidential,body_hash,recorded_at) VALUES (?1,?2,?3,?4,?5)",
                        params![source_id,case_id,confidential as i64,body_hash,now])
                }.map_err(|_|"transcript write failed")?;
                Ok(())
            })?;
            let (_, hash) = state(store)?;
            Ok(
                json!({"source_id":source_id,"project_revision":revision,"content_hash":hash,"body_hash_verified":true}),
            )
        }
        "qualitative.add_code" => {
            let code_id = required_text(args, "code_id")?.trim();
            let name = required_text(args, "name")?.trim();
            let actor = required_text(args, "actor")?.trim();
            let description = args
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim();
            let parent = args.get("parent").and_then(Value::as_str);
            if !valid_identifier(code_id)
                || name.is_empty()
                || name.chars().count() > 200
                || description.chars().count() > 20_000
                || actor.is_empty()
                || actor.len() > 255
                || parent.is_some_and(|value| !valid_identifier(value))
            {
                return Err("invalid qualitative code".into());
            }
            ensure_parent_acyclic(store, code_id, parent)?;
            let payload = json!({
                "code_id":code_id,
                "name":name,
                "description_sha256":digest(description.as_bytes()),
                "parent":parent,
                "actor":actor
            });
            let (_, project_revision) = mutate(store, operation, ctx, &payload, |tx, now| {
                tx.execute(
                    "INSERT INTO qualitative_codes(id,name,description,parent_id,active,created_at)
                     VALUES (?1,?2,?3,?4,1,?5)",
                    params![code_id, name, description, parent, now],
                )
                .map_err(|_| "qualitative code already exists")?;
                Ok(())
            })?;
            let (_, content_hash) = state(store)?;
            Ok(json!({
                "code_id":code_id,
                "project_revision":project_revision,
                "content_hash":content_hash
            }))
        }
        "qualitative.update_code" => {
            let code_id = required_text(args, "code_id")?.trim();
            let actor = required_text(args, "actor")?.trim();
            if !valid_identifier(code_id) || actor.is_empty() || actor.len() > 255 {
                return Err("invalid qualitative code update".into());
            }
            let current: (String, String, Option<String>) = store
                .connection()
                .query_row(
                    "SELECT name,description,parent_id FROM qualitative_codes WHERE id=?1 AND active=1",
                    [code_id],
                    |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
                )
                .map_err(|_| "qualitative code not found")?;
            let name = args
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or(&current.0)
                .trim()
                .to_owned();
            let description = args
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or(&current.1)
                .trim()
                .to_owned();
            let parent = if args.get("parent").is_some() {
                args.get("parent")
                    .and_then(Value::as_str)
                    .map(str::to_owned)
            } else {
                current.2
            };
            if name.is_empty()
                || name.chars().count() > 200
                || description.chars().count() > 20_000
                || parent
                    .as_deref()
                    .is_some_and(|value| !valid_identifier(value))
            {
                return Err("invalid qualitative code update".into());
            }
            ensure_parent_acyclic(store, code_id, parent.as_deref())?;
            let payload = json!({
                "code_id":code_id,
                "name":name,
                "description_sha256":digest(description.as_bytes()),
                "parent":parent,
                "actor":actor
            });
            let (_, project_revision) = mutate(store, operation, ctx, &payload, |tx, _now| {
                if tx
                    .execute(
                        "UPDATE qualitative_codes SET name=?1,description=?2,parent_id=?3
                         WHERE id=?4 AND active=1",
                        params![name, description, parent, code_id],
                    )
                    .map_err(|_| "qualitative code update failed")?
                    != 1
                {
                    return Err("qualitative code not found".into());
                }
                Ok(())
            })?;
            let (_, content_hash) = state(store)?;
            Ok(json!({
                "code_id":code_id,
                "project_revision":project_revision,
                "content_hash":content_hash
            }))
        }
        "qualitative.delete_code" => {
            let code_id = required_text(args, "code_id")?.trim();
            let actor = required_text(args, "actor")?.trim();
            if !valid_identifier(code_id) || actor.is_empty() || actor.len() > 255 {
                return Err("invalid qualitative code delete".into());
            }
            let child_count: i64 = store
                .connection()
                .query_row(
                    "SELECT count(*) FROM qualitative_codes WHERE parent_id=?1 AND active=1",
                    [code_id],
                    |row| row.get(0),
                )
                .map_err(|_| "qualitative child lookup failed")?;
            let annotation_count: i64 = store
                .connection()
                .query_row(
                    "SELECT count(*) FROM qualitative_annotations WHERE code_id=?1",
                    [code_id],
                    |row| row.get(0),
                )
                .map_err(|_| "qualitative annotation lookup failed")?;
            if child_count != 0 || annotation_count != 0 {
                return Err("qualitative code is still referenced".into());
            }
            let payload = json!({"code_id":code_id,"actor":actor});
            let (_, project_revision) = mutate(store, operation, ctx, &payload, |tx, _now| {
                if tx
                    .execute(
                        "DELETE FROM qualitative_codes WHERE id=?1 AND active=1",
                        [code_id],
                    )
                    .map_err(|_| "qualitative code delete failed")?
                    != 1
                {
                    return Err("qualitative code not found".into());
                }
                Ok(())
            })?;
            let (_, content_hash) = state(store)?;
            Ok(json!({
                "code_id":code_id,
                "project_revision":project_revision,
                "content_hash":content_hash
            }))
        }
        "qualitative.annotate" => {
            let source_id = required_text(args, "source_id")?.trim();
            let code_id = required_text(args, "code_id")?.trim();
            let coder = required_text(args, "coder")?.trim();
            let unit_id = required_text(args, "unit_id")?.trim();
            let start = args
                .get("start")
                .and_then(Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .ok_or("invalid annotation start")?;
            let end = args
                .get("end")
                .and_then(Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .ok_or("invalid annotation end")?;
            if !valid_identifier(source_id)
                || !valid_identifier(code_id)
                || !valid_identifier(unit_id)
                || coder.is_empty()
                || coder.len() > 255
                || start >= end
            {
                return Err("invalid qualitative annotation".into());
            }
            let code_exists: i64 = store
                .connection()
                .query_row(
                    "SELECT count(*) FROM qualitative_codes WHERE id=?1 AND active=1",
                    [code_id],
                    |row| row.get(0),
                )
                .map_err(|_| "qualitative code lookup failed")?;
            if code_exists != 1 {
                return Err("qualitative code not found".into());
            }
            let (body, body_hash): (String, String) = store
                .connection()
                .query_row(
                    "SELECT body,body_hash FROM document_text WHERE source_id=?1",
                    [source_id],
                    |row| Ok((row.get(0)?, row.get(1)?)),
                )
                .map_err(|_| "qualitative source text not found")?;
            if digest(body.as_bytes()) != body_hash {
                return Err("qualitative source text checksum mismatch".into());
            }
            let character_count = body.chars().count();
            if end > character_count {
                return Err("qualitative annotation exceeds source text".into());
            }
            let quote: String = body.chars().skip(start).take(end - start).collect();
            if quote.is_empty() {
                return Err("qualitative annotation quote is empty".into());
            }
            let payload = json!({
                "unit_id":unit_id,
                "source_id":source_id,
                "code_id":code_id,
                "coder":coder,
                "start":start,
                "end":end,
                "body_hash":body_hash,
                "quote_sha256":digest(quote.as_bytes())
            });
            let (_, project_revision) = mutate(store, operation, ctx, &payload, |tx, now| {
                tx.execute(
                    "INSERT INTO qualitative_annotations
                     (id,source_id,code_id,coder,start,end,quote,body_hash,recorded_at)
                     VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
                    params![
                        unit_id,
                        source_id,
                        code_id,
                        coder,
                        start as i64,
                        end as i64,
                        quote,
                        body_hash,
                        now
                    ],
                )
                .map_err(|_| "qualitative annotation already exists or is invalid")?;
                Ok(())
            })?;
            let (_, content_hash) = state(store)?;
            Ok(json!({
                "unit_id":unit_id,
                "quote":quote,
                "quote_verified":true,
                "project_revision":project_revision,
                "content_hash":content_hash
            }))
        }
        _ => Err("unsupported qualitative write".into()),
    }
}

pub(super) fn kappa(args: &Value) -> Result<Value, String> {
    let first = args
        .get("first")
        .and_then(Value::as_object)
        .ok_or("first coder mapping required")?;
    let second = args
        .get("second")
        .and_then(Value::as_object)
        .ok_or("second coder mapping required")?;
    if first.is_empty() || first.len() != second.len() {
        return Err("coders must use identical non-empty unit IDs".into());
    }
    let first_keys: BTreeSet<_> = first.keys().collect();
    let second_keys: BTreeSet<_> = second.keys().collect();
    if first_keys != second_keys {
        return Err("coders must use identical non-empty unit IDs".into());
    }
    let mut first_counts = BTreeMap::<String, usize>::new();
    let mut second_counts = BTreeMap::<String, usize>::new();
    let mut observed_matches = 0usize;
    for key in first_keys {
        let left = first[key]
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or("missing codes are not accepted")?;
        let right = second[key]
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or("missing codes are not accepted")?;
        if left == right {
            observed_matches += 1;
        }
        *first_counts.entry(left.to_owned()).or_default() += 1;
        *second_counts.entry(right.to_owned()).or_default() += 1;
    }
    let n = first.len() as f64;
    let labels: BTreeSet<_> = first_counts
        .keys()
        .chain(second_counts.keys())
        .cloned()
        .collect();
    let observed = observed_matches as f64 / n;
    let expected = labels
        .iter()
        .map(|label| {
            let first_rate = *first_counts.get(label).unwrap_or(&0) as f64 / n;
            let second_rate = *second_counts.get(label).unwrap_or(&0) as f64 / n;
            first_rate * second_rate
        })
        .sum::<f64>();
    if expected >= 1.0 - f64::EPSILON {
        return Err("kappa undefined when chance agreement equals one".into());
    }
    Ok(json!({
        "kappa":(observed-expected)/(1.0-expected),
        "observed_agreement":observed,
        "expected_agreement":expected,
        "n_units":first.len(),
        "labels":labels,
        "assumption":"Identical fixed unitization; nominal labels"
    }))
}
