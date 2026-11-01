//! F03: source-bound, immutable local reviewer comments, not Word Track Changes.
//! Offsets are Unicode scalar positions, never UTF-8 bytes or grapheme clusters.
use super::{digest, mutate};
use researchweave_core::DispatchContext;
use researchweave_project::ProjectStore;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use uuid::Uuid;

struct Anchor<'a> {
    manuscript_id: &'a str,
    section: &'a str,
    revision: i64,
    body_sha256: &'a str,
    start: usize,
    end: usize,
    quote: &'a str,
    reviewer: &'a str,
    comment: &'a str,
    expected_project_revision: i64,
}

fn bounded<'a>(args: &'a Value, name: &str, max: usize) -> Result<&'a str, String> {
    let value = args
        .get(name)
        .and_then(Value::as_str)
        .ok_or("comment field missing")?;
    if value.trim().is_empty() || value.chars().count() > max || value.contains('\0') {
        return Err(format!("invalid comment {name}"));
    }
    Ok(value)
}

fn anchor<'a>(args: &'a Value, ctx: &DispatchContext) -> Result<Anchor<'a>, String> {
    let expected = ctx
        .expected_revision
        .and_then(|r| i64::try_from(r).ok())
        .ok_or("explicit expected project revision required")?;
    let manuscript_id = bounded(args, "manuscript_id", 128)?;
    if manuscript_id.len() > 128 {
        return Err("manuscript ID too long".into());
    }
    let section = bounded(args, "section", 160)?;
    let revision = args["source_revision"]
        .as_i64()
        .filter(|r| *r > 0)
        .ok_or("positive source_revision required")?;
    let body_sha256 = bounded(args, "source_body_sha256", 64)?;
    if body_sha256.len() != 64
        || !body_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err("invalid source body SHA-256".into());
    }
    let start = args["start_scalar"]
        .as_u64()
        .and_then(|n| usize::try_from(n).ok())
        .ok_or("invalid start_scalar")?;
    let end = args["end_scalar"]
        .as_u64()
        .and_then(|n| usize::try_from(n).ok())
        .ok_or("invalid end_scalar")?;
    if start >= end || end > 1_000_000 || end - start > 2_048 {
        return Err("invalid quote span".into());
    }
    let quote = bounded(args, "quote", 2_048)?;
    if quote.chars().count() != end - start {
        return Err("quote/span Unicode scalar length mismatch".into());
    }
    let reviewer = bounded(args, "reviewer", 160)?;
    let comment = bounded(args, "comment", 4_000)?;
    if comment.len() > 16_000 || reviewer.len() > 640 {
        return Err("comment byte limit exceeded".into());
    }
    Ok(Anchor {
        manuscript_id,
        section,
        revision,
        body_sha256,
        start,
        end,
        quote,
        reviewer,
        comment,
        expected_project_revision: expected,
    })
}

fn validate_source(conn: &Connection, a: &Anchor<'_>) -> Result<(), String> {
    let current_project_revision: i64 = conn
        .query_row("SELECT revision FROM project", [], |row| row.get(0))
        .map_err(|_| "project revision unavailable")?;
    if current_project_revision != a.expected_project_revision {
        return Err("stale project revision; preview again".into());
    }
    let latest: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(revision),0) FROM manuscripts WHERE id=?1 AND section=?2",
            params![a.manuscript_id, a.section],
            |row| row.get(0),
        )
        .map_err(|_| "source manuscript unavailable")?;
    if latest != a.revision {
        return Err("stale manuscript section revision; preview again".into());
    }
    let body: String = conn
        .query_row(
            "SELECT body FROM manuscripts WHERE id=?1 AND section=?2 AND revision=?3",
            params![a.manuscript_id, a.section, a.revision],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| "source manuscript unreadable")?
        .ok_or("source manuscript revision not found")?;
    if digest(body.as_bytes()) != a.body_sha256 {
        return Err("source manuscript SHA-256 mismatch; preview again".into());
    }
    let actual: String = body.chars().skip(a.start).take(a.end - a.start).collect();
    if actual != a.quote {
        return Err("quote does not match Unicode scalar anchor".into());
    }
    // This first narrow slice rejects overlap on the same immutable section
    // revision rather than pretending to resolve conflicting markup.
    let overlaps: i64 = conn
        .query_row(
            "SELECT count(*) FROM manuscript_comments
             WHERE manuscript_id=?1 AND section=?2 AND source_revision=?3
               AND start_scalar < ?4 AND end_scalar > ?5",
            params![
                a.manuscript_id,
                a.section,
                a.revision,
                a.end as i64,
                a.start as i64
            ],
            |row| row.get(0),
        )
        .map_err(|_| "comment overlap check failed")?;
    if overlaps != 0 {
        return Err("overlapping comment already anchored to this source revision".into());
    }
    Ok(())
}

