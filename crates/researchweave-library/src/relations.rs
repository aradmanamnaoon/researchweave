//! Reversible reference identity decisions and human-attested citation graph.
use super::{
    collections::{exists, mutate},
    required,
};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use uuid::Uuid;

type ReferenceRow = (
    String,
    String,
    String,
    Option<i64>,
    Option<String>,
    String,
    String,
    String,
    String,
    String,
    String,
);

fn sha(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn reference_wire(store: &ProjectStore, reference_id: &str) -> Result<Value, String> {
    let row: ReferenceRow = store
        .connection()
        .query_row(
            "SELECT id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at
             FROM reference WHERE id=?1",
            [reference_id],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                    row.get(7)?,
                    row.get(8)?,
                    row.get(9)?,
                    row.get(10)?,
                ))
            },
        )
        .map_err(|_| "reference not found")?;
    let authors: Value = serde_json::from_str(&row.2).map_err(|_| "reference authors corrupted")?;
    let metadata: Value =
        serde_json::from_str(&row.8).map_err(|_| "reference metadata corrupted")?;
    Ok(json!({
        "id":row.0,
        "title":row.1,
        "authors":authors,
        "year":row.3,
        "doi":row.4,
        "kind":row.5,
        "format":row.6,
        "raw":row.7,
        "metadata":metadata,
        "status":row.9,
        "imported_at":row.10
    }))
}

fn normalize_doi(value: Option<&str>) -> Option<String> {
    let value = value?.trim().to_ascii_lowercase();
    let value = value
        .strip_prefix("https://doi.org/")
        .or_else(|| value.strip_prefix("http://doi.org/"))
        .or_else(|| value.strip_prefix("doi:"))
        .unwrap_or(&value)
        .trim();
    if value.starts_with("10.")
        && value.contains('/')
        && value.len() <= 255
        && !value.chars().any(char::is_whitespace)
    {
        Some(value.to_owned())
    } else {
        None
    }
}

