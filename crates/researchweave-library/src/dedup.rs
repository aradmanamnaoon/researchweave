//! Conservative offline duplicate candidates and explicit reversible identity decisions.
//! No reference, source, citation, or raw bibliographic record is deleted.
use super::{bounded, collections, collections::current_revision, relations, required};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use uuid::Uuid;

const MAX_SCAN: i64 = 200;
const MAX_RESULTS: i64 = 100;

#[derive(Clone)]
struct Reference {
    id: String,
    title: String,
    authors: Vec<String>,
    year: Option<i64>,
    doi: Option<String>,
    raw_sha256: String,
}

fn hash(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn normalize_text(input: &str) -> String {
    input
        .to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { ' ' })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn first_author(authors: &[String]) -> String {
    let Some(first) = authors.first() else {
        return String::new();
    };
    let surname = first
        .split_once(',')
        .map(|(surname, _)| surname)
        .or_else(|| first.split_whitespace().last())
        .unwrap_or("");
    normalize_text(surname)
}

fn normalize_doi(input: Option<&str>) -> Option<String> {
    let input = input?.trim();
    let mut input = input.to_ascii_lowercase();
    for prefix in [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ] {
        if let Some(rest) = input.strip_prefix(prefix) {
            input = rest.to_owned();
            break;
        }
    }
    let (registrant, suffix) = input.split_once('/')?;
    let digits = registrant.strip_prefix("10.")?;
    if !(4..=9).contains(&digits.len())
        || !digits.bytes().all(|b| b.is_ascii_digit())
        || suffix.is_empty()
        || input.len() > 255
        || input.chars().any(|c| c.is_whitespace() || c.is_control())
    {
        return None;
    }
    Some(input)
}

fn references(store: &ProjectStore) -> Result<(Vec<Reference>, bool), String> {
    let total: i64 = store
        .connection()
        .query_row("SELECT COUNT(*) FROM reference", [], |row| row.get(0))
        .map_err(|_| "reference count unavailable")?;
    let mut statement = store
        .connection()
        .prepare(
            "SELECT r.id,r.title,r.authors_json,r.year,r.doi,r.raw FROM reference r \
         LEFT JOIN reference_alias a ON a.original_id=r.id \
         WHERE a.original_id IS NULL \
         ORDER BY r.id LIMIT ?1",
        )
        .map_err(|_| "reference scan unavailable")?;
    let rows = statement
        .query_map(params![MAX_SCAN], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, Option<i64>>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, String>(5)?,
            ))
        })
        .map_err(|_| "reference scan unavailable")?;
    let mut output = Vec::new();
    for row in rows {
        let (id, title, authors_json, year, doi, raw) = row.map_err(|_| "invalid reference row")?;
        let authors: Vec<String> =
            serde_json::from_str(&authors_json).map_err(|_| "invalid reference authors")?;
        if authors.len() > 100 {
            return Err("invalid reference author count".into());
        }
        output.push(Reference {
            id,
            title,
            authors,
            year,
            doi,
            raw_sha256: hash(raw.as_bytes()),
        });
    }
    // Count all rows, including aliased entries, to be conservative about scan completeness.
    Ok((output, total > MAX_SCAN))
}

fn candidate(left: &Reference, right: &Reference, revision: i64) -> Option<Value> {
    let left_doi = normalize_doi(left.doi.as_deref());
    let right_doi = normalize_doi(right.doi.as_deref());
    let doi_equal = left_doi.is_some() && left_doi == right_doi;
    // Malformed, nonempty identifiers are contradictory evidence, not absent
    // evidence. Never silently downgrade them to "missing DOI" and permit a
    // title/author/year-only alias that may conflate distinct publications.
    let doi_unparseable = [left, right].iter().any(|reference| {
        reference
            .doi
            .as_deref()
            .is_some_and(|raw| !raw.trim().is_empty() && normalize_doi(Some(raw)).is_none())
    });
    let doi_conflict =
        doi_unparseable || (left_doi.is_some() && right_doi.is_some() && left_doi != right_doi);
    let title_equal = !normalize_text(&left.title).is_empty()
        && normalize_text(&left.title) == normalize_text(&right.title);
    let author_left = first_author(&left.authors);
    let author_equal = !author_left.is_empty() && author_left == first_author(&right.authors);
    let year_equal = left.year.is_some() && left.year == right.year;
    if !doi_equal && !(title_equal && author_equal && year_equal) {
        return None;
    }
    // Require three independent consistent metadata signals before approving
    // an identity alias; an exact DOI alone can belong to conflicting records.
    let safe_to_review = title_equal && author_equal && year_equal && !doi_conflict;
    let conflict = !safe_to_review;
    let score = if conflict {
        0
    } else if doi_equal {
        100
    } else {
        80
    };
    let fingerprint_source = json!({
        "schema":"reference-dedup-f14-v1",
        "revision":revision,
        "left_id":left.id,"right_id":right.id,
        "left_title":left.title,"right_title":right.title,
        "left_authors":left.authors,"right_authors":right.authors,
        "left_year":left.year,"right_year":right.year,
        "left_doi":left.doi,"right_doi":right.doi,
        "left_raw_sha256":left.raw_sha256,"right_raw_sha256":right.raw_sha256,
    });
    Some(json!({
        "left_id":left.id,"right_id":right.id,
        "left_title":left.title,"right_title":right.title,
        "score":score,"candidate_sha256":hash(fingerprint_source.to_string().as_bytes()),
        "signals":{"doi_equal":doi_equal,"doi_conflict":doi_conflict,
            "doi_unparseable":doi_unparseable,
            "title_equal":title_equal,"first_author_equal":author_equal,"year_equal":year_equal},
        "review_status":if conflict {"conflicting_metadata"} else {"review_required"},
        "eligible_for_approval":safe_to_review,
        "automatically_merged":false,
    }))
}

/// A pair's *source identity* is independent of unrelated project revisions.
/// In contrast, candidate_sha256 intentionally includes project revision so
/// that previews cannot be replayed after any intervening write.
fn stable_pair_sha256(left: &Reference, right: &Reference) -> String {
    hash(
        json!({
            "schema":"reference-dedup-f14-pair-v1",
            "left_id":left.id,"right_id":right.id,
            "left_title":left.title,"right_title":right.title,
            "left_authors":left.authors,"right_authors":right.authors,
            "left_year":left.year,"right_year":right.year,
            "left_doi":left.doi,"right_doi":right.doi,
            "left_raw_sha256":left.raw_sha256,"right_raw_sha256":right.raw_sha256,
        })
        .to_string()
        .as_bytes(),
    )
}