fn preview_digest(a: &Anchor<'_>, ctx: &DispatchContext) -> String {
    // Not a secret or electronic signature. Hosts MUST independently obtain
    // explicit human approval before using this preview-bound digest to write.
    // The trusted host allocates a NEW command request_id at execution. Do not
    // bind this ephemeral ID to a preview: authorization is enforced by the
    // host's one-use approval, the project CAS, and the append-only event chain.
    digest(
        serde_json::to_string(&json!({
            "schema":"rw-manuscript-comment-preview-v1",
            "project_id":ctx.project_id,
            "actor":ctx.actor,
            "expected_project_revision":a.expected_project_revision,
            "manuscript_id":a.manuscript_id,
            "section":a.section,
            "source_revision":a.revision,
            "source_body_sha256":a.body_sha256,
            "start_scalar":a.start,
            "end_scalar":a.end,
            "quote_sha256":digest(a.quote.as_bytes()),
            "reviewer_sha256":digest(a.reviewer.as_bytes()),
            "comment_sha256":digest(a.comment.as_bytes())
        }))
        .expect("in-memory preview JSON")
        .as_bytes(),
    )
}

pub(super) fn preview(
    store: &ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let a = anchor(args, ctx)?;
    validate_source(store.connection(), &a)?;
    Ok(json!({
        "preview":true,
        "writes":0,
        "approved":false,
        "source_revision":a.revision,
        "source_body_sha256":a.body_sha256,
        "start_scalar":a.start,
        "end_scalar":a.end,
        "quote_sha256":digest(a.quote.as_bytes()),
        "comment_characters":a.comment.chars().count(),
        "comment_text_redacted":true,
        "reviewer_text_redacted":true,
        "preview_sha256":preview_digest(&a,ctx),
        "requires_explicit_human_approval":true,
        "word_track_changes_supported":false
    }))
}

pub(super) fn record(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let a = anchor(args, ctx)?;
    let approved = args["approved_preview_sha256"]
        .as_str()
        .ok_or("approved preview digest required")?;
    if approved != preview_digest(&a, ctx) {
        return Err("approved preview no longer matches comment, source or project".into());
    }
    let comment_id = Uuid::new_v4().to_string();
    let payload = json!({
        "comment_id":comment_id,
        "manuscript_id":a.manuscript_id,
        "section":a.section,
        "source_revision":a.revision,
        "source_body_sha256":a.body_sha256,
        "start_scalar":a.start,
        "end_scalar":a.end,
        "quote_sha256":digest(a.quote.as_bytes()),
        "reviewer_sha256":digest(a.reviewer.as_bytes()),
        "comment_sha256":digest(a.comment.as_bytes()),
        "text_redacted":true
    });
    let (_, revision) = mutate(store, "writing.comment_record", ctx, &payload, |tx, now| {
        // Atomic CAS and manuscript/overlap recheck inside the same transaction.
        validate_source(tx, &a)?;
        tx.execute(
            "INSERT INTO manuscript_comments
             (id,manuscript_id,section,source_revision,source_body_sha256,
              start_scalar,end_scalar,quote,reviewer,comment,actor,recorded_at,project_revision)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13)",
            params![
                comment_id,
                a.manuscript_id,
                a.section,
                a.revision,
                a.body_sha256,
                a.start as i64,
                a.end as i64,
                a.quote,
                a.reviewer,
                a.comment,
                ctx.actor,
                now,
                a.expected_project_revision + 1
            ],
        )
        .map_err(|_| "immutable comment insertion failed")?;
        Ok(())
    })?;
    Ok(json!({
        "comment_id":comment_id,
        "project_revision":revision,
        "source_revision":a.revision,
        "source_body_sha256":a.body_sha256,
        "appended":true,
        "manuscript_body_mutated":false,
        "external_verification":false,
        "word_track_changes_supported":false
    }))
}