fn normalized_text(value: &str) -> String {
    value
        .to_lowercase()
        .chars()
        .map(|character| {
            if character.is_alphanumeric() {
                character
            } else {
                ' '
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn surname(value: &str) -> String {
    let normalized = value.trim().to_lowercase();
    if let Some((first, _)) = normalized.split_once(',') {
        return normalized_text(first);
    }
    normalized
        .split_whitespace()
        .last()
        .map(normalized_text)
        .unwrap_or_default()
}

fn metadata_differences(canonical: &Value, duplicate: &Value) -> Vec<Value> {
    ["title", "authors", "year", "doi", "kind"]
        .into_iter()
        .filter(|field| canonical[*field] != duplicate[*field])
        .map(|field| {
            json!({
                "field":field,
                "canonical":canonical[field],
                "duplicate":duplicate[field]
            })
        })
        .collect()
}

fn resolve(store: &ProjectStore, reference_id: &str) -> Result<Value, String> {
    let original = reference_wire(store, reference_id)?;
    let alias: Option<(String, String)> = store
        .connection()
        .query_row(
            "SELECT canonical_id,reason FROM reference_alias WHERE original_id=?1",
            [reference_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .map_err(|_| "reference alias lookup failed")?;
    if let Some((canonical_id, reason)) = alias {
        let canonical = reference_wire(store, &canonical_id)?;
        return Ok(json!({
            "reference_id":reference_id,
            "canonical_id":canonical_id,
            "is_alias":true,
            "alias_reason":reason,
            "canonical":canonical,
            "original":original,
            "aliases":[]
        }));
    }
    let mut statement = store
        .connection()
        .prepare(
            "SELECT original_id,reason FROM reference_alias
             WHERE canonical_id=?1 ORDER BY original_id",
        )
        .map_err(|_| "reference alias lookup failed")?;
    let aliases = statement
        .query_map([reference_id], |row| {
            Ok(json!({
                "reference_id":row.get::<_,String>(0)?,
                "reason":row.get::<_,String>(1)?
            }))
        })
        .map_err(|_| "reference alias lookup failed")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "reference alias lookup failed")?;
    Ok(json!({
        "reference_id":reference_id,
        "canonical_id":reference_id,
        "is_alias":false,
        "alias_reason":null,
        "canonical":original,
        "aliases":aliases
    }))
}

fn merge(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let canonical_id = required(args, "canonical_id", 128)?;
    let duplicate_id = required(args, "duplicate_id", 128)?;
    let rationale = required(args, "rationale", 2000)?.trim();
    if canonical_id == duplicate_id || rationale.is_empty() {
        return Err("merge requires distinct references and reviewer rationale".into());
    }
    let canonical = reference_wire(store, canonical_id)?;
    let duplicate = reference_wire(store, duplicate_id)?;
    let differences = metadata_differences(&canonical, &duplicate);
    let canonical_is_alias: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM reference_alias WHERE original_id=?1",
            [canonical_id],
            |row| row.get(0),
        )
        .map_err(|_| "reference alias lookup failed")?;
    let duplicate_is_alias: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM reference_alias WHERE original_id=?1",
            [duplicate_id],
            |row| row.get(0),
        )
        .map_err(|_| "reference alias lookup failed")?;
    let duplicate_is_canonical: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM reference_alias WHERE canonical_id=?1",
            [duplicate_id],
            |row| row.get(0),
        )
        .map_err(|_| "reference alias lookup failed")?;
    if canonical_is_alias != 0 || duplicate_is_alias != 0 || duplicate_is_canonical != 0 {
        return Err("reference merge conflicts with existing alias mapping".into());
    }
    if preview {
        return Ok(json!({
            "preview":true,
            "canonical_id":canonical_id,
            "alias_id":duplicate_id,
            "metadata_differences":differences,
            "metadata_resolution":"preserved_both_records_no_auto_overwrite"
        }));
    }
    let payload = json!({
        "canonical_id":canonical_id,
        "duplicate_id":duplicate_id,
        "rationale":rationale
    });
    let (_, revision) = mutate(store, "reference.merge", &payload, ctx, |tx, _now| {
        tx.execute(
            "INSERT INTO reference_alias(original_id,canonical_id,reason) VALUES (?1,?2,?3)",
            params![duplicate_id, canonical_id, rationale],
        )
        .map_err(|_| "reference merge conflict")?;
        Ok(())
    })?;
    Ok(json!({
        "canonical_id":canonical_id,
        "alias_id":duplicate_id,
        "reversible":true,
        "revision":revision,
        "metadata_differences":differences,
        "metadata_resolution":"preserved_both_records_no_auto_overwrite"
    }))
}

fn unmerge(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let duplicate_id = required(args, "duplicate_id", 128)?;
    let rationale = required(args, "rationale", 2000)?.trim();
    if rationale.is_empty() {
        return Err("undo rationale required".into());
    }
    let canonical: String = store
        .connection()
        .query_row(
            "SELECT canonical_id FROM reference_alias WHERE original_id=?1",
            [duplicate_id],
            |row| row.get(0),
        )
        .map_err(|_| "reference has no active merge")?;
    if preview {
        return Ok(json!({
            "preview":true,
            "alias_id":duplicate_id,
            "previous_canonical_id":canonical,
            "reverted":false
        }));
    }
    let payload = json!({"alias_id":duplicate_id,"rationale":rationale});
    let (_, revision) = mutate(store, "reference.unmerge", &payload, ctx, |tx, _now| {
        if tx
            .execute(
                "DELETE FROM reference_alias WHERE original_id=?1",
                [duplicate_id],
            )
            .map_err(|_| "reference unmerge failed")?
            != 1
        {
            return Err("reference has no active merge".into());
        }
        Ok(())
    })?;
    Ok(json!({
        "alias_id":duplicate_id,
        "previous_canonical_id":canonical,
        "reverted":true,
        "revision":revision
    }))
}

fn compare_identity(
    store: &ProjectStore,
    reference_id: &str,
    observed: &Map<String, Value>,
) -> Result<Value, String> {
    if observed.len() > 120 {
        return Err("excessive provider metadata fields".into());
    }
    let reference = reference_wire(store, reference_id)?;
    let local_doi = normalize_doi(reference["doi"].as_str());
    let candidate_doi = observed
        .get("doi")
        .and_then(Value::as_str)
        .and_then(|value| normalize_doi(Some(value)));
    let doi_status = match (&local_doi, &candidate_doi) {
        (None, _) => "reference_missing_or_invalid",
        (Some(_), None) => "candidate_missing_or_invalid",
        (Some(left), Some(right)) if left == right => "exact",
        _ => "different_identifier",
    };
    let candidate_title = observed.get("title").and_then(Value::as_str);
    let local_title = reference["title"].as_str().unwrap_or_default();
    let title_status = if candidate_title.is_some_and(|value| !value.trim().is_empty())
        && !local_title.trim().is_empty()
    {
        if normalized_text(candidate_title.unwrap()) == normalized_text(local_title) {
            "exact"
        } else {
            "mismatch"
        }
    } else {
        "unknown"
    };
    let local_year = reference["year"].as_i64();
    let candidate_year = observed.get("year").and_then(Value::as_i64);
    let year_status = match (local_year, candidate_year) {
        (_, Some(year)) if !(1500..=2200).contains(&year) => "invalid_provider_value",
        (Some(left), Some(right)) if left == right => "exact",
        (Some(_), Some(_)) => "mismatch",
        _ => "unknown",
    };
    let local_first = reference["authors"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .map(surname)
        .unwrap_or_default();
    let candidate_first = observed["authors"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .map(surname)
        .unwrap_or_default();
    let author_status = if local_first.is_empty() || candidate_first.is_empty() {
        "unknown"
    } else if local_first == candidate_first {
        "exact"
    } else {
        "mismatch"
    };
    let has_mismatch = [doi_status, title_status, year_status, author_status]
        .iter()
        .any(|status| {
            matches!(
                *status,
                "different_identifier" | "mismatch" | "invalid_provider_value"
            )
        });
    let identity = if has_mismatch {
        "metadata_mismatch"
    } else if doi_status == "exact"
        && title_status == "exact"
        && (year_status == "exact" || author_status == "exact")
    {
        "bibliographic_consistency"
    } else {
        "insufficient_metadata"
    };
    Ok(json!({
        "identity":identity,
        "details":[
            {"field":"doi","status":doi_status},
            {"field":"title","status":title_status},
            {"field":"year","status":year_status},
            {"field":"first_author","status":author_status}
        ],
        "catalog_existence":"not_checked",
        "scientific_claims_verified":false,
        "retraction_status":"unknown",
        "correction_status":"unknown"
    }))
}

fn identity_record(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let reference_id = required(args, "reference_id", 128)?;
    let provider = required(args, "provider", 128)?.trim();
    let observed = args
        .get("observed")
        .and_then(Value::as_object)
        .ok_or("observed metadata object required")?;
    if provider.is_empty() {
        return Err("provider required".into());
    }
    let result = compare_identity(store, reference_id, observed)?;
    let observation_json = serde_json::to_string(&Value::Object(observed.clone()))
        .map_err(|_| "observation serialization failed")?;
    let result_json =
        serde_json::to_string(&result).map_err(|_| "identity result serialization failed")?;
    let observation_sha256 = sha(observation_json.as_bytes());
    let check_id = Uuid::new_v4().to_string();
    if preview {
        return Ok(json!({
            "preview":true,
            "check_id":check_id,
            "reference_id":reference_id,
            "provider":provider,
            "observation_sha256":observation_sha256,
            "result":result
        }));
    }
    let payload = json!({
        "check_id":check_id,
        "reference_id":reference_id,
        "provider":provider,
        "observation_sha256":observation_sha256,
        "identity":result["identity"]
    });
    let (_, revision) = mutate(
        store,
        "reference.identity_record",
        &payload,
        ctx,
        |tx, now| {
            tx.execute(
                "INSERT INTO reference_identity_checks
             (id,reference_id,provider,observation_json,observation_sha256,result_json,checked_at)
             VALUES (?1,?2,?3,?4,?5,?6,?7)",
                params![
                    check_id,
                    reference_id,
                    provider,
                    observation_json,
                    observation_sha256,
                    result_json,
                    now
                ],
            )
            .map_err(|_| "identity observation insert failed")?;
            Ok(())
        },
    )?;
    let mut output = result;
    let object = output
        .as_object_mut()
        .ok_or("identity result unavailable")?;
    object.insert("check_id".into(), Value::String(check_id));
    object.insert("revision".into(), json!(revision));
    Ok(output)
}

fn identity_history(store: &ProjectStore, reference_id: &str) -> Result<Value, String> {
    let _ = reference_wire(store, reference_id)?;
    let mut statement = store
        .connection()
        .prepare(
            "SELECT id,provider,observation_json,observation_sha256,result_json,checked_at
             FROM reference_identity_checks WHERE reference_id=?1 ORDER BY checked_at,id",
        )
        .map_err(|_| "identity history unavailable")?;
    let rows = statement
        .query_map([reference_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
            ))
        })
        .map_err(|_| "identity history unavailable")?;
    let mut records = Vec::new();
    for row in rows {
        let (check_id, provider, observation, observation_sha256, result, checked_at) =
            row.map_err(|_| "identity history corrupted")?;
        records.push(json!({
            "check_id":check_id,
            "reference_id":reference_id,
            "provider":provider,
            "observation":serde_json::from_str::<Value>(&observation).map_err(|_|"identity observation corrupted")?,
            "observation_sha256":observation_sha256,
            "result":serde_json::from_str::<Value>(&result).map_err(|_|"identity result corrupted")?,
            "checked_at":checked_at
        }));
    }
    Ok(json!({"records":records}))
}

fn verify_anchor(
    store: &ProjectStore,
    anchor_id: &str,
) -> Result<(String, String, String), String> {
    let row: (String, String, i64, i64, String, i64, String, i64) = store
        .connection()
        .query_row(
            "SELECT a.quote,a.source_id,a.start,a.end,a.body_hash,a.verified,d.body,s.deleted
             FROM anchors a
             JOIN sources s ON s.id=a.source_id
             JOIN document_text d ON d.source_id=a.source_id
             WHERE a.id=?1",
            [anchor_id],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                    row.get(7)?,
                ))
            },
        )
        .map_err(|_| "citation relationship requires an exact source anchor")?;
    if row.5 != 1 || row.7 != 0 || sha(row.6.as_bytes()) != row.4 {
        return Err("citation source anchor is stale or inactive".into());
    }
    let start = usize::try_from(row.2).map_err(|_| "anchor start invalid")?;
    let end = usize::try_from(row.3).map_err(|_| "anchor end invalid")?;
    let quote: String = row
        .6
        .chars()
        .skip(start)
        .take(end.saturating_sub(start))
        .collect();
    if quote != row.0 {
        return Err("citation source anchor no longer matches".into());
    }
    Ok((row.0, row.1, row.4))
}