fn sorted_pair<'a>(left: &'a Reference, right: &'a Reference) -> (&'a Reference, &'a Reference) {
    if left.id < right.id {
        (left, right)
    } else {
        (right, left)
    }
}

fn pair_ids(args: &Value) -> Result<(String, String), String> {
    let left = required(args, "left_id", 128)?;
    let right = required(args, "right_id", 128)?;
    for (label, value) in [("left_id", left), ("right_id", right)] {
        let parsed = Uuid::parse_str(value).map_err(|_| format!("invalid {label} UUID"))?;
        if parsed.to_string() != value {
            return Err(format!("noncanonical {label} UUID"));
        }
    }
    if left == right {
        return Err("reference decision requires two different IDs".into());
    }
    if left < right {
        Ok((left.to_owned(), right.to_owned()))
    } else {
        Ok((right.to_owned(), left.to_owned()))
    }
}

#[derive(Clone, PartialEq, Eq)]
struct RecordedDecision {
    decision: String,
    stable_pair_sha256: String,
    project_revision: i64,
}

fn latest_decision(
    conn: &Connection,
    left_id: &str,
    right_id: &str,
) -> Result<Option<RecordedDecision>, String> {
    conn.query_row(
        "SELECT decision,stable_pair_sha256,project_revision
         FROM reference_dedup_decisions WHERE left_id=?1 AND right_id=?2
         ORDER BY project_revision DESC LIMIT 1",
        params![left_id, right_id],
        |row| {
            Ok(RecordedDecision {
                decision: row.get(0)?,
                stable_pair_sha256: row.get(1)?,
                project_revision: row.get(2)?,
            })
        },
    )
    .optional()
    .map_err(|_| "reference review decision lookup unavailable".into())
}

fn decision_state(record: Option<&RecordedDecision>, stable: &str) -> &'static str {
    match record {
        None => "unreviewed",
        Some(value) if value.stable_pair_sha256 != stable => "source_changed_re_review_required",
        Some(value) if value.decision == "keep_separate" => "kept_separate",
        Some(value) if value.decision == "reconsider" => "reconsidered",
        _ => "unsupported_decision",
    }
}

fn source_reference(store: &ProjectStore, id: &str) -> Result<Reference, String> {
    source_reference_on(store.connection(), id)
}

fn source_reference_on(conn: &Connection, id: &str) -> Result<Reference, String> {
    let source = conn
        .query_row(
            "SELECT title,authors_json,year,doi,raw FROM reference WHERE id=?1",
            [id],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, Option<i64>>(2)?,
                    row.get::<_, Option<String>>(3)?,
                    row.get::<_, String>(4)?,
                ))
            },
        )
        .optional()
        .map_err(|_| "reference decision source lookup failed")?
        .ok_or("reference decision source does not exist")?;
    let authors: Vec<String> =
        serde_json::from_str(&source.1).map_err(|_| "invalid reference decision authors")?;
    if authors.len() > 100 {
        return Err("invalid reference decision author count".into());
    }
    Ok(Reference {
        id: id.to_owned(),
        title: source.0,
        authors,
        year: source.2,
        doi: source.3,
        raw_sha256: hash(source.4.as_bytes()),
    })
}

/// Source inspection before an approval is not a transactional snapshot: an
/// external connection could alter a source row or its alias mapping before
/// the project revision/event transaction starts. Recheck all approved source
/// identities *inside* the same transaction that inserts the immutable row.
/// This does not modify, merge or alias any bibliography records.
fn verify_decision_snapshot(
    conn: &Connection,
    left_id: &str,
    right_id: &str,
    revision: i64,
    reviewed_candidate_sha256: &str,
    reviewed_pair_sha256: &str,
) -> Result<(), String> {
    let total: i64 = conn
        .query_row("SELECT COUNT(*) FROM reference", [], |row| row.get(0))
        .map_err(|_| "reference count unavailable during decision commit")?;
    if total > MAX_SCAN {
        return Err("candidate scan incomplete during decision commit".into());
    }
    let alias_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM reference_alias WHERE original_id IN (?1,?2)",
            params![left_id, right_id],
            |row| row.get(0),
        )
        .map_err(|_| "reference aliases unavailable during decision commit")?;
    if alias_count != 0 {
        return Err("reference alias changed before decision commit".into());
    }
    let first = source_reference_on(conn, left_id)?;
    let second = source_reference_on(conn, right_id)?;
    let current = candidate(&first, &second, revision)
        .ok_or("reference pair no longer matches the reviewed candidate")?;
    if current["candidate_sha256"] != reviewed_candidate_sha256
        || stable_pair_sha256(&first, &second) != reviewed_pair_sha256
    {
        return Err("reference source snapshot changed before decision commit".into());
    }
    Ok(())
}

/// Guard BOTH the human F14 approval path and the older explicit reference.merge
/// operation; otherwise a retained keep-separate decision could be overridden
/// through the legacy merge button without a fresh reconsideration.
pub(super) fn guard_direct_merge(store: &ProjectStore, args: &Value) -> Result<(), String> {
    guard_direct_merge_on(store.connection(), args)
}

/// Re-run the binding identity-decision check under the same SQLite write
/// transaction that inserts the alias. A preflight-only guard can race with
/// a concurrently approved immutable keep-separate decision.
pub(super) fn guard_direct_merge_on(conn: &Connection, args: &Value) -> Result<(), String> {
    let canonical = required(args, "canonical_id", 128)?;
    let duplicate = required(args, "duplicate_id", 128)?;
    if canonical == duplicate {
        return Err("cannot merge a reference into itself".into());
    }
    let first = source_reference_on(conn, canonical)?;
    let second = source_reference_on(conn, duplicate)?;
    let (left, right) = sorted_pair(&first, &second);
    let stable = stable_pair_sha256(left, right);
    let prior = latest_decision(conn, &left.id, &right.id)?;
    if decision_state(prior.as_ref(), &stable) == "kept_separate" {
        return Err(
            "reviewer kept these source records separate; a new explicit reconsideration is required"
                .into(),
        );
    }
    Ok(())
}

