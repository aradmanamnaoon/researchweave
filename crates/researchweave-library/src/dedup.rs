//! Conservative offline duplicate candidates and explicit reversible identity decisions.
//! No reference, source, citation, or raw bibliographic record is deleted.
use super::{bounded, collections::current_revision, relations, required};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

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
    let doi_conflict = left_doi.is_some() && right_doi.is_some() && left_doi != right_doi;
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
            "title_equal":title_equal,"first_author_equal":author_equal,"year_equal":year_equal},
        "review_status":if conflict {"conflicting_metadata"} else {"review_required"},
        "eligible_for_approval":safe_to_review,
        "automatically_merged":false,
    }))
}

fn build_candidates(store: &ProjectStore, limit: i64) -> Result<Value, String> {
    let revision = store.info().map_err(|_| "project unavailable")?.revision;
    let (references, scan_truncated) = references(store)?;
    let mut candidates = Vec::new();
    for i in 0..references.len() {
        for other in &references[i + 1..] {
            if let Some(item) = candidate(&references[i], other, revision) {
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