fn citation_add(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let citing = required(args, "citing_reference_id", 128)?;
    let cited = required(args, "cited_reference_id", 128)?;
    let provenance = required(args, "provenance", 3000)?.trim();
    let confirmed_by = required(args, "confirmed_by", 150)?.trim();
    if citing == cited || provenance.is_empty() || confirmed_by.is_empty() {
        return Err("citation requires distinct references, provenance and reviewer".into());
    }
    for id in [citing, cited] {
        if !exists(store, "reference", "id", id)? {
            return Err("citation reference is missing".into());
        }
    }
    let id = Uuid::new_v4().to_string();
    if preview {
        return Ok(json!({
            "preview":true,
            "id":id,
            "status":"human_attested_unanchored",
            "read_status_inferred":false
        }));
    }
    let payload = json!({
        "id":id,
        "citing_id":citing,
        "cited_id":cited,
        "confirmed_by":confirmed_by,
        "provenance":provenance
    });
    let (_, revision) = mutate(store, "reference.citation_add", &payload, ctx, |tx, now| {
        tx.execute(
            "INSERT INTO citation_assertions
             (id,citing_id,cited_id,provenance,confirmed_by,created_at)
             VALUES (?1,?2,?3,?4,?5,?6)",
            params![id, citing, cited, provenance, confirmed_by, now],
        )
        .map_err(|_| "citation relation already exists")?;
        Ok(())
    })?;
    Ok(json!({
        "id":id,
        "revision":revision,
        "read_status_inferred":false,
        "verified_anchor":false,
        "status":"human_attested_unanchored"
    }))
}