fn decision_history(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let (left, right) = pair_ids(args)?;
    let limit = bounded(args, "limit", 50, 100)?;
    let first = source_reference(store, &left)?;
    let second = source_reference(store, &right)?;
    let stable = stable_pair_sha256(&first, &second);
    let mut stmt = store
        .connection()
        .prepare(
            "SELECT id,decision,reviewed_candidate_sha256,stable_pair_sha256,
                    review_revision,project_revision,rationale,actor,recorded_at,request_id
             FROM reference_dedup_decisions
             WHERE left_id=?1 AND right_id=?2 ORDER BY project_revision DESC LIMIT ?3",
        )
        .map_err(|_| "reference decision history unavailable")?;
    let rows = stmt
        .query_map(params![left, right, limit], |row| {
            Ok(json!({
                "id":row.get::<_, String>(0)?,"decision":row.get::<_, String>(1)?,
                "candidate_sha256":row.get::<_, String>(2)?,
                "stable_pair_sha256":row.get::<_, String>(3)?,
                "review_revision":row.get::<_, i64>(4)?,
                "project_revision":row.get::<_, i64>(5)?,
                "rationale":row.get::<_, String>(6)?,"actor":row.get::<_, String>(7)?,
                "recorded_at":row.get::<_, String>(8)?,
                "request_id":row.get::<_, String>(9)?,
            }))
        })
        .map_err(|_| "reference decision history unavailable")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "reference decision row invalid")?;
    let latest = latest_decision(store.connection(), &left, &right)?;
    Ok(json!({
        "left_id":left,"right_id":right,"source_pair_sha256":stable,
        "decision_state":decision_state(latest.as_ref(), &stable),
        "rows":rows,"writes":0,"history_limit":limit,
        "source_verification":"Local source record snapshot only; no independent DOI identity validation",
    }))
}

fn record_decision(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
    decision: &'static str,
) -> Result<Value, String> {
    let (left_id, right_id) = pair_ids(args)?;
    let fingerprint = required(args, "candidate_sha256", 64)?;
    if fingerprint.len() != 64
        || !fingerprint
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err("invalid candidate SHA-256".into());
    }
    let rationale = required(args, "rationale", 2000)?.trim();
    if rationale.is_empty() || rationale.chars().any(char::is_control) {
        return Err("human review rationale must be visible nonempty text".into());
    }
    let revision = current_revision(store, ctx)?;
    let (records, scan_truncated) = references(store)?;
    if scan_truncated {
        return Err("candidate scan incomplete; human decision refused".into());
    }
    let first = records
        .iter()
        .find(|record| record.id == left_id)
        .ok_or("left reference missing or already aliased")?;
    let second = records
        .iter()
        .find(|record| record.id == right_id)
        .ok_or("right reference missing or already aliased")?;
    let candidate =
        candidate(first, second, revision).ok_or("pair is not a duplicate candidate")?;
    if candidate["candidate_sha256"] != fingerprint {
        return Err("stale candidate SHA-256; scan and review again".into());
    }
    let stable = stable_pair_sha256(first, second);
    let prior = latest_decision(store.connection(), &left_id, &right_id)?;
    let state = decision_state(prior.as_ref(), &stable);
    match decision {
        "keep_separate" if state == "kept_separate" => {
            return Err("same unchanged sources already kept separate".into());
        }
        "reconsider" if state != "kept_separate" => {
            return Err("no current keep-separate decision to reconsider".into());
        }
        "keep_separate" | "reconsider" => {}
        _ => return Err("unsupported reference decision".into()),
    }
    let id = Uuid::new_v4().to_string();
    let event_payload = json!({
        "decision_id":id,"left_id":left_id,"right_id":right_id,"decision":decision,
        "reviewed_candidate_sha256":fingerprint,"stable_pair_sha256":stable,
        // The full human rationale is retained in the immutable decision row,
        // but not duplicated into the append-only project event / exports.
        // Bind the event to the same exact reviewed text by digest instead.
        "review_revision":revision,
        "rationale_sha256":hash(rationale.as_bytes()),
        "rationale_utf8_bytes":rationale.len(),
    });
    if preview {
        return Ok(json!({
            "decision":decision,"left_id":left_id,"right_id":right_id,
            "candidate_sha256":fingerprint,"stable_pair_sha256":stable,
            "review_revision":revision,"would_create_project_revision":revision + 1,
            "previous_decision_state":state,"preview_only":true,"writes":0,
            "original_reference_rows_deleted":0,"source_rows_deleted":0,
        }));
    }
    let actor = ctx.actor.to_string();
    let request_id = ctx.request_id.to_string();
    let op = if decision == "keep_separate" {
        "reference.dedup_keep_separate"
    } else {
        "reference.dedup_reconsider"
    };
    let ((), new_revision) = collections::mutate(store, op, &event_payload, ctx, |tx, now| {
        verify_decision_snapshot(tx, &left_id, &right_id, revision, fingerprint, &stable)?;
        let refreshed = latest_decision(tx, &left_id, &right_id)?;
        if refreshed != prior {
            return Err("reference decision history changed during approval".into());
        }
        tx.execute(
            "INSERT INTO reference_dedup_decisions
             (id,left_id,right_id,decision,reviewed_candidate_sha256,stable_pair_sha256,
              review_revision,project_revision,rationale,actor,recorded_at,request_id)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12)",
            params![
                id,
                left_id,
                right_id,
                decision,
                fingerprint,
                stable,
                revision,
                revision + 1,
                rationale,
                actor,
                now,
                request_id
            ],
        )
        .map_err(|_| "reference decision insertion failed")?;
        Ok(())
    })?;
    Ok(json!({
        "id":id,"decision":decision,"left_id":left_id,"right_id":right_id,
        "stable_pair_sha256":stable,"candidate_sha256":fingerprint,
        "recorded_project_revision":new_revision,"review_revision":revision,
        "original_reference_rows_deleted":0,"source_rows_deleted":0,
        "event_recorded":true,"automatic_merge":false,
    }))
}

fn build_candidates(store: &ProjectStore, limit: i64) -> Result<Value, String> {
    let revision = store.info().map_err(|_| "project unavailable")?.revision;
    let (references, scan_truncated) = references(store)?;
    let mut candidates = Vec::new();
    for i in 0..references.len() {
        for other in &references[i + 1..] {
            if let Some(mut item) = candidate(&references[i], other, revision) {
                let (left, right) = sorted_pair(&references[i], other);
                let stable = stable_pair_sha256(left, right);
                let prior = latest_decision(store.connection(), &left.id, &right.id)?;
                item["decision_state"] = json!(decision_state(prior.as_ref(), &stable));
                item["last_decision_project_revision"] =
                    json!(prior.as_ref().map(|record| record.project_revision));
                // Provenance is a stable digest over both original source
                // records, never a user-provided suggestion probability.
                item["stable_pair_sha256"] = json!(stable);
                candidates.push(item);
            }
        }
    }
    candidates.sort_by(|a, b| {
        b["score"]
            .as_i64()
            .cmp(&a["score"].as_i64())
            .then_with(|| a["left_id"].as_str().cmp(&b["left_id"].as_str()))
            .then_with(|| a["right_id"].as_str().cmp(&b["right_id"].as_str()))
    });
    let total_candidates = candidates.len();
    candidates.truncate(limit as usize);
    Ok(json!({
        "project_revision":revision,"scan_limit":MAX_SCAN,"scan_truncated":scan_truncated,
        "candidate_count_in_scan":total_candidates,
        "candidates_truncated":total_candidates > limit as usize,
        "candidates":candidates,"writes":0,
        "review_required":true,"automatic_merge":false,
        "verification":"Offline metadata similarity only. A matching DOI is not proof of identity; inspect original records and external evidence before approval."
    }))
}