pub(super) fn list(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let manuscript_id = bounded(args, "manuscript_id", 128)?;
    let section = bounded(args, "section", 160)?;
    let mut statement = store.connection().prepare(
        "SELECT c.id,c.source_revision,c.source_body_sha256,c.start_scalar,c.end_scalar,
                c.quote,c.reviewer,c.comment,c.actor,c.recorded_at,c.project_revision,
                m.body,
                (SELECT MAX(revision) FROM manuscripts WHERE id=c.manuscript_id AND section=c.section)
         FROM manuscript_comments c JOIN manuscripts m
           ON m.id=c.manuscript_id AND m.section=c.section AND m.revision=c.source_revision
         WHERE c.manuscript_id=?1 AND c.section=?2
         ORDER BY c.project_revision,c.id LIMIT 1001",
    ).map_err(|_| "comment listing unavailable")?;
    let rows = statement
        .query_map(params![manuscript_id, section], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, i64>(3)?,
                r.get::<_, i64>(4)?,
                r.get::<_, String>(5)?,
                r.get::<_, String>(6)?,
                r.get::<_, String>(7)?,
                r.get::<_, String>(8)?,
                r.get::<_, String>(9)?,
                r.get::<_, i64>(10)?,
                r.get::<_, String>(11)?,
                r.get::<_, i64>(12)?,
            ))
        })
        .map_err(|_| "comment listing failed")?;
    let mut comments = Vec::new();
    for row in rows {
        let (
            id,
            rev,
            sha,
            start,
            end,
            quote,
            reviewer,
            comment,
            actor,
            at,
            project_revision,
            body,
            latest,
        ) = row.map_err(|_| "stored comment unreadable")?;
        let anchored = start >= 0
            && end > start
            && digest(body.as_bytes()) == sha
            && body
                .chars()
                .skip(start as usize)
                .take((end - start) as usize)
                .collect::<String>()
                == quote;
        let status = if !anchored {
            "invalid_source_anchor"
        } else if latest != rev {
            "historical_source_revision"
        } else {
            "current"
        };
        comments.push(json!({
            "id":id,"manuscript_id":manuscript_id,"section":section,
            "source_revision":rev,"source_body_sha256":sha,
            "start_scalar":start,"end_scalar":end,"quote":quote,
            "reviewer":reviewer,"comment":comment,"actor":actor,
            "recorded_at":at,"project_revision":project_revision,
            "anchor_status":status,"auto_relocated":false,
            "word_track_changes_supported":false
        }));
    }
    if comments.len() > 1_000 {
        return Err("comment listing exceeds 1000 records; pagination not implemented".into());
    }
    Ok(json!({"manuscript_id":manuscript_id,"section":section,
        "comments":comments,"count":comments.len(),"read_only":true,
        "historical_anchors_never_silently_relocated":true}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::EvidenceHandler;
    use researchweave_core::OperationHandler;
    use researchweave_project::ProjectInfo;
    use rusqlite::Connection;

    fn ctx(id: Uuid, revision: u64) -> DispatchContext {
        DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: id,
            actor: "synthetic-research-reviewer".into(),
            expected_revision: Some(revision),
        }
    }

    fn project(root: &std::path::Path) -> (Uuid, EvidenceHandler) {
        let id = Uuid::new_v4();
        ProjectStore::create(
            root,
            &ProjectInfo {
                id: id.to_string(),
                title: "Synthetic comments".into(),
                question: "Can this synthetic anchor be verified?".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-11-01T00:00:00Z".into(),
            },
        )
        .unwrap();
        (id, EvidenceHandler::bound(id, root).unwrap())
    }

    #[test]
    fn preview_and_approved_record_accept_different_command_ids_but_reject_actor_or_revision() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("f03-host-new-command-per-approval");
        let (id, handler) = project(&root);
        let saved = handler.execute(
            "writing.section_save",
            &json!({
                "project_id":id,"manuscript_id":"m","section":"Results",
                "body":"A🧠汉B","citations":[]
            }),
            &ctx(id, 0),
        );
        assert_eq!(saved["status"], "ok", "{saved}");
        let args = json!({
            "project_id":id,"manuscript_id":"m","section":"Results",
            "source_revision":1,
            "source_body_sha256":saved["data"]["body_sha256"],
            "start_scalar":1,"end_scalar":3,"quote":"🧠汉",
            "reviewer":"Reviewer A","comment":"Check synthetic methods."
        });
        let preview_context = ctx(id, 1);
        let approved_context = ctx(id, 1);
        assert_ne!(preview_context.request_id, approved_context.request_id);
        let preview = handler.preview("writing.comment_record", &args, &preview_context);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["writes"], 0);
        let digest = preview["data"]["preview_sha256"].as_str().unwrap();
        assert_eq!(digest.len(), 64);
        // A separate trusted command with the same project/actor/revision
        // binds the same reviewed content, regardless of its fresh request ID.
        let independently_previewed =
            handler.preview("writing.comment_record", &args, &approved_context);
        assert_eq!(independently_previewed["data"]["preview_sha256"], digest);
        let mut approved_args = args.clone();
        approved_args["approved_preview_sha256"] = json!(digest);

        let mut changed_actor = ctx(id, 1);
        changed_actor.actor = "unreviewed-actor".into();
        assert_eq!(
            handler.execute("writing.comment_record", &approved_args, &changed_actor)["status"],
            "error"
        );
        assert_eq!(
            handler.execute("writing.comment_record", &approved_args, &ctx(id, 0))["status"],
            "error"
        );
        let current_before = ProjectStore::open(&root).unwrap().info().unwrap().revision;
        assert_eq!(current_before, 1);
        let inserted = handler.execute("writing.comment_record", &approved_args, &approved_context);
        assert_eq!(inserted["status"], "ok", "{inserted}");
        assert_eq!(inserted["data"]["project_revision"], 2);
        assert_eq!(inserted["data"]["manuscript_body_mutated"], false);
        let store = ProjectStore::open(&root).unwrap();
        let record_count: i64 = store
            .connection()
            .query_row("SELECT count(*) FROM manuscript_comments", [], |r| r.get(0))
            .unwrap();
        assert_eq!(record_count, 1);
        let recorded_request_id: String = store
            .connection()
            .query_row(
                "SELECT request_id FROM events WHERE operation='writing.comment_record'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(recorded_request_id, approved_context.request_id.to_string());
        drop(store);
        // Once the revision changes, even a third fresh request ID with the
        // old preview cannot record again; request IDs are still unique events.
        let repeat = handler.execute("writing.comment_record", &approved_args, &ctx(id, 1));
        assert_eq!(repeat["status"], "error");
        assert_eq!(
            ProjectStore::open(&root).unwrap().info().unwrap().revision,
            2
        );
    }

    #[test]
    fn preview_approval_unicode_redaction_cas_and_historical_status() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("P Α");
        let (id, handler) = project(&path);
        let source = "A🧠é汉B";
        let saved = handler.execute(
            "writing.section_save",
            &json!({"project_id":id,"manuscript_id":"m","section":"Résultats",
                "body":source,"citations":[]}),
            &ctx(id, 0),
        );
        assert_eq!(saved["status"], "ok", "{saved}");
        let sha = saved["data"]["body_sha256"].as_str().unwrap();
        let base = json!({
            "project_id":id,"manuscript_id":"m","section":"Résultats",
            "source_revision":1,"source_body_sha256":sha,
            "start_scalar":1,"end_scalar":4,"quote":"🧠é汉",
            "reviewer":"Reviewer Ω","comment":"Clarify the sample, not a scientific claim"
        });
        let before = ProjectStore::open(&path).unwrap().info().unwrap().revision;
        let approval_ctx = ctx(id, before as u64);
        let preview = handler.preview("writing.comment_record", &base, &approval_ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["writes"], 0);
        assert_eq!(preview["data"]["comment_text_redacted"], true);
        assert!(!preview.to_string().contains("Clarify the sample"));
        assert!(!preview.to_string().contains("Reviewer Ω"));
        assert!(!preview.to_string().contains("🧠é汉"));
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            before
        );
        let rejected_without_approval =
            handler.execute("writing.comment_record", &base, &approval_ctx);
        assert_eq!(rejected_without_approval["status"], "error");
        let mut approved = base.clone();
        approved["approved_preview_sha256"] = preview["data"]["preview_sha256"].clone();
        let inserted = handler.execute("writing.comment_record", &approved, &approval_ctx);
        assert_eq!(inserted["status"], "ok", "{inserted}");
        assert_eq!(inserted["data"]["manuscript_body_mutated"], false);
        assert_eq!(inserted["data"]["project_revision"], before + 1);
        assert_eq!(
            handler.execute("writing.comment_record", &approved, &approval_ctx)["status"],
            "error"
        );
        let listing = handler.execute(
            "writing.comment_list",
            &json!({"project_id":id,"manuscript_id":"m","section":"Résultats"}),
            &ctx(id, (before + 1) as u64),
        );
        assert_eq!(listing["status"], "ok", "{listing}");
        assert_eq!(listing["data"]["count"], 1);
        assert_eq!(listing["data"]["comments"][0]["anchor_status"], "current");
        assert_eq!(listing["data"]["comments"][0]["quote"], "🧠é汉");
        assert_eq!(listing["data"]["comments"][0]["comment"], base["comment"]);
        let store = ProjectStore::open(&path).unwrap();
        let persisted_body: String = store
            .connection()
            .query_row(
                "SELECT body FROM manuscripts WHERE id='m' AND section='Résultats' AND revision=1",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(persisted_body, source);
        assert!(store
            .connection()
            .execute("UPDATE manuscript_comments SET comment='changed'", [])
            .is_err());
        assert!(store
            .connection()
            .execute("DELETE FROM manuscript_comments", [])
            .is_err());
        drop(store);
        let next = handler.execute(
            "writing.section_save",
            &json!({"project_id":id,"manuscript_id":"m","section":"Résultats",
                "body":"Revised final section","citations":[]}),
            &ctx(id, (before + 1) as u64),
        );
        assert_eq!(next["status"], "ok", "{next}");
        let historical = handler.execute(
            "writing.comment_list",
            &json!({"project_id":id,"manuscript_id":"m","section":"Résultats"}),
            &ctx(id, (before + 2) as u64),
        );
        assert_eq!(
            historical["data"]["comments"][0]["anchor_status"],
            "historical_source_revision"
        );
        assert_eq!(historical["data"]["comments"][0]["auto_relocated"], false);
    }

    #[test]
    fn malformed_stale_cross_project_overlap_and_no_preview_writes() {
        let dir = tempfile::tempdir().unwrap();
        let path_a = dir.path().join("A");
        let path_b = dir.path().join("B");
        let (a, ha) = project(&path_a);
        let (b, _hb) = project(&path_b);
        let saved = ha.execute(
            "writing.section_save",
            &json!({"project_id":a,"manuscript_id":"m","section":"Results",
                "body":"A🧠é汉B","citations":[]}),
            &ctx(a, 0),
        );
        assert_eq!(saved["status"], "ok");
        let mut base = json!({
            "project_id":a,"manuscript_id":"m","section":"Results",
            "source_revision":1,"source_body_sha256":saved["data"]["body_sha256"],
            "start_scalar":1,"end_scalar":4,"quote":"🧠é汉",
            "reviewer":"R","comment":"Synthetic reviewer concern"
        });
        let stable = ctx(a, 1);
        for (field, value) in [
            ("start_scalar", json!(2)),
            ("end_scalar", json!(2)),
            ("end_scalar", json!(1_000_001)),
            ("quote", json!("🧠é错")),
            ("source_body_sha256", json!("0".repeat(64))),
            ("source_revision", json!(2)),
            ("reviewer", json!(" ")),
            ("comment", json!("x".repeat(4001))),
        ] {
            let mut invalid = base.clone();
            invalid[field] = value;
            assert_eq!(
                ha.preview("writing.comment_record", &invalid, &stable)["status"],
                "error",
                "{field}"
            );
        }
        assert_eq!(
            ha.preview("writing.comment_record", &base, &ctx(a, 0))["status"],
            "error"
        );
        assert_eq!(
            ha.preview("writing.comment_record", &base, &ctx(b, 1))["status"],
            "error"
        );
        base["project_id"] = json!(b);
        assert_eq!(
            ha.preview("writing.comment_record", &base, &stable)["status"],
            "error"
        );
        base["project_id"] = json!(a);
        assert_eq!(
            ProjectStore::open(&path_a)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            1
        );
        let preview = ha.preview("writing.comment_record", &base, &stable);
        assert_eq!(preview["status"], "ok", "{preview}");
        let mut approved = base.clone();
        approved["approved_preview_sha256"] = preview["data"]["preview_sha256"].clone();
        approved["comment"] = json!("mutated after review");
        assert_eq!(
            ha.execute("writing.comment_record", &approved, &stable)["status"],
            "error"
        );
        approved["comment"] = base["comment"].clone();
        assert_eq!(
            ha.execute("writing.comment_record", &approved, &stable)["status"],
            "ok"
        );
        let overlap_ctx = ctx(a, 2);
        let mut overlap = base.clone();
        overlap["start_scalar"] = json!(2);
        overlap["end_scalar"] = json!(3);
        overlap["quote"] = json!("é");
        assert_eq!(
            ha.preview("writing.comment_record", &overlap, &overlap_ctx)["status"],
            "error"
        );
        assert_eq!(
            ProjectStore::open(&path_a)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            2
        );
        assert_eq!(
            ProjectStore::open(&path_b)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            0
        );
        let event_payload: String = Connection::open(path_a.join("data/project.sqlite"))
            .unwrap()
            .query_row(
                "SELECT payload_json FROM events WHERE operation='writing.comment_record'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert!(!event_payload.contains("Synthetic reviewer concern"));
    }
}