fn citation_link(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let citing = required(args, "citing_id", 128)?;
    let cited = required(args, "cited_id", 128)?;
    let anchor_id = required(args, "anchor_id", 128)?;
    let actor = required(args, "actor", 150)?.trim();
    let rationale = required(args, "rationale", 3000)?.trim();
    if citing == cited || actor.is_empty() || rationale.is_empty() {
        return Err("anchored citation requires distinct references, actor and rationale".into());
    }
    for id in [citing, cited] {
        if !exists(store, "reference", "id", id)? {
            return Err("citation reference does not exist".into());
        }
    }
    let (quote, source_id, _) = verify_anchor(store, anchor_id)?;
    let quote_sha256 = sha(quote.as_bytes());
    let id = Uuid::new_v4().to_string();
    if preview {
        return Ok(json!({
            "preview":true,
            "id":id,
            "anchor_id":anchor_id,
            "source_id":source_id,
            "quote_sha256":quote_sha256,
            "status":"human_attested_exact_anchor"
        }));
    }
    let payload = json!({
        "id":id,
        "citing_id":citing,
        "cited_id":cited,
        "anchor_id":anchor_id,
        "anchor_sha256":quote_sha256,
        "actor":actor
    });
    let (_, revision) = mutate(
        store,
        "reference.citation_link",
        &payload,
        ctx,
        |tx, now| {
            let duplicate: i64 = tx
                .query_row(
                    "SELECT count(*) FROM reference_citations
                 WHERE citing_id=?1 AND cited_id=?2 AND anchor_id=?3 AND revoked_at IS NULL",
                    params![citing, cited, anchor_id],
                    |row| row.get(0),
                )
                .map_err(|_| "citation duplicate check failed")?;
            if duplicate != 0 {
                return Err("active identical citation relation exists".into());
            }
            tx.execute(
                "INSERT INTO reference_citations
             (id,citing_id,cited_id,anchor_id,anchor_sha256,actor,rationale,created_at,
              revoked_at,revocation_reason,revoked_by)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,NULL,NULL,NULL)",
                params![
                    id,
                    citing,
                    cited,
                    anchor_id,
                    quote_sha256,
                    actor,
                    rationale,
                    now
                ],
            )
            .map_err(|_| "citation relation insert failed")?;
            Ok(())
        },
    )?;
    Ok(json!({
        "id":id,
        "citing_id":citing,
        "cited_id":cited,
        "anchor_id":anchor_id,
        "status":"human_attested_exact_anchor",
        "paper_read":"unknown",
        "revision":revision
    }))
}