fn approve(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let canonical = required(args, "canonical_id", 128)?;
    let duplicate = required(args, "duplicate_id", 128)?;
    let fingerprint = required(args, "candidate_sha256", 64)?;
    let rationale = required(args, "rationale", 2000)?.trim();
    if canonical == duplicate
        || rationale.is_empty()
        || !fingerprint.bytes().all(|b| b.is_ascii_hexdigit())
        || fingerprint.len() != 64
    {
        return Err("invalid reviewer approval or candidate digest".into());
    }
    let revision = current_revision(store, ctx)?;
    let (records, scan_truncated) = references(store)?;
    // Refuse a truncated scan on approval; a human should inspect a complete
    // candidate snapshot or use the established explicit merge route.
    if scan_truncated {
        return Err("candidate scan incomplete; approval refused".into());
    }
    let first = records
        .iter()
        .find(|r| r.id == canonical)
        .ok_or("canonical reference not eligible")?;
    let second = records
        .iter()
        .find(|r| r.id == duplicate)
        .ok_or("duplicate reference not eligible")?;
    let (left, right) = if first.id < second.id {
        (first, second)
    } else {
        (second, first)
    };
    let current =
        candidate(left, right, revision).ok_or("references are not duplicate candidates")?;
    if current["eligible_for_approval"] != true {
        return Err(
            "conflicting identifiers or metadata require independent identity resolution".into(),
        );
    }
    if current["candidate_sha256"] != fingerprint {
        return Err("stale candidate fingerprint; review again".into());
    }
    // A locally recorded independent-identity decision cannot be bypassed by
    // the specialized alias approval path. A separate explicit reconsideration
    // must be recorded before the same unchanged records can be aliased.
    guard_direct_merge(store, args)?;
    let result = relations::run(store, "reference.merge", args, ctx, preview)?;
    Ok(
        json!({"decision":"approve_alias","candidate_sha256":fingerprint,
        "human_review_required":true,"reference_rows_deleted":0,"source_rows_deleted":0,
        "alias_operation":result}),
    )
}

fn restore(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    let canonical = required(args, "canonical_id", 128)?;
    let duplicate = required(args, "duplicate_id", 128)?;
    let rationale = required(args, "rationale", 2000)?.trim();
    if canonical == duplicate || rationale.is_empty() {
        return Err("invalid restore approval".into());
    }
    current_revision(store, ctx)?;
    let mapped: Option<String> = store
        .connection()
        .query_row(
            "SELECT canonical_id FROM reference_alias WHERE original_id=?1",
            [duplicate],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| "reference alias lookup failed")?;
    if mapped.as_deref() != Some(canonical) {
        return Err("active alias target mismatch".into());
    }
    let result = relations::run(store, "reference.unmerge", args, ctx, preview)?;
    Ok(
        json!({"decision":"restore_independent_reference","reference_rows_deleted":0,
        "source_rows_deleted":0,"alias_operation":result}),
    )
}