fn citation_revoke(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let edge_id = required(args, "edge_id", 128)?;
    let actor = required(args, "actor", 150)?.trim();
    let rationale = required(args, "rationale", 3000)?.trim();
    if actor.is_empty() || rationale.is_empty() {
        return Err("citation revocation requires actor and rationale".into());
    }
    let active: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM reference_citations WHERE id=?1 AND revoked_at IS NULL",
            [edge_id],
            |row| row.get(0),
        )
        .map_err(|_| "citation edge lookup failed")?;
    if active != 1 {
        return Err("citation edge missing or already revoked".into());
    }
    if preview {
        return Ok(json!({"preview":true,"id":edge_id,"would_revoke":true}));
    }
    let payload = json!({"edge_id":edge_id,"actor":actor,"rationale":rationale});
    let (_, revision) = mutate(
        store,
        "reference.citation_revoke",
        &payload,
        ctx,
        |tx, now| {
            if tx
            .execute(
                "UPDATE reference_citations SET revoked_at=?1,revocation_reason=?2,revoked_by=?3
                 WHERE id=?4 AND revoked_at IS NULL",
                params![now, rationale, actor, edge_id],
            )
            .map_err(|_| "citation revocation failed")?
            != 1
        {
            return Err("citation edge missing or already revoked".into());
        }
            Ok(())
        },
    )?;
    Ok(json!({"id":edge_id,"revoked":true,"revision":revision}))
}

fn graph(store: &ProjectStore, include_revoked: bool) -> Result<Value, String> {
    let mut nodes = BTreeMap::<String, Value>::new();
    let mut edges = Vec::new();
    let sql = if include_revoked {
        "SELECT id,citing_id,cited_id,anchor_id,anchor_sha256,actor,rationale,created_at,
                revoked_at FROM reference_citations ORDER BY created_at,id"
    } else {
        "SELECT id,citing_id,cited_id,anchor_id,anchor_sha256,actor,rationale,created_at,
                revoked_at FROM reference_citations WHERE revoked_at IS NULL ORDER BY created_at,id"
    };
    let mut statement = store
        .connection()
        .prepare(sql)
        .map_err(|_| "citation graph unavailable")?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, String>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, Option<String>>(8)?,
            ))
        })
        .map_err(|_| "citation graph unavailable")?;
    for row in rows {
        let (id, citing, cited, anchor_id, anchor_hash, actor, rationale, created_at, revoked_at) =
            row.map_err(|_| "citation graph corrupted")?;
        let current = verify_anchor(store, &anchor_id)
            .map(|(quote, _, _)| sha(quote.as_bytes()) == anchor_hash)
            .unwrap_or(false);
        for reference_id in [&citing, &cited] {
            if !nodes.contains_key(reference_id) {
                let reference = reference_wire(store, reference_id)?;
                nodes.insert(
                    reference_id.clone(),
                    json!({
                        "id":reference_id,
                        "title":reference["title"],
                        "doi":reference["doi"],
                        "paper_read":"unknown"
                    }),
                );
            }
        }
        edges.push(json!({
            "id":id,
            "citing_id":citing,
            "cited_id":cited,
            "anchor_id":anchor_id,
            "actor":actor,
            "rationale":rationale,
            "created_at":created_at,
            "revoked_at":revoked_at,
            "status":if current {"human_attested_exact_anchor"} else {"stale_anchor"},
            "quote_sha256":anchor_hash,
            "link_verified_by_human":true,
            "scientific_claims_verified":false
        }));
    }
    let mut assertions = store
        .connection()
        .prepare(
            "SELECT id,citing_id,cited_id,provenance,confirmed_by,created_at
             FROM citation_assertions ORDER BY created_at,id",
        )
        .map_err(|_| "citation assertions unavailable")?;
    let rows = assertions
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
            ))
        })
        .map_err(|_| "citation assertions unavailable")?;
    for row in rows {
        let (id, citing, cited, provenance, confirmed_by, created_at) =
            row.map_err(|_| "citation assertions corrupted")?;
        for reference_id in [&citing, &cited] {
            if !nodes.contains_key(reference_id) {
                let reference = reference_wire(store, reference_id)?;
                nodes.insert(
                    reference_id.clone(),
                    json!({
                        "id":reference_id,
                        "title":reference["title"],
                        "doi":reference["doi"],
                        "paper_read":"unknown"
                    }),
                );
            }
        }
        edges.push(json!({
            "id":id,
            "citing_id":citing,
            "cited_id":cited,
            "anchor_id":null,
            "actor":confirmed_by,
            "rationale":provenance,
            "created_at":created_at,
            "revoked_at":null,
            "status":"human_attested_unanchored",
            "quote_sha256":null,
            "link_verified_by_human":true,
            "scientific_claims_verified":false
        }));
    }
    let verified = edges
        .iter()
        .all(|edge| edge["status"] == "human_attested_exact_anchor");
    let active_edges = edges
        .iter()
        .filter(|edge| edge["revoked_at"].is_null())
        .count();
    Ok(json!({
        "nodes":nodes.into_values().collect::<Vec<_>>(),
        "edges":edges,
        "active_edges":active_edges,
        "paper_read_inferred":false,
        "read_status_inferred":false,
        "orphan_edges":[],
        "verified":verified,
        "warnings":["Citation relationships are human attested; the graph does not certify that either article was read."]
    }))
}