pub(super) fn run(
    store: &mut ProjectStore,
    op: &str,
    args: &Value,
    ctx: &DispatchContext,
    preview: bool,
) -> Result<Value, String> {
    match op {
        "reference.dedup_candidates" => {
            build_candidates(store, bounded(args, "limit", 50, MAX_RESULTS)?)
        }
        "reference.dedup_decision_history" => decision_history(store, args),
        "reference.dedup_keep_separate" => {
            record_decision(store, args, ctx, preview, "keep_separate")
        }
        "reference.dedup_reconsider" => record_decision(store, args, ctx, preview, "reconsider"),
        "reference.dedup_approve" => approve(store, args, ctx, preview),
        "reference.dedup_restore" => restore(store, args, ctx, preview),
        _ => Err("unsupported reference deduplication operation".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::LibraryHandler;
    use chrono::Utc;
    use researchweave_core::{Effect, OperationHandler};
    use researchweave_project::ProjectInfo;
    use uuid::Uuid;

    #[test]
    fn malformed_doi_must_not_be_treated_as_an_absent_identifier() {
        let first = Reference {
            id: "reference-a".into(),
            title: "The same paper".into(),
            authors: vec!["A. Researcher".into()],
            year: Some(2025),
            doi: Some("invalid-identifier".into()),
            raw_sha256: "a".repeat(64),
        };
        let second = Reference {
            id: "reference-b".into(),
            title: first.title.clone(),
            authors: first.authors.clone(),
            year: first.year,
            doi: None,
            raw_sha256: "b".repeat(64),
        };
        let caution = candidate(&first, &second, 3).unwrap();
        assert_eq!(caution["signals"]["doi_unparseable"], true);
        assert_eq!(caution["signals"]["doi_conflict"], true);
        assert_eq!(caution["eligible_for_approval"], false);
        assert_eq!(caution["review_status"], "conflicting_metadata");
        assert_eq!(caution["score"], 0);
        let mut valid_missing = first;
        valid_missing.doi = None;
        let review = candidate(&valid_missing, &second, 3).unwrap();
        assert_eq!(review["signals"]["doi_unparseable"], false);
        assert_eq!(review["eligible_for_approval"], true);
    }

    fn fixture() -> (tempfile::TempDir, LibraryHandler, DispatchContext) {
        let folder = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        ProjectStore::create(
            folder.path().join(project_id.to_string()),
            &ProjectInfo {
                id: project_id.to_string(),
                title: "F14 dedup test".into(),
                question: "What evidence applies?".into(),
                design: "systematic_review".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: Utc::now().to_rfc3339(),
            },
        )
        .unwrap();
        let handler = LibraryHandler::new(folder.path().to_path_buf());
        (
            folder,
            handler,
            DispatchContext {
                request_id: Uuid::new_v4(),
                project_id,
                actor: "reviewer".into(),
                expected_revision: Some(0),
            },
        )
    }

    fn add(
        handler: &LibraryHandler,
        ctx: &mut DispatchContext,
        title: &str,
        author: &str,
        year: i64,
        doi: Option<&str>,
    ) -> String {
        let body = format!("@article{{test{year}, title={{{title}}}, author={{{author}}}}}");
        let payload = json!({"project_id":ctx.project_id.to_string(),"title":title,"format":"bibtex", "raw":body,
            "authors":[author],"year":year,"doi":doi,"kind":"article","metadata":{}});
        let result = handler.execute("library.reference_add", &payload, ctx);
        assert_eq!(result["status"], "ok", "{result}");
        let id = result["data"]["reference_id"].as_str().unwrap().to_owned();
        ctx.expected_revision = Some(ctx.expected_revision.unwrap() + 1);
        ctx.request_id = Uuid::new_v4();
        id
    }

    #[test]
    fn durable_keep_separate_reopen_cas_reconsider_and_merge_guard() {
        let (folder, handler, mut ctx) = fixture();
        let first = add(
            &handler,
            &mut ctx,
            "Cognition شناخت",
            "Zoë Researcher",
            2025,
            Some("10.1234/first"),
        );
        let second = add(
            &handler,
            &mut ctx,
            "Cognition شناخت",
            "Zoë Researcher",
            2025,
            Some("10.1234/second"),
        );
        let path = folder.path().join(ctx.project_id.to_string());
        let search = json!({"project_id":ctx.project_id.to_string()});
        let candidates = handler.execute("reference.dedup_candidates", &search, &ctx);
        assert_eq!(candidates["status"], "ok", "{candidates}");
        let candidate = &candidates["data"]["candidates"][0];
        // Same title, author and year but contradictory DOIs: an alias is
        // refused, while keeping the works distinct is still permitted.
        assert_eq!(candidate["eligible_for_approval"], false);
        assert_eq!(candidate["decision_state"], "unreviewed");
        let fingerprint = candidate["candidate_sha256"].as_str().unwrap().to_owned();
        let source_hash = candidate["stable_pair_sha256"].as_str().unwrap().to_owned();
        let keep = json!({"project_id":ctx.project_id.to_string(),
            "left_id":first,"right_id":second,"candidate_sha256":fingerprint,
            "rationale":"Reviewed original records; conflicting DOI means separate publications"});
        let invalid = handler.execute(
            "reference.dedup_keep_separate",
            &json!({"project_id":ctx.project_id.to_string(),"left_id":first,
                "right_id":second,"candidate_sha256":"0".repeat(64),
                "rationale":"reviewed source"}),
            &ctx,
        );
        assert_eq!(invalid["status"], "failed");
        let preview = handler.preview("reference.dedup_keep_separate", &keep, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["preview_only"], true);
        assert_eq!(preview["data"]["writes"], 0);
        assert_eq!(preview["impact"]["local_writes"], json!([]));
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            2
        );
        let accepted = handler.execute("reference.dedup_keep_separate", &keep, &ctx);
        assert_eq!(accepted["status"], "ok", "{accepted}");
        assert_eq!(accepted["data"]["stable_pair_sha256"], source_hash);
        assert_eq!(accepted["data"]["recorded_project_revision"], 3);
        assert_eq!(
            accepted["impact"]["local_writes"],
            json!(["reference_dedup_decisions", "events", "project"])
        );
        let committed = ProjectStore::open(&path).unwrap();
        let payload_json: String = committed
            .connection()
            .query_row(
                "SELECT payload_json FROM events WHERE sequence=3",
                [],
                |row| row.get(0),
            )
            .unwrap();
        let event_payload: Value = serde_json::from_str(&payload_json).unwrap();
        let (stored_id, stored_rationale, stored_revision): (String, String, i64) = committed
            .connection()
            .query_row(
                "SELECT id,rationale,project_revision FROM reference_dedup_decisions",
                [],
                |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
            )
            .unwrap();
        assert_eq!(event_payload["decision_id"], stored_id);
        assert_eq!(accepted["data"]["id"], stored_id);
        assert_eq!(event_payload["stable_pair_sha256"], source_hash);
        assert_eq!(event_payload["review_revision"], 2);
        assert_eq!(stored_revision, 3);
        assert_eq!(
            event_payload["rationale_sha256"],
            hash(stored_rationale.as_bytes())
        );
        assert_eq!(stored_rationale, keep["rationale"].as_str().unwrap());
        drop(committed);
        assert_eq!(
            handler.execute("reference.dedup_keep_separate", &keep, &ctx)["status"],
            "failed"
        );
        ctx.expected_revision = Some(3);
        ctx.request_id = Uuid::new_v4();
        let reopened = LibraryHandler::new(folder.path().to_path_buf());
        let history =
            json!({"project_id":ctx.project_id.to_string(),"left_id":first,"right_id":second});
        let recorded = reopened.execute("reference.dedup_decision_history", &history, &ctx);
        assert_eq!(recorded["status"], "ok", "{recorded}");
        assert_eq!(recorded["data"]["decision_state"], "kept_separate");
        assert_eq!(recorded["data"]["rows"].as_array().unwrap().len(), 1);
        assert_eq!(recorded["data"]["rows"][0]["actor"], "reviewer");
        let after_scan = reopened.execute("reference.dedup_candidates", &search, &ctx);
        assert_eq!(
            after_scan["data"]["candidates"][0]["decision_state"],
            "kept_separate"
        );
        assert_eq!(
            after_scan["data"]["candidates"][0]["stable_pair_sha256"],
            source_hash
        );
        let merge = json!({"project_id":ctx.project_id.to_string(),
            "canonical_id":first,"duplicate_id":second,"rationale":"wrongly merging kept sources"});
        let scoped = ProjectStore::open(&path).unwrap();
        let transaction = scoped.connection().unchecked_transaction().unwrap();
        let denied = guard_direct_merge_on(&transaction, &merge).unwrap_err();
        assert!(denied.contains("kept these source records separate"));
        transaction.rollback().unwrap();
        drop(scoped);
        assert_eq!(
            reopened.preview("reference.merge", &merge, &ctx)["status"],
            "failed"
        );
        assert_eq!(
            reopened.execute("reference.merge", &merge, &ctx)["status"],
            "failed"
        );
        let reconsider = json!({"project_id":ctx.project_id.to_string(),
            "left_id":second,"right_id":first,
            "candidate_sha256":after_scan["data"]["candidates"][0]["candidate_sha256"],
            "rationale":"Explicit second reviewer has now re-examined the two sources"});
        assert_eq!(
            reopened.preview("reference.dedup_reconsider", &reconsider, &ctx)["status"],
            "ok"
        );
        let accepted = reopened.execute("reference.dedup_reconsider", &reconsider, &ctx);
        assert_eq!(accepted["status"], "ok", "{accepted}");
        ctx.expected_revision = Some(4);
        ctx.request_id = Uuid::new_v4();
        let reconsidered = reopened.execute("reference.dedup_decision_history", &history, &ctx);
        assert_eq!(reconsidered["data"]["decision_state"], "reconsidered");
        assert_eq!(reconsidered["data"]["rows"].as_array().unwrap().len(), 2);
        let scoped = ProjectStore::open(&path).unwrap();
        let transaction = scoped.connection().unchecked_transaction().unwrap();
        assert!(guard_direct_merge_on(&transaction, &merge).is_ok());
        transaction.rollback().unwrap();
        drop(scoped);
        let merged = reopened.execute("reference.merge", &merge, &ctx);
        assert_eq!(merged["status"], "ok", "{merged}");
        let store = ProjectStore::open(&path).unwrap();
        let (references, aliases, decisions, events): (i64, i64, i64, i64) = (
            store
                .connection()
                .query_row("SELECT count(*) FROM reference", [], |r| r.get(0))
                .unwrap(),
            store
                .connection()
                .query_row("SELECT count(*) FROM reference_alias", [], |r| r.get(0))
                .unwrap(),
            store
                .connection()
                .query_row("SELECT count(*) FROM reference_dedup_decisions", [], |r| {
                    r.get(0)
                })
                .unwrap(),
            store
                .connection()
                .query_row("SELECT count(*) FROM events", [], |r| r.get(0))
                .unwrap(),
        );
        assert_eq!((references, aliases, decisions, events), (2, 1, 2, 5));
        assert!(store
            .connection()
            .execute(
                "UPDATE reference_dedup_decisions SET rationale='tampered'",
                []
            )
            .is_err());
        assert!(store
            .connection()
            .execute("DELETE FROM reference_dedup_decisions", [])
            .is_err());
    }

    #[test]
    fn source_snapshot_rechecked_in_commit_transaction_and_unrelated_revision_does_not_erase_review(
    ) {
        let (folder, handler, mut ctx) = fixture();
        let first = add(
            &handler,
            &mut ctx,
            "Same article",
            "Researcher One",
            2024,
            Some("10.1234/first"),
        );
        let second = add(
            &handler,
            &mut ctx,
            "Same article",
            "Researcher One",
            2024,
            Some("10.1234/second"),
        );
        let request = json!({"project_id":ctx.project_id.to_string()});
        let scanned = handler.execute("reference.dedup_candidates", &request, &ctx);
        let candidate = &scanned["data"]["candidates"][0];
        let fingerprint = candidate["candidate_sha256"].as_str().unwrap().to_owned();
        let stable = candidate["stable_pair_sha256"].as_str().unwrap().to_owned();
        let revision = i64::try_from(ctx.expected_revision.unwrap()).unwrap();
        let path = folder.path().join(ctx.project_id.to_string());
        let store = ProjectStore::open(&path).unwrap();
        let (left, right) = if first < second {
            (&first, &second)
        } else {
            (&second, &first)
        };
        let tx = store.connection().unchecked_transaction().unwrap();
        assert!(
            verify_decision_snapshot(&tx, left, right, revision, &fingerprint, &stable).is_ok()
        );
        tx.rollback().unwrap();
        drop(store);

        let keep = json!({"project_id":ctx.project_id.to_string(),
            "left_id":first,"right_id":second,
            "candidate_sha256":fingerprint,
            "rationale":"Two independent DOI registrations; keep sources distinct"});
        assert_eq!(
            handler.execute("reference.dedup_keep_separate", &keep, &ctx)["status"],
            "ok"
        );
        ctx.expected_revision = Some(ctx.expected_revision.unwrap() + 1);
        ctx.request_id = Uuid::new_v4();

        // Unrelated writes invalidate candidate_sha256 but do not invalidate
        // the decision over the unchanged pair's stable bibliographic sources.
        let _third = add(
            &handler,
            &mut ctx,
            "Another independent article",
            "Other Author",
            2023,
            None,
        );
        let rescanned = handler.execute("reference.dedup_candidates", &request, &ctx);
        let current = &rescanned["data"]["candidates"][0];
        assert_eq!(current["decision_state"], "kept_separate");
        assert_eq!(current["stable_pair_sha256"], stable);
        assert_ne!(current["candidate_sha256"], fingerprint);
        let history = handler.execute(
            "reference.dedup_decision_history",
            &json!({"project_id":ctx.project_id.to_string(),
                "left_id":first,"right_id":second}),
            &ctx,
        );
        assert_eq!(history["data"]["rows"].as_array().unwrap().len(), 1);
        assert_eq!(history["data"]["decision_state"], "kept_separate");
    }

    #[test]
    fn transaction_source_snapshot_rejects_direct_edits_or_alias_without_project_revision_bump() {
        let (folder, handler, mut ctx) = fixture();
        let first = add(
            &handler,
            &mut ctx,
            "Identical title",
            "Author One",
            2025,
            None,
        );
        let second = add(
            &handler,
            &mut ctx,
            "Identical title",
            "Author One",
            2025,
            None,
        );
        let path = folder.path().join(ctx.project_id.to_string());
        let scan = handler.execute(
            "reference.dedup_candidates",
            &json!({"project_id":ctx.project_id.to_string()}),
            &ctx,
        );
        let candidate = &scan["data"]["candidates"][0];
        let fingerprint = candidate["candidate_sha256"].as_str().unwrap().to_owned();
        let stable = candidate["stable_pair_sha256"].as_str().unwrap().to_owned();
        let revision = i64::try_from(ctx.expected_revision.unwrap()).unwrap();
        let (left, right) = if first < second {
            (&first, &second)
        } else {
            (&second, &first)
        };
        let store = ProjectStore::open(&path).unwrap();
        assert!(verify_decision_snapshot(
            store.connection(),
            left,
            right,
            revision,
            &fingerprint,
            &stable
        )
        .is_ok());
        let original_raw: String = store
            .connection()
            .query_row("SELECT raw FROM reference WHERE id=?1", [left], |row| {
                row.get(0)
            })
            .unwrap();
        store
            .connection()
            .execute(
                "UPDATE reference SET raw=?1 WHERE id=?2",
                params!["@article{tampered}", left],
            )
            .unwrap();
        assert_eq!(store.info().unwrap().revision, revision);
        assert!(verify_decision_snapshot(
            store.connection(),
            left,
            right,
            revision,
            &fingerprint,
            &stable
        )
        .is_err());
        let attempted = handler.execute(
            "reference.dedup_keep_separate",
            &json!({"project_id":ctx.project_id.to_string(),
                "left_id":first,"right_id":second,
                "candidate_sha256":fingerprint,
                "rationale":"Reviewed pair before unexpected source edit"}),
            &ctx,
        );
        assert_eq!(attempted["status"], "failed", "{attempted}");

        // Restore exactly the source text to distinguish alias changes from
        // changes to the candidate fingerprint itself.
        store
            .connection()
            .execute(
                "UPDATE reference SET raw=?1 WHERE id=?2",
                params![original_raw, left],
            )
            .unwrap();
        assert!(verify_decision_snapshot(
            store.connection(),
            left,
            right,
            revision,
            &fingerprint,
            &stable
        )
        .is_ok());
        store
            .connection()
            .execute(
                "INSERT INTO reference_alias(original_id,canonical_id,reason) VALUES (?1,?2,'synthetic alias')",
                params![left, right],
            )
            .unwrap();
        assert!(verify_decision_snapshot(
            store.connection(),
            left,
            right,
            revision,
            &fingerprint,
            &stable
        )
        .is_err());
        assert_eq!(
            store
                .connection()
                .query_row::<i64, _, _>(
                    "SELECT COUNT(*) FROM reference_dedup_decisions",
                    [],
                    |row| row.get(0)
                )
                .unwrap(),
            0
        );
    }

    #[test]
    fn conservative_candidates_include_unicode_and_block_doi_collision_overmerge() {
        let (_folder, handler, mut ctx) = fixture();
        let first = add(
            &handler,
            &mut ctx,
            "Neural Networks: شناخت",
            "Zoë García",
            2024,
            Some("10.1234/NEURO"),
        );
        let second = add(
            &handler,
            &mut ctx,
            "Neural Networks - شناخت",
            "Zoë García",
            2024,
            Some("https://doi.org/10.1234/neuro"),
        );
        let collision = add(
            &handler,
            &mut ctx,
            "Different science",
            "Someone Else",
            2023,
            Some("10.1234/neuro"),
        );
        let conflicting_doi = add(
            &handler,
            &mut ctx,
            "Neural Networks شناخت",
            "Zoë García",
            2024,
            Some("10.4321/different"),
        );
        let unrelated = add(
            &handler,
            &mut ctx,
            "Novel independent paper",
            "Other Researcher",
            2024,
            Some("10.5678/other"),
        );
        let args = json!({"project_id":ctx.project_id.to_string(),"limit":50});
        let before = handler.preview("reference.dedup_candidates", &args, &ctx);
        let after = handler.execute("reference.dedup_candidates", &args, &ctx);
        assert_eq!(before, after);
        assert_eq!(after["status"], "ok", "{after}");
        assert_eq!(after["data"]["writes"], 0);
        let candidates = after["data"]["candidates"].as_array().unwrap();
        assert!(candidates.iter().any(|c| {
            (c["left_id"] == first && c["right_id"] == second
                || c["left_id"] == second && c["right_id"] == first)
                && c["eligible_for_approval"] == true
                && c["score"] == 100
        }));
        assert!(candidates.iter().any(|c| {
            (c["left_id"] == first && c["right_id"] == collision
                || c["left_id"] == collision && c["right_id"] == first)
                && c["eligible_for_approval"] == false
                && c["review_status"] == "conflicting_metadata"
        }));
        let collision_review = candidates
            .iter()
            .find(|c| {
                (c["left_id"] == first && c["right_id"] == collision)
                    || (c["left_id"] == collision && c["right_id"] == first)
            })
            .unwrap();
        let collision_approval = handler.execute(
            "reference.dedup_approve",
            &json!({"project_id":ctx.project_id.to_string(),"canonical_id":first,
                "duplicate_id":collision,"candidate_sha256":collision_review["candidate_sha256"],
                "rationale":"Should reject despite matching DOI"}),
            &ctx,
        );
        assert_eq!(
            collision_approval["status"], "failed",
            "{collision_approval}"
        );
        assert!(candidates.iter().any(|c| {
            (c["left_id"] == first && c["right_id"] == conflicting_doi
                || c["left_id"] == conflicting_doi && c["right_id"] == first)
                && c["eligible_for_approval"] == false
                && c["signals"]["doi_conflict"] == true
        }));
        assert!(!candidates
            .iter()
            .any(|c| c["left_id"] == unrelated || c["right_id"] == unrelated));
        assert_eq!(
            LibraryHandler::capabilities()
                .into_iter()
                .find(|cap| cap.operation == "reference.dedup_candidates")
                .unwrap()
                .effect,
            Effect::Read
        );
        assert_eq!(
            LibraryHandler::capabilities()
                .into_iter()
                .find(|cap| cap.operation == "reference.dedup_approve")
                .unwrap()
                .effect,
            Effect::LocalWrite
        );
    }

    #[test]
    fn reviewed_fingerprint_approval_restore_restart_preserves_all_original_references() {
        let (folder, handler, mut ctx) = fixture();
        let first = add(
            &handler,
            &mut ctx,
            "Neuropsychology فارسی",
            "Zoë García",
            2025,
            Some("10.1111/abc"),
        );
        let second = add(
            &handler,
            &mut ctx,
            "Neuropsychology  فارسی",
            "Zoë García",
            2025,
            Some("DOI:10.1111/ABC"),
        );
        let args = json!({"project_id":ctx.project_id.to_string()});
        let pre = handler.execute("reference.dedup_candidates", &args, &ctx);
        assert_eq!(pre["status"], "ok", "{pre}");
        let item = &pre["data"]["candidates"][0];
        assert_eq!(item["eligible_for_approval"], true);
        let fingerprint = item["candidate_sha256"].as_str().unwrap();
        let approval = json!({"project_id":ctx.project_id.to_string(),"canonical_id":first,
            "duplicate_id":second,"candidate_sha256":fingerprint,
            "rationale":"Compared original article metadata and confirmed same work"});
        let wrong = handler.execute(
            "reference.dedup_approve",
            &json!({"project_id":ctx.project_id.to_string(),"canonical_id":first,
                "duplicate_id":second,"candidate_sha256":"0".repeat(64),"rationale":"reviewed"}),
            &ctx,
        );
        assert_eq!(wrong["status"], "failed");
        let preview = handler.preview("reference.dedup_approve", &approval, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["impact"]["local_writes"], json!([]));
        let accepted = handler.execute("reference.dedup_approve", &approval, &ctx);
        assert_eq!(accepted["status"], "ok", "{accepted}");
        assert_eq!(accepted["data"]["alias_operation"]["reversible"], true);
        assert_eq!(
            handler.execute("reference.dedup_approve", &approval, &ctx)["status"],
            "failed"
        );
        let reopened = LibraryHandler::new(folder.path().to_path_buf());
        let resolved = reopened.execute(
            "reference.resolve",
            &json!({"project_id":ctx.project_id.to_string(),"reference_id":second}),
            &ctx,
        );
        assert_eq!(resolved["data"]["is_alias"], true);
        assert_eq!(resolved["data"]["canonical_id"], first);
        let path = folder.path().join(ctx.project_id.to_string());
        let raw_first = reopened.execute(
            "library.reference_export",
            &json!({"project_id":ctx.project_id.to_string(),"reference_id":first}),
            &ctx,
        );
        let raw_second = reopened.execute(
            "library.reference_export",
            &json!({"project_id":ctx.project_id.to_string(),"reference_id":second}),
            &ctx,
        );
        assert!(raw_first["data"]["raw"].as_str().unwrap().contains("فارسی"));
        assert!(raw_second["data"]["raw"]
            .as_str()
            .unwrap()
            .contains("فارسی"));
        let mut restore_ctx = ctx.clone();
        restore_ctx.expected_revision = Some(3);
        restore_ctx.request_id = Uuid::new_v4();
        let wrong_restore = reopened.execute(
            "reference.dedup_restore",
            &json!({"project_id":ctx.project_id.to_string(),"canonical_id":second,
                "duplicate_id":first,"rationale":"wrong mapping"}),
            &restore_ctx,
        );
        assert_eq!(wrong_restore["status"], "failed");
        let restore_args = json!({"project_id":ctx.project_id.to_string(),"canonical_id":first,
            "duplicate_id":second,"rationale":"Human reviewer reverted identity assessment"});
        let restored = reopened.execute("reference.dedup_restore", &restore_args, &restore_ctx);
        assert_eq!(restored["status"], "ok", "{restored}");
        assert_eq!(restored["data"]["alias_operation"]["reverted"], true);
        let store = ProjectStore::open(&path).unwrap();
        assert_eq!(store.info().unwrap().revision, 4);
        assert_eq!(
            store
                .connection()
                .query_row("SELECT count(*) FROM reference", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            2
        );
        assert_eq!(
            store
                .connection()
                .query_row("SELECT count(*) FROM reference_alias", [], |r| r
                    .get::<_, i64>(0))
                .unwrap(),
            0
        );
        assert_eq!(
            store
                .connection()
                .query_row("SELECT count(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            4
        );
        assert_eq!(
            reopened.execute("reference.dedup_restore", &restore_args, &restore_ctx)["status"],
            "failed"
        );
        let reloaded = LibraryHandler::new(folder.path().to_path_buf());
        let after = reloaded.execute("reference.dedup_candidates", &args, &restore_ctx);
        assert_eq!(after["status"], "ok", "{after}");
        assert_ne!(
            after["data"]["candidates"][0]["candidate_sha256"],
            item["candidate_sha256"]
        );
        let cross = reloaded.execute(
            "reference.dedup_candidates",
            &json!({"project_id":Uuid::new_v4().to_string()}),
            &restore_ctx,
        );
        assert_eq!(cross["status"], "failed");
        let bound = LibraryHandler::bound(ctx.project_id, &path).unwrap();
        let wrong_context = DispatchContext {
            project_id: Uuid::new_v4(),
            ..restore_ctx
        };
        assert_eq!(
            bound.execute("reference.dedup_candidates", &args, &wrong_context)["status"],
            "failed"
        );
    }

    #[test]
    fn empty_and_invalid_limits_never_mutate() {
        let (folder, handler, ctx) = fixture();
        let args = json!({"project_id":ctx.project_id.to_string()});
        let empty = handler.execute("reference.dedup_candidates", &args, &ctx);
        assert_eq!(empty["status"], "ok");
        assert_eq!(empty["data"]["candidates"], json!([]));
        for limit in [json!(0), json!(101), json!("7"), json!(-2)] {
            assert_eq!(
                handler.execute(
                    "reference.dedup_candidates",
                    &json!({"project_id":ctx.project_id.to_string(),"limit":limit}),
                    &ctx
                )["status"],
                "failed"
            );
        }
        let store = ProjectStore::open(folder.path().join(ctx.project_id.to_string())).unwrap();
        assert_eq!(store.info().unwrap().revision, 0);
    }

    #[test]
    fn scan_cap_is_reported_and_approval_refuses_incomplete_library() {
        let (folder, handler, ctx) = fixture();
        let path = folder.path().join(ctx.project_id.to_string());
        let store = ProjectStore::open(&path).unwrap();
        for index in 0..201 {
            let id = format!("ref-{index:04}");
            store.connection().execute(
                "INSERT INTO reference (id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES (?1,?2,'[]',2025,NULL,'article','bibtex',?3,'{}','unverified','fixture')",
                params![id,format!("Distinct paper {index}"),format!("@article{{item{index}}}")],
            ).unwrap();
        }
        drop(store);
        let result = handler.execute(
            "reference.dedup_candidates",
            &json!({"project_id":ctx.project_id.to_string(),"limit":1}),
            &ctx,
        );
        assert_eq!(result["status"], "ok", "{result}");
        assert_eq!(result["data"]["scan_truncated"], true);
        assert_eq!(result["data"]["scan_limit"], 200);
        let rejected=handler.execute("reference.dedup_approve",
            &json!({"project_id":ctx.project_id.to_string(),"canonical_id":"ref-0000",
                "duplicate_id":"ref-0001","candidate_sha256":"a".repeat(64),"rationale":"reviewed"}),&ctx);
        assert_eq!(rejected["status"], "failed");
        assert!(rejected["error"]["message"]
            .as_str()
            .unwrap()
            .contains("scan incomplete"));
        let reopened = ProjectStore::open(&path).unwrap();
        assert_eq!(reopened.info().unwrap().revision, 0);
        assert_eq!(
            reopened
                .connection()
                .query_row("SELECT count(*) FROM reference_alias", [], |r| r
                    .get::<_, i64>(0))
                .unwrap(),
            0
        );
    }
}