fn xml_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn graphml(store: &ProjectStore) -> Result<Value, String> {
    let graph = graph(store, false)?;
    if graph["verified"] != true {
        return Err("graph contains unanchored or stale citation relations".into());
    }
    let mut text = String::from(
        r#"<?xml version="1.0" encoding="UTF-8"?><graphml xmlns="http://graphml.graphdrawing.org/xmlns"><graph id="researchweave-citations" edgedefault="directed">"#,
    );
    for node in graph["nodes"].as_array().into_iter().flatten() {
        text.push_str(&format!(
            r#"<node id="{}"/>"#,
            xml_escape(node["id"].as_str().unwrap_or_default())
        ));
    }
    for edge in graph["edges"].as_array().into_iter().flatten() {
        text.push_str(&format!(
            r#"<edge id="{}" source="{}" target="{}"/>"#,
            xml_escape(edge["id"].as_str().unwrap_or_default()),
            xml_escape(edge["citing_id"].as_str().unwrap_or_default()),
            xml_escape(edge["cited_id"].as_str().unwrap_or_default())
        ));
    }
    text.push_str("</graph></graphml>");
    Ok(json!({
        "format":"graphml",
        "text":text,
        "nodes":graph["nodes"].as_array().map_or(0,Vec::len),
        "edges":graph["edges"].as_array().map_or(0,Vec::len),
        "paper_read_inferred":false
    }))
}

pub(super) fn run(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    match operation {
        "reference.resolve" => resolve(store, required(args, "reference_id", 128)?),
        "reference.validate" => {
            let reference_id = required(args, "reference_id", 128)?;
            let reference = reference_wire(store, reference_id)?;
            let doi = normalize_doi(reference["doi"].as_str());
            Ok(json!({
                "reference_id":reference_id,
                "doi":doi,
                "doi_syntax_valid":doi.is_some(),
                "metadata_parseable":true,
                "catalog_checked":false,
                "scientific_claims_verified":false
            }))
        }
        "reference.merge" => merge(store, args, ctx, preview),
        "reference.unmerge" => unmerge(store, args, ctx, preview),
        "reference.identity_record" => identity_record(store, args, ctx, preview),
        "reference.identity_history" => {
            identity_history(store, required(args, "reference_id", 128)?)
        }
        "reference.citation_add" => citation_add(store, args, ctx, preview),
        "reference.citation_link" => citation_link(store, args, ctx, preview),
        "reference.citation_revoke" => citation_revoke(store, args, ctx, preview),
        "reference.citation_graph" => graph(
            store,
            args.get("include_revoked")
                .and_then(Value::as_bool)
                .unwrap_or(false),
        ),
        "reference.citation_graphml" => graphml(store),
        _ => Err("unsupported reference relation operation".into()),
    }
}
