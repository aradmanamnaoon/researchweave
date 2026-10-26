//! Bounded, read-only evidence capabilities backed by the native project store.
//! Only implemented operations are advertised; mutation operations require
//! a faithful event/revision integration before they can be registered.
use researchweave_core::{Capability, DispatchContext, Effect, OperationHandler};
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension, Transaction};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    path::{Component, Path, PathBuf},
};
use uuid::Uuid;
mod forms;
mod highlights;
mod publishing;
mod publishing_formats;
mod qualitative;
mod review;

enum EvidenceLocation {
    WorkspaceRoot(PathBuf),
    Bound { project_id: Uuid, path: PathBuf },
}

pub struct EvidenceHandler {
    location: EvidenceLocation,
}

impl EvidenceHandler {
    pub fn new(trusted_workspace: PathBuf) -> Self {
        Self {
            location: EvidenceLocation::WorkspaceRoot(trusted_workspace),
        }
    }

    /// Bind evidence operations to one exact project path selected by the trusted host.
    ///
    /// The project path never crosses the command boundary; dispatched operations
    /// remain scoped exclusively by the project UUID.
    pub fn bound(project_id: Uuid, path: impl AsRef<Path>) -> Result<Self, String> {
        let path = path.as_ref();
        if !path.is_absolute()
            || path.file_name().is_none()
            || path
                .components()
                .any(|component| matches!(component, Component::ParentDir))
        {
            return Err("bound evidence path must be an absolute normalized directory".into());
        }
        let metadata = fs::symlink_metadata(path).map_err(|_| "bound evidence path unavailable")?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err("bound evidence path must be a real project directory".into());
        }
        let path = path
            .canonicalize()
            .map_err(|_| "bound evidence path unavailable")?;
        Ok(Self {
            location: EvidenceLocation::Bound { project_id, path },
        })
    }

    pub fn capabilities() -> Vec<Capability> {
        let mut capabilities: Vec<Capability> = [
            (
                "question.feedback",
                &["question", "framework", "fields"][..],
            ),
            ("protocol.history", &["project_id", "protocol_id"][..]),
            (
                "protocol.diff",
                &["project_id", "protocol_id", "from_version", "to_version"][..],
            ),
            ("protocol.export", &["project_id", "protocol_id"][..]),
            ("question.history", &["project_id", "question_id"][..]),
            ("evidence.note_history", &["project_id", "note_id"][..]),
            ("evidence.notebook_export", &["project_id"][..]),
            (
                "evidence.highlight_history",
                &["project_id", "highlight_id"][..],
            ),
            ("evidence.notebook_history", &["project_id"][..]),
            (
                "writing.section_history",
                &["project_id", "manuscript_id", "section"][..],
            ),
            ("writing.inspect", &["project_id", "manuscript_id"][..]),
            ("writing.bibliography", &["project_id", "manuscript_id"][..]),
            ("writing.check", &["project_id", "manuscript_id"][..]),
            (
                "writing.submission_packet",
                &["project_id", "manuscript_id", "journal"][..],
            ),
            (
                "writing.submission_export",
                &["project_id", "manuscript_id", "journal"][..],
            ),
            (
                "writing.manuscript_export",
                &["project_id", "manuscript_id"][..],
            ),
            ("writing.claim_check", &["project_id", "claim_id"][..]),
            ("review.records", &["project_id", "review_id"][..]),
            (
                "review.adjudications",
                &["project_id", "review_id", "record_id"][..],
            ),
            (
                "review.extractions",
                &["project_id", "review_id", "record_id"][..],
            ),
            (
                "review.votes",
                &["project_id", "review_id", "record_id"][..],
            ),
            (
                "review.status",
                &["project_id", "review_id", "record_id", "stage"][..],
            ),
            ("review.prisma", &["project_id", "review_id"][..]),
            ("review.form_history", &["project_id", "form_id"][..]),
            ("review.form_values", &["project_id", "form_id"][..]),
            ("qualitative.inspect", &["project_id"][..]),
            ("qualitative.mixed_provenance", &["project_id"][..]),
            ("qualitative.transcripts", &["project_id"][..]),
            ("qualitative.kappa", &["first", "second"][..]),
        ]
        .into_iter()
        .map(|(name, required)| {
            Capability::new(
                name,
                Effect::Read,
                json!({
                    "effect":"read", "required_arguments":required,
                    "approval_required":false,
                    "project_scoped":!matches!(name,"question.feedback" | "qualitative.kappa")
                }),
            )
        })
        .collect();
        for (name, required) in [
            (
                "protocol.create",
                &["project_id", "title", "author", "body"][..],
            ),
            (
                "protocol.amend",
                &["project_id", "protocol_id", "author", "rationale", "body"],
            ),
            (
                "question.create",
                &["project_id", "question", "framework", "fields", "author"],
            ),
            (
                "question.amend",
                &[
                    "project_id",
                    "question_id",
                    "question",
                    "framework",
                    "fields",
                    "author",
                    "rationale",
                ],
            ),
            (
                "evidence.note",
                &["project_id", "source_id", "title", "body"],
            ),
            (
                "evidence.note_revise",
                &[
                    "project_id",
                    "note_id",
                    "title",
                    "body",
                    "actor",
                    "rationale",
                ],
            ),
            (
                "evidence.note_delete",
                &["project_id", "note_id", "actor", "reason"],
            ),
            (
                "evidence.anchor",
                &["project_id", "source_id", "quote", "start", "end"],
            ),
            (
                "evidence.highlight_create",
                &[
                    "project_id",
                    "source_id",
                    "page_number",
                    "start",
                    "end",
                    "quote",
                ],
            ),
            (
                "evidence.highlight_relocate",
                &["project_id", "highlight_id", "target_source_id"],
            ),
            (
                "review.record_add",
                &["project_id", "review_id", "reference_id"],
            ),
            (
                "review.vote",
                &[
                    "project_id",
                    "review_id",
                    "record_id",
                    "reviewer",
                    "stage",
                    "decision",
                    "reason",
                ],
            ),
            (
                "review.screen",
                &[
                    "project_id",
                    "review_id",
                    "record_id",
                    "reviewer",
                    "stage",
                    "decision",
                    "reason",
                ],
            ),
            (
                "review.adjudicate",
                &[
                    "project_id",
                    "review_id",
                    "record_id",
                    "stage",
                    "decision",
                    "reason",
                    "adjudicator",
                ],
            ),
            ("review.advance", &["project_id", "review_id", "record_id"]),
            (
                "review.extract",
                &[
                    "project_id",
                    "review_id",
                    "record_id",
                    "field_name",
                    "value",
                    "reviewer",
                ],
            ),
            (
                "writing.section_save",
                &[
                    "project_id",
                    "manuscript_id",
                    "section",
                    "body",
                    "citations",
                ][..],
            ),
            (
                "writing.section_restore",
                &["project_id", "manuscript_id", "section", "source_revision"][..],
            ),
            (
                "writing.claim_add",
                &["project_id", "statement", "interpretation"][..],
            ),
            ("ui.notebook.save", &["project_id", "notebook"][..]),
            (
                "qualitative.add_code",
                &[
                    "project_id",
                    "expected_content_hash",
                    "code_id",
                    "name",
                    "actor",
                ][..],
            ),
            (
                "qualitative.update_code",
                &["project_id", "expected_content_hash", "code_id", "actor"][..],
            ),
            (
                "qualitative.delete_code",
                &["project_id", "expected_content_hash", "code_id", "actor"][..],
            ),
            (
                "qualitative.annotate",
                &[
                    "project_id",
                    "expected_content_hash",
                    "source_id",
                    "start",
                    "end",
                    "code_id",
                    "coder",
                    "unit_id",
                ][..],
            ),
            (
                "qualitative.transcript_register",
                &[
                    "project_id",
                    "expected_content_hash",
                    "source_id",
                    "case_id",
                    "confidential",
                    "expected_body_hash",
                ][..],
            ),
            (
                "qualitative.transcript_update",
                &[
                    "project_id",
                    "expected_content_hash",
                    "source_id",
                    "case_id",
                    "confidential",
                    "expected_body_hash",
                ][..],
            ),
            (
                "review.form_create",
                &["project_id", "name", "fields", "author"][..],
            ),
            (
                "review.form_revise",
                &[
                    "project_id",
                    "form_id",
                    "fields",
                    "author",
                    "rationale",
                    "migration",
                ][..],
            ),
            (
                "review.form_record",
                &["project_id", "form_id", "record_id", "values", "reviewer"][..],
            ),
        ] {
            capabilities.push(Capability::new(
                name,
                Effect::LocalWrite,
                json!({
                    "effect":"local-write", "required_arguments":required,
                    "approval_required":true,"project_scoped":true,"revision_guarded":true
                }),
            ));
        }
        capabilities
    }

    fn store(&self, args: &Value, context: &DispatchContext) -> Result<ProjectStore, String> {
        let id = args
            .get("project_id")
            .and_then(Value::as_str)
            .ok_or("project_id required")?;
        let parsed = Uuid::parse_str(id).map_err(|_| "invalid project id")?;
        if parsed != context.project_id {
            return Err("project scope mismatch".into());
        }
        let path = match &self.location {
            EvidenceLocation::WorkspaceRoot(workspace) => {
                let canonical_base = workspace
                    .canonicalize()
                    .map_err(|_| "workspace unavailable")?;
                let canonical_path = workspace
                    .join(parsed.to_string())
                    .canonicalize()
                    .map_err(|_| "project not found")?;
                if !canonical_path.starts_with(&canonical_base)
                    || canonical_path.parent() != Some(canonical_base.as_path())
                {
                    return Err("unsafe project path".into());
                }
                canonical_path
            }
            EvidenceLocation::Bound { project_id, path } => {
                if *project_id != parsed {
                    return Err("project scope mismatch".into());
                }
                path.clone()
            }
        };
        let project = ProjectStore::open(path).map_err(|_| "project unavailable")?;
        if project.info().map_err(|_| "invalid project")?.id != parsed.to_string() {
            return Err("project identity mismatch".into());
        }
        Ok(project)
    }

    fn history(store: &ProjectStore, args: &Value) -> Result<Vec<Value>, String> {
        let id = required_text(args, "protocol_id")?;
        let mut statement = store.connection().prepare(
            "SELECT version,title,body_json,rationale,author,recorded_at FROM protocols WHERE id=? ORDER BY version"
        ).map_err(|_| "protocol query failed")?;
        let records = statement
            .query_map(params![id], |row| {
                let body: String = row.get(2)?;
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    body,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                ))
            })
            .map_err(|_| "protocol query failed")?;
        let mut output = Vec::new();
        for record in records {
            let (version, title, body, rationale, author, recorded_at) =
                record.map_err(|_| "corrupt protocol")?;
            let body: Value = serde_json::from_str(&body).map_err(|_| "corrupt protocol body")?;
            output.push(json!({"version":version,"title":title,"body":body,
                "rationale":rationale,"author":author,"recorded_at":recorded_at}));
        }
        if output.is_empty() {
            return Err("protocol not found".into());
        }
        Ok(output)
    }

    fn run(&self, operation: &str, args: &Value, ctx: &DispatchContext) -> Result<Value, String> {
        if operation == "question.feedback" {
            return question_feedback(args);
        }
        if operation == "qualitative.kappa" {
            return qualitative::kappa(args);
        }
        let mut store = self.store(args, ctx)?;
        if operation == "project.open" {
            return serde_json::to_value(store.info().map_err(|_| "invalid project")?)
                .map_err(|_| "serialization failure".into());
        }
        if matches!(operation, "protocol.create" | "protocol.amend") {
            return protocol_mutate(&mut store, operation, args, ctx);
        }
        if matches!(operation, "question.create" | "question.amend") {
            return question_mutate(&mut store, operation, args, ctx);
        }
        if operation == "question.history" {
            return question_history(&store, args);
        }
        if matches!(
            operation,
            "evidence.note" | "evidence.note_revise" | "evidence.note_delete"
        ) {
            return note_mutate(&mut store, operation, args, ctx);
        }
        if operation == "evidence.note_history" {
            return note_history(&store, args);
        }
        if operation == "evidence.notebook_export" {
            return notebook_export(&store);
        }
        if operation == "evidence.notebook_history" {
            return notebook_history(&store);
        }
        if operation == "ui.notebook.save" {
            return notebook_save(&mut store, args, ctx);
        }
        if operation == "evidence.anchor" {
            return anchor_mutate(&mut store, args, ctx);
        }
        if matches!(
            operation,
            "evidence.highlight_create" | "evidence.highlight_relocate"
        ) {
            return highlights::write(&mut store, operation, args, ctx);
        }
        if operation == "evidence.highlight_history" {
            return highlights::history(&store, args);
        }
        if matches!(
            operation,
            "qualitative.add_code"
                | "qualitative.update_code"
                | "qualitative.delete_code"
                | "qualitative.annotate"
                | "qualitative.transcript_register"
                | "qualitative.transcript_update"
        ) {
            return qualitative::write(&mut store, operation, args, ctx);
        }
        if operation == "qualitative.inspect" {
            return qualitative::inspect(&store);
        }
        if operation == "qualitative.transcripts" {
            return qualitative::transcripts(&store);
        }
        if matches!(
            operation,
            "writing.bibliography"
                | "writing.check"
                | "writing.submission_packet"
                | "writing.submission_export"
        ) {
            return publishing::read(&store, operation, args);
        }
        if operation == "qualitative.mixed_provenance" {
            return qualitative::mixed_provenance(&store, args);
        }
        if matches!(operation, "review.form_history" | "review.form_values") {
            return forms::read(&store, operation, args);
        }
        if matches!(
            operation,
            "review.form_create" | "review.form_revise" | "review.form_record"
        ) {
            return forms::write(&mut store, operation, args, ctx);
        }
        if matches!(
            operation,
            "writing.section_save" | "writing.section_restore" | "writing.claim_add"
        ) {
            return writing_mutate(&mut store, operation, args, ctx);
        }
        if matches!(
            operation,
            "writing.section_history"
                | "writing.inspect"
                | "writing.manuscript_export"
                | "writing.claim_check"
        ) {
            return writing_read(&store, operation, args);
        }
        if matches!(
            operation,
            "review.record_add"
                | "review.vote"
                | "review.screen"
                | "review.adjudicate"
                | "review.advance"
                | "review.extract"
                | "review.form_create"
                | "review.form_revise"
                | "review.form_record"
        ) {
            return review::write(&mut store, operation, args, ctx);
        }
        if matches!(
            operation,
            "review.records"
                | "review.votes"
                | "review.status"
                | "review.prisma"
                | "review.adjudications"
                | "review.extractions"
        ) {
            return review::read(&store, operation, args);
        }
        let history = Self::history(&store, args)?;
        match operation {
            "protocol.history" => Ok(json!({"history":history})),
            "protocol.diff" => {
                let from = args
                    .get("from_version")
                    .and_then(Value::as_i64)
                    .ok_or("from_version required")?;
                let to = args
                    .get("to_version")
                    .and_then(Value::as_i64)
                    .ok_or("to_version required")?;
                if from <= 0 || from >= to {
                    return Err("invalid version range".into());
                }
                let before = history
                    .iter()
                    .find(|row| row["version"] == from)
                    .ok_or("version not found")?;
                let after = history
                    .iter()
                    .find(|row| row["version"] == to)
                    .ok_or("version not found")?;
                let a = before["body"].as_object().ok_or("invalid body")?;
                let b = after["body"].as_object().ok_or("invalid body")?;
                let keys: BTreeSet<_> = a.keys().chain(b.keys()).collect();
                let changes: Vec<Value> = keys.into_iter().filter(|key| a.get(*key) != b.get(*key)).map(|key| json!({
                    "field":key,"kind":if !a.contains_key(key) {"added"} else if !b.contains_key(key) {"removed"} else {"changed"},
                    "before":a.get(key),"after":b.get(key)
                })).collect();
                let fields: Vec<Value> = changes.iter().map(|item| item["field"].clone()).collect();
                Ok(
                    json!({"protocol_id":args["protocol_id"],"from_version":from,"to_version":to,
                    "changes":changes,"changed_fields":fields,"amendment_rationale":after["rationale"],
                    "amendment_author":after["author"],"amendment_recorded_at":after["recorded_at"],"history_overwritten":false}),
                )
            }
            "protocol.export" => {
                let mut lines = vec![
                    format!("# {}", history[0]["title"].as_str().unwrap_or("")),
                    String::new(),
                    "## Version history".into(),
                    String::new(),
                ];
                for row in history {
                    lines.extend([
                        format!("### Version {}", row["version"]),
                        String::new(),
                        format!("- Author: {}", row["author"].as_str().unwrap_or("")),
                        format!(
                            "- Recorded at: {}",
                            row["recorded_at"].as_str().unwrap_or("")
                        ),
                        format!("- Rationale: {}", row["rationale"].as_str().unwrap_or("")),
                        String::new(),
                    ]);
                    let serialized = serde_json::to_string_pretty(&row["body"])
                        .map_err(|_| "serialization error")?;
                    lines.extend(serialized.lines().map(|line| format!("    {line}")));
                    lines.push(String::new());
                }
                Ok(json!({"text":lines.join("\n")}))
            }
            _ => Err("operation not implemented".into()),
        }
    }

    fn preview_write(
        &self,
        operation: &str,
        args: &Value,
        ctx: &DispatchContext,
    ) -> Result<Value, String> {
        let source = self.store(args, ctx)?;
        let before = source.info().map_err(|_| "invalid project")?.revision;
        let shadow_root = tempfile::tempdir().map_err(|_| "preview workspace unavailable")?;
        fs::create_dir(shadow_root.path().join("data"))
            .map_err(|_| "preview workspace unavailable")?;
        fs::create_dir(shadow_root.path().join("objects"))
            .map_err(|_| "preview workspace unavailable")?;
        source
            .backup_database(&shadow_root.path().join("data/project.sqlite"))
            .map_err(|_| "preview snapshot failed")?;
        let mut shadow =
            ProjectStore::open(shadow_root.path()).map_err(|_| "preview snapshot invalid")?;
        let simulated = match operation {
            "protocol.create" | "protocol.amend" => {
                protocol_mutate(&mut shadow, operation, args, ctx)?
            }
            "question.create" | "question.amend" => {
                question_mutate(&mut shadow, operation, args, ctx)?
            }
            "evidence.note" | "evidence.note_revise" | "evidence.note_delete" => {
                note_mutate(&mut shadow, operation, args, ctx)?
            }
            "ui.notebook.save" => notebook_save(&mut shadow, args, ctx)?,
            "evidence.anchor" => anchor_mutate(&mut shadow, args, ctx)?,
            "evidence.highlight_create" | "evidence.highlight_relocate" => {
                highlights::write(&mut shadow, operation, args, ctx)?
            }
            "qualitative.add_code"
            | "qualitative.update_code"
            | "qualitative.delete_code"
            | "qualitative.annotate" => qualitative::write(&mut shadow, operation, args, ctx)?,
            "qualitative.transcript_register" | "qualitative.transcript_update" => {
                qualitative::write(&mut shadow, operation, args, ctx)?
            }
            "review.form_create" | "review.form_revise" | "review.form_record" => {
                forms::write(&mut shadow, operation, args, ctx)?
            }
            "writing.section_save" | "writing.section_restore" | "writing.claim_add" => {
                writing_mutate(&mut shadow, operation, args, ctx)?
            }
            "review.record_add" | "review.vote" | "review.screen" | "review.adjudicate"
            | "review.advance" | "review.extract" => {
                review::write(&mut shadow, operation, args, ctx)?
            }
            _ => return Err("operation does not support write preview".into()),
        };
        let after = shadow
            .info()
            .map_err(|_| "preview snapshot invalid")?
            .revision;
        Ok(json!({
            "preview":true,
            "authoritative_revision":before,
            "simulated_revision":after,
            "writes":after.saturating_sub(before),
            "simulated_result":simulated
        }))
    }
}

fn required_text<'a>(args: &'a Value, field: &str) -> Result<&'a str, String> {
    args.get(field)
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("{field} required"))
}

fn digest(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}
fn timestamp() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, true)
}

/// Atomic project revision, Python-compatible canonical payload hash and event
/// hash chain. The request id may never be replayed, including after reopen.
fn mutate<T>(
    store: &mut ProjectStore,
    operation: &str,
    context: &DispatchContext,
    payload: &Value,
    callback: impl FnOnce(&Transaction<'_>, &str) -> Result<T, String>,
) -> Result<(T, i64), String> {
    let tx = store.transaction().map_err(|_| "transaction failed")?;
    let request_id = context.request_id.to_string();
    let replay: i64 = tx
        .query_row(
            "SELECT count(*) FROM events WHERE request_id=?1",
            [&request_id],
            |r| r.get(0),
        )
        .map_err(|_| "request check failed")?;
    if replay != 0 {
        return Err("request already applied".into());
    }
    let revision: i64 = tx
        .query_row("SELECT revision FROM project", [], |r| r.get(0))
        .map_err(|_| "project unavailable")?;
    if context
        .expected_revision
        .is_some_and(|expected| expected != revision as u64)
    {
        return Err("stale project revision".into());
    }
    let now = timestamp();
    let result = callback(&tx, &now)?;
    let payload_json = serde_json::to_string(payload).map_err(|_| "serialization failed")?;
    let payload_hash = digest(payload_json.as_bytes());
    let predecessor: String = tx
        .query_row(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1",
            [],
            |r| r.get(0),
        )
        .unwrap_or_else(|_| "0".repeat(64));
    let next = revision.checked_add(1).ok_or("revision overflow")?;
    let event_hash = digest(
        serde_json::to_string(&json!([
            next,
            request_id,
            operation,
            context.actor,
            payload_hash,
            predecessor,
            now
        ]))
        .map_err(|_| "event serialization failed")?
        .as_bytes(),
    );
    tx.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
        params![
            next,
            request_id,
            operation,
            context.actor,
            payload_json,
            payload_hash,
            predecessor,
            event_hash,
            now
        ],
    )
    .map_err(|_| "event insertion failed")?;
    tx.execute(
        "UPDATE project SET revision=?1 WHERE revision=?2",
        params![next, revision],
    )
    .map_err(|_| "revision update failed")?;
    tx.commit().map_err(|_| "commit failed")?;
    Ok((result, next))
}

fn protocol_mutate(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let author = required_text(args, "author")?.trim();
    if author.is_empty() || author.len() > 255 {
        return Err("invalid protocol author".into());
    }
    let body = args
        .get("body")
        .and_then(Value::as_object)
        .ok_or("protocol body required")?;
    let encoded = serde_json::to_string(body).map_err(|_| "invalid body")?;
    if encoded.len() > 250_000 {
        return Err("protocol too large".into());
    }
    if operation == "protocol.create" {
        let title = required_text(args, "title")?.trim();
        if title.is_empty() || title.len() > 300 {
            return Err("invalid protocol title".into());
        }
        let design = body.get("design").and_then(Value::as_str).unwrap_or("");
        if ![
            "exploratory",
            "observational",
            "experimental",
            "qualitative",
            "mixed",
            "computational",
            "systematic_review",
            "replication",
            "nonacademic",
        ]
        .contains(&design)
            || body
                .get("objective")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .is_empty()
        {
            return Err("invalid protocol design or objective".into());
        }
        let id = uuid::Uuid::new_v4().to_string();
        let payload = json!({"protocol_id":id,"version":1});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            tx.execute(
                "INSERT INTO protocols VALUES (?,?,?,?,?,?,?)",
                params![id, 1, title, encoded, "Original registration", author, now],
            )
            .map_err(|_| "protocol insert failed")?;
            Ok(())
        })?;
        Ok(json!({"protocol_id":id,"protocol_version":1,"project_revision":revision}))
    } else {
        let id = required_text(args, "protocol_id")?;
        let rationale = required_text(args, "rationale")?.trim();
        if rationale.is_empty() || rationale.len() > 5000 {
            return Err("invalid amendment rationale".into());
        }
        let payload =
            json!({"protocol_id":id,"author":author,"rationale":rationale,"new_body":body});
        let (version, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            let (version,title,prior):(i64,String,String) = tx.query_row("SELECT version,title,body_json FROM protocols WHERE id=? ORDER BY version DESC LIMIT 1",
                [id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?))).map_err(|_| "protocol not found")?;
            if prior == encoded {
                return Err("no changes to amend".into());
            }
            let next = version.checked_add(1).ok_or("version overflow")?;
            tx.execute(
                "INSERT INTO protocols VALUES (?,?,?,?,?,?,?)",
                params![id, next, title, encoded, rationale, author, now],
            )
            .map_err(|_| "protocol amend failed")?;
            Ok(next)
        })?;
        Ok(json!({"protocol_id":id,"protocol_version":version,"project_revision":revision}))
    }
}

fn anchor_mutate(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let source = required_text(args, "source_id")?;
    let quote = required_text(args, "quote")?;
    let start = args
        .get("start")
        .and_then(Value::as_u64)
        .ok_or("invalid start")? as usize;
    let end = args
        .get("end")
        .and_then(Value::as_u64)
        .ok_or("invalid end")? as usize;
    let page = match args.get("page") {
        Some(Value::Null) | None => None,
        Some(value) => Some(value.as_i64().filter(|p| *p > 0).ok_or("invalid page")?),
    };
    if quote.chars().count() > 20_000 || start > end {
        return Err("invalid quote offsets".into());
    }
    let (body, body_hash): (String, String) = store
        .connection()
        .query_row(
            "SELECT body,body_hash FROM document_text WHERE source_id=?",
            [source],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .map_err(|_| "source text not found")?;
    if digest(body.as_bytes()) != body_hash {
        return Err("source text checksum mismatch".into());
    }
    let length = body.chars().count();
    if end > length {
        return Err("invalid quote offsets".into());
    }
    let exact = body
        .chars()
        .skip(start)
        .take(end - start)
        .collect::<String>()
        == quote;
    let id = uuid::Uuid::new_v4().to_string();
    let payload = json!({"source_id":source,"anchor_id":id,"quote_verified":exact});
    let (_, revision) = mutate(store, "evidence.anchor", ctx, &payload, |tx, _| {
        tx.execute(
            "INSERT INTO anchors VALUES (?,?,?,?,?,?,?,?)",
            params![
                id,
                source,
                quote,
                start as i64,
                end as i64,
                page,
                body_hash,
                i64::from(exact)
            ],
        )
        .map_err(|_| "anchor insertion failed")?;
        Ok(())
    })?;
    Ok(
        json!({"anchor_id":id,"quote_verified":exact,"classification":if exact {"exact"}else{"unverifiable"},"revision":revision}),
    )
}

fn notebook_export(store: &ProjectStore) -> Result<Value, String> {
    let latest_notebook: Option<(i64, String, String)> = store
        .connection()
        .query_row(
            "SELECT revision,body,edited_at FROM notebook_entries
             WHERE id='project' ORDER BY revision DESC LIMIT 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()
        .map_err(|_| "notebook revision query failed")?;
    let has_tombstones: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='note_tombstones'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| "notebook schema unavailable")?;
    let sql = if has_tombstones == 0 {
        "SELECT n.title,n.body,s.title,n.source_id FROM notes n JOIN sources s ON s.id=n.source_id ORDER BY n.created_at,n.id"
    } else {
        "SELECT n.title,n.body,s.title,n.source_id FROM notes n JOIN sources s ON s.id=n.source_id LEFT JOIN note_tombstones t ON t.note_id=n.id WHERE t.note_id IS NULL ORDER BY n.created_at,n.id"
    };
    let mut stmt = store
        .connection()
        .prepare(sql)
        .map_err(|_| "notebook query failed")?;
    let rows = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, String>(3)?,
            ))
        })
        .map_err(|_| "notebook query failed")?;
    let mut lines = vec!["# Research notebook".to_owned(), String::new()];
    if let Some((revision, body, edited_at)) = latest_notebook {
        lines.extend([
            format!("*Saved revision {revision}; edited {edited_at}.*"),
            String::new(),
            body,
            String::new(),
            "---".to_owned(),
            String::new(),
            "## Evidence notes".to_owned(),
            String::new(),
        ]);
    } else {
        lines.extend([
            "*No project notebook text has been saved yet.*".to_owned(),
            String::new(),
            "## Evidence notes".to_owned(),
            String::new(),
        ]);
    }
    lines.extend([
        "*Human notes are interpretations; source quotations must be independently verified.*"
            .to_owned(),
        String::new(),
    ]);
    for row in rows {
        let (title, body, source, id) = row.map_err(|_| "notebook data invalid")?;
        lines.extend([
            format!("## {}", title.replace('\n', " ").replace('#', "")),
            format!("Source: {source} ({id})"),
            String::new(),
            body,
            String::new(),
        ]);
    }
    Ok(json!({"text":lines.join("\n")}))
}

fn notebook_save(
    store: &mut ProjectStore,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let body = args
        .get("notebook")
        .and_then(Value::as_str)
        .ok_or("notebook text required")?;
    if body.chars().count() > 500_000 || body.contains('\0') {
        return Err("notebook text exceeds bounds".into());
    }
    let payload = json!({
        "notebook_id":"project",
        "body_sha256":digest(body.as_bytes()),
        "characters":body.chars().count()
    });
    let (notebook_revision, project_revision) = mutate(
        store,
        "ui.notebook.save",
        ctx,
        &payload,
        |tx, now| {
            let latest: i64 = tx
                .query_row(
                    "SELECT COALESCE(MAX(revision),0) FROM notebook_entries WHERE id='project'",
                    [],
                    |row| row.get(0),
                )
                .map_err(|_| "notebook revision unavailable")?;
            if let Some(previous) = tx
                .query_row(
                    "SELECT body FROM notebook_entries WHERE id='project' ORDER BY revision DESC LIMIT 1",
                    [],
                    |row| row.get::<_, String>(0),
                )
                .optional()
                .map_err(|_| "notebook revision unavailable")?
            {
                if previous == body {
                    return Err("notebook has no changes".into());
                }
            }
            let next = latest.checked_add(1).ok_or("notebook revision overflow")?;
            tx.execute(
                "INSERT INTO notebook_entries(id,revision,body,edited_at) VALUES ('project',?1,?2,?3)",
                params![next, body, now],
            )
            .map_err(|_| "notebook save failed")?;
            Ok(next)
        },
    )?;
    Ok(json!({
        "notebook_revision":notebook_revision,
        "project_revision":project_revision,
        "body_sha256":digest(body.as_bytes()),
        "characters":body.chars().count(),
        "autosave_safe":true
    }))
}

fn notebook_history(store: &ProjectStore) -> Result<Value, String> {
    let mut statement = store
        .connection()
        .prepare(
            "SELECT revision,body,edited_at FROM notebook_entries
             WHERE id='project' ORDER BY revision",
        )
        .map_err(|_| "notebook history unavailable")?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| "notebook history unavailable")?;
    let mut revisions = Vec::new();
    for row in rows {
        let (revision, body, edited_at) = row.map_err(|_| "notebook history corrupted")?;
        revisions.push(json!({
            "revision":revision,
            "body":body,
            "edited_at":edited_at,
            "body_sha256":digest(body.as_bytes())
        }));
    }
    Ok(json!({"notebook_id":"project","revisions":revisions,"count":revisions.len()}))
}

fn note_tables(tx: &Transaction<'_>) -> Result<(), String> {
    tx.execute_batch(
        "CREATE TABLE IF NOT EXISTS note_revisions (
        note_id TEXT NOT NULL REFERENCES notes(id),revision INTEGER NOT NULL CHECK(revision>0),
        title TEXT NOT NULL,body TEXT NOT NULL,rationale TEXT NOT NULL,
        actor TEXT NOT NULL,recorded_at TEXT NOT NULL,PRIMARY KEY(note_id,revision));
        CREATE TABLE IF NOT EXISTS note_tombstones (
        note_id TEXT PRIMARY KEY REFERENCES notes(id),reason TEXT NOT NULL,
        actor TEXT NOT NULL,deleted_at TEXT NOT NULL)",
    )
    .map_err(|_| "note history schema failed".into())
}

fn adopt_note(tx: &Transaction<'_>, id: &str) -> Result<(String, String, String), String> {
    note_tables(tx)?;
    let (title, body, created): (String, String, String) = tx
        .query_row(
            "SELECT title,body,created_at FROM notes WHERE id=?",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
        )
        .map_err(|_| "note not found")?;
    let count: i64 = tx
        .query_row(
            "SELECT count(*) FROM note_revisions WHERE note_id=?",
            [id],
            |r| r.get(0),
        )
        .map_err(|_| "note history unavailable")?;
    if count == 0 {
        tx.execute(
            "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
            params![
                id,
                1,
                title,
                body,
                "Legacy note adopted into revision history",
                "migration",
                created
            ],
        )
        .map_err(|_| "note adoption failed")?;
    }
    Ok((title, body, created))
}

fn note_mutate(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    if operation == "evidence.note" {
        let source = required_text(args, "source_id")?;
        let title = required_text(args, "title")?.trim();
        let body = required_text(args, "body")?.trim();
        if title.is_empty()
            || title.chars().count() > 300
            || body.is_empty()
            || body.chars().count() > 250_000
        {
            return Err("invalid note".into());
        }
        let id = uuid::Uuid::new_v4().to_string();
        let payload =
            json!({"note_id":id,"source_id":source,"body_sha256":digest(body.as_bytes())});
        let (_, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            let exists: i64 = tx
                .query_row(
                    "SELECT count(*) FROM sources WHERE id=? AND deleted=0",
                    [source],
                    |r| r.get(0),
                )
                .map_err(|_| "source unavailable")?;
            if exists == 0 {
                return Err("source not found".into());
            }
            note_tables(tx)?;
            tx.execute(
                "INSERT INTO notes VALUES (?,?,?,?,?)",
                params![id, source, title, body, now],
            )
            .map_err(|_| "note insert failed")?;
            tx.execute(
                "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
                params![id, 1, title, body, "Initial note", "unknown", now],
            )
            .map_err(|_| "note history insert failed")?;
            Ok(())
        })?;
        return Ok(
            json!({"note_id":id,"source_id":source,"revision":revision,"evidence_class":"human_note_unverified"}),
        );
    }
    let id = required_text(args, "note_id")?;
    let actor = required_text(args, "actor")?.trim();
    if actor.is_empty() || actor.len() > 255 {
        return Err("invalid note actor".into());
    }
    if operation == "evidence.note_revise" {
        let title = required_text(args, "title")?.trim();
        let body = required_text(args, "body")?.trim();
        let rationale = required_text(args, "rationale")?.trim();
        if title.is_empty()
            || title.chars().count() > 300
            || body.is_empty()
            || body.chars().count() > 250_000
            || rationale.is_empty()
            || rationale.len() > 5000
        {
            return Err("invalid note revision".into());
        }
        let payload = json!({"note_id":id,"body_sha256":digest(body.as_bytes()),"actor":actor,"rationale":rationale});
        let (note_revision, project_revision) =
            mutate(store, operation, ctx, &payload, |tx, now| {
                let (old_title, old_body, _) = adopt_note(tx, id)?;
                let deleted: i64 = tx
                    .query_row(
                        "SELECT count(*) FROM note_tombstones WHERE note_id=?",
                        [id],
                        |r| r.get(0),
                    )
                    .map_err(|_| "note tombstone unavailable")?;
                if deleted != 0 || (old_title == title && old_body == body) {
                    return Err("note deleted or unchanged".into());
                }
                let version: i64 = tx
                    .query_row(
                        "SELECT max(revision) FROM note_revisions WHERE note_id=?",
                        [id],
                        |r| r.get(0),
                    )
                    .map_err(|_| "note revision unavailable")?;
                let next = version.checked_add(1).ok_or("note revision overflow")?;
                tx.execute(
                    "INSERT INTO note_revisions VALUES (?,?,?,?,?,?,?)",
                    params![id, next, title, body, rationale, actor, now],
                )
                .map_err(|_| "revision insert failed")?;
                tx.execute(
                    "UPDATE notes SET title=?,body=? WHERE id=?",
                    params![title, body, id],
                )
                .map_err(|_| "note update failed")?;
                Ok(next)
            })?;
        Ok(
            json!({"note_id":id,"note_revision":note_revision,"project_revision":project_revision,"history_preserved":true}),
        )
    } else {
        let reason = required_text(args, "reason")?.trim();
        if reason.is_empty() || reason.len() > 5000 {
            return Err("invalid deletion reason".into());
        }
        let payload = json!({"note_id":id,"actor":actor,"reason":reason});
        let (_, project_revision) = mutate(store, operation, ctx, &payload, |tx, now| {
            adopt_note(tx, id)?;
            let deleted: i64 = tx
                .query_row(
                    "SELECT count(*) FROM note_tombstones WHERE note_id=?",
                    [id],
                    |r| r.get(0),
                )
                .map_err(|_| "tombstone query failed")?;
            if deleted != 0 {
                return Err("note already deleted".into());
            }
            tx.execute(
                "INSERT INTO note_tombstones VALUES (?,?,?,?)",
                params![id, reason, actor, now],
            )
            .map_err(|_| "tombstone insert failed")?;
            Ok(())
        })?;
        Ok(
            json!({"note_id":id,"deleted":true,"physical_row_preserved":true,"project_revision":project_revision}),
        )
    }
}

fn note_history(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let id = required_text(args, "note_id")?;
    let (source, title, body, created): (String, String, String, String) = store
        .connection()
        .query_row(
            "SELECT source_id,title,body,created_at FROM notes WHERE id=?",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .map_err(|_| "note not found")?;
    let exists: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='note_revisions'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| "schema query failed")?;
    let mut revisions = vec![json!({"note_id":id,"revision":1,"title":title,"body":body,
        "rationale":"Legacy note without explicit revision metadata","actor":"unknown","recorded_at":created})];
    if exists != 0 {
        let mut stmt=store.connection().prepare("SELECT revision,title,body,rationale,actor,recorded_at FROM note_revisions WHERE note_id=? ORDER BY revision")
            .map_err(|_|"note history unavailable")?;
        let rows = stmt
            .query_map([id], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                    r.get::<_, String>(4)?,
                    r.get::<_, String>(5)?,
                ))
            })
            .map_err(|_| "note history unavailable")?;
        let mut recorded = Vec::new();
        for row in rows {
            let (revision, title, body, rationale, actor, recorded_at) =
                row.map_err(|_| "corrupt note history")?;
            recorded.push(json!({"note_id":id,"revision":revision,"title":title,"body":body,"rationale":rationale,"actor":actor,"recorded_at":recorded_at}));
        }
        if !recorded.is_empty() {
            revisions = recorded;
        }
    }
    let tombstone_exists: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='note_tombstones'",
            [],
            |r| r.get(0),
        )
        .map_err(|_| "tombstone schema unavailable")?;
    let tombstone = if tombstone_exists == 0 {
        None
    } else {
        use rusqlite::OptionalExtension;
        store.connection().query_row("SELECT reason,actor,deleted_at FROM note_tombstones WHERE note_id=?",[id],
            |r|Ok(json!({"note_id":id,"reason":r.get::<_,String>(0)?,"actor":r.get::<_,String>(1)?,"deleted_at":r.get::<_,String>(2)?})))
            .optional().map_err(|_|"tombstone query failed")?
    };
    Ok(
        json!({"note_id":id,"source_id":source,"revisions":revisions,"deleted":tombstone.is_some(),"tombstone":tombstone}),
    )
}

fn question_history(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let id = required_text(args, "question_id")?;
    let exists: i64 = store
        .connection()
        .query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='research_questions'",
            [],
            |row| row.get(0),
        )
        .map_err(|_| "schema check failed")?;
    if exists == 0 {
        return Ok(json!({"history":[]}));
    }
    let mut statement = store.connection().prepare(
        "SELECT version,question,framework,fields_json,rationale,author,recorded_at,content_sha256 FROM research_questions WHERE id=? ORDER BY version"
    ).map_err(|_| "question history unavailable")?;
    let rows = statement
        .query_map([id], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
                row.get::<_, String>(6)?,
                row.get::<_, String>(7)?,
            ))
        })
        .map_err(|_| "question history unavailable")?;
    let mut history = Vec::new();
    for row in rows {
        let (version, question, framework, fields, rationale, author, recorded_at, content_sha256) =
            row.map_err(|_| "corrupt question history")?;
        let fields: Value = serde_json::from_str(&fields).map_err(|_| "corrupt question fields")?;
        history.push(
            json!({"question_id":id,"version":version,"question":question,"framework":framework,
            "fields":fields,"rationale":rationale,"author":author,"recorded_at":recorded_at,
            "content_sha256":content_sha256,"hypotheses_generated":0}),
        );
    }
    Ok(json!({"history":history}))
}

fn question_mutate(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    let feedback = question_feedback(args)?;
    if feedback["ready_to_record"] != true {
        return Err("incomplete question framework".into());
    }
    let question = required_text(args, "question")?.trim();
    let framework = required_text(args, "framework")?;
    let author = required_text(args, "author")?.trim();
    let rationale = if operation == "question.create" {
        "Initial structured question"
    } else {
        required_text(args, "rationale")?.trim()
    };
    if author.is_empty() || author.len() > 255 || rationale.is_empty() || rationale.len() > 5000 {
        return Err("invalid question author or rationale".into());
    }
    let fields = args["fields"].as_object().ok_or("invalid fields")?;
    let mut normalized = Map::new();
    for (key, val) in fields {
        let text = val.as_str().ok_or("question fields must be strings")?;
        normalized.insert(key.clone(), Value::String(text.trim().into()));
    }
    let document = json!({"question":question,"framework":framework,"fields":normalized,"rationale":rationale,"author":author});
    let content_sha256 = digest(
        serde_json::to_string(&document)
            .map_err(|_| "invalid document")?
            .as_bytes(),
    );
    let fields_json = serde_json::to_string(&normalized).map_err(|_| "invalid fields")?;
    let id = if operation == "question.create" {
        uuid::Uuid::new_v4().to_string()
    } else {
        required_text(args, "question_id")?.to_owned()
    };
    let payload = if operation == "question.create" {
        json!({"question_id":id,"version":1,"framework":framework,"content_sha256":content_sha256,"hypotheses_generated":0})
    } else {
        json!({"question_id":id,"framework":framework,"content_sha256":content_sha256,"hypotheses_generated":0})
    };
    let (version, revision) = mutate(store, operation, ctx, &payload, |tx, now| {
        tx.execute_batch(
            "CREATE TABLE IF NOT EXISTS research_questions (
            id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
            question TEXT NOT NULL,framework TEXT NOT NULL,fields_json TEXT NOT NULL,
            rationale TEXT NOT NULL,author TEXT NOT NULL,recorded_at TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,PRIMARY KEY(id,version))",
        )
        .map_err(|_| "question schema failed")?;
        let version = if operation == "question.create" {
            1
        } else {
            let (old_version,old_hash):(i64,String)=tx.query_row(
                "SELECT version,content_sha256 FROM research_questions WHERE id=? ORDER BY version DESC LIMIT 1",
                [&id], |row| Ok((row.get(0)?,row.get(1)?))).map_err(|_| "question not found")?;
            if old_hash == content_sha256 {
                return Err("no question changes".into());
            }
            old_version.checked_add(1).ok_or("version overflow")?
        };
        tx.execute(
            "INSERT INTO research_questions VALUES (?,?,?,?,?,?,?,?,?)",
            params![
                id,
                version,
                question,
                framework,
                fields_json,
                rationale,
                author,
                now,
                content_sha256
            ],
        )
        .map_err(|_| "question insertion failed")?;
        Ok(version)
    })?;
    Ok(
        json!({"question_id":id,"version":version,"framework":framework,"content_sha256":content_sha256,
        "hypotheses_generated":0,"project_revision":revision}),
    )
}

fn question_feedback(args: &Value) -> Result<Value, String> {
    let question = required_text(args, "question")?;
    if question.trim().is_empty() {
        return Err("blank question".into());
    }
    let framework = required_text(args, "framework")?;
    let required: &[&str] = match framework {
        "PICO" => &["population", "intervention", "comparison", "outcome"],
        "PECO" => &["population", "exposure", "comparison", "outcome"],
        "SPIDER" => &[
            "sample",
            "phenomenon",
            "design",
            "evaluation",
            "research_type",
        ],
        "EXPLORATORY" => &["topic", "population"],
        _ => return Err("unknown framework".into()),
    };
    let fields: &Map<String, Value> = args
        .get("fields")
        .and_then(Value::as_object)
        .ok_or("fields required")?;
    let missing: Vec<_> = required
        .iter()
        .filter(|key| {
            fields
                .get(**key)
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .is_empty()
        })
        .collect();
    let mut warnings = Vec::new();
    if question.len() < 20 {
        warnings.push("Question may be too broad or underspecified.");
    }
    if framework == "EXPLORATORY" {
        warnings.push("Exploratory questions do not imply a confirmatory hypothesis.");
    }
    if !missing.is_empty() {
        warnings.push("Complete the framework fields before protocol registration.");
    }
    Ok(
        json!({"framework":framework,"missing_fields":missing,"warnings":warnings,
        "ready_to_record":missing.is_empty(),"hypotheses_generated":0}),
    )
}

fn writing_mutate(
    store: &mut ProjectStore,
    operation: &str,
    args: &Value,
    ctx: &DispatchContext,
) -> Result<Value, String> {
    match operation {
        "writing.section_save" => {
            let manuscript_id = required_text(args, "manuscript_id")?.trim();
            let section = required_text(args, "section")?.trim();
            let body = required_text(args, "body")?;
            if manuscript_id.is_empty()
                || manuscript_id.len() > 128
                || section.is_empty()
                || section.chars().count() > 160
                || body.chars().count() > 1_000_000
            {
                return Err("invalid manuscript section".into());
            }
            let citations = args
                .get("citations")
                .and_then(Value::as_array)
                .ok_or("citations array required")?;
            if citations.len() > 10_000
                || citations.iter().any(|citation| {
                    citation
                        .as_str()
                        .is_none_or(|value| value.is_empty() || value.len() > 256)
                })
            {
                return Err("invalid citations".into());
            }
            let citations_json =
                serde_json::to_string(citations).map_err(|_| "invalid citations")?;
            let body_sha256 = digest(body.as_bytes());
            let payload = json!({
                "manuscript_id":manuscript_id,
                "section":section,
                "body_sha256":body_sha256,
                "citations":citations
            });
            let (section_revision, project_revision) = mutate(
                store,
                operation,
                ctx,
                &payload,
                |tx, now| {
                    let latest: i64 = tx
                        .query_row(
                            "SELECT COALESCE(MAX(revision),0) FROM manuscripts WHERE id=?1 AND section=?2",
                            params![manuscript_id, section],
                            |row| row.get(0),
                        )
                        .map_err(|_| "manuscript revision unavailable")?;
                    let next = latest
                        .checked_add(1)
                        .ok_or("manuscript revision overflow")?;
                    tx.execute(
                        "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at) VALUES (?1,?2,?3,?4,?5,?6)",
                        params![manuscript_id, section, next, body, citations_json, now],
                    )
                    .map_err(|_| "manuscript section insert failed")?;
                    Ok(next)
                },
            )?;
            Ok(json!({
                "manuscript_id":manuscript_id,
                "section":section,
                "section_revision":section_revision,
                "project_revision":project_revision,
                "body_sha256":body_sha256,
                "autosave_safe":true
            }))
        }
        "writing.section_restore" => {
            let manuscript_id = required_text(args, "manuscript_id")?.trim();
            let section = required_text(args, "section")?.trim();
            let source_revision = args
                .get("source_revision")
                .and_then(Value::as_i64)
                .filter(|revision| *revision > 0)
                .ok_or("invalid source_revision")?;
            if manuscript_id.is_empty()
                || manuscript_id.len() > 128
                || section.is_empty()
                || section.chars().count() > 160
            {
                return Err("invalid manuscript section".into());
            }
            let payload = json!({
                "manuscript_id":manuscript_id,
                "section":section,
                "source_revision":source_revision
            });
            let (section_revision, project_revision) = mutate(
                store,
                operation,
                ctx,
                &payload,
                |tx, now| {
                    let (body, citations): (String, String) = tx
                        .query_row(
                            "SELECT body,citations_json FROM manuscripts WHERE id=?1 AND section=?2 AND revision=?3",
                            params![manuscript_id, section, source_revision],
                            |row| Ok((row.get(0)?, row.get(1)?)),
                        )
                        .map_err(|_| "source manuscript revision not found")?;
                    let latest: i64 = tx
                        .query_row(
                            "SELECT COALESCE(MAX(revision),0) FROM manuscripts WHERE id=?1 AND section=?2",
                            params![manuscript_id, section],
                            |row| row.get(0),
                        )
                        .map_err(|_| "manuscript revision unavailable")?;
                    if latest == source_revision {
                        return Err("source revision is already current".into());
                    }
                    let next = latest
                        .checked_add(1)
                        .ok_or("manuscript revision overflow")?;
                    tx.execute(
                        "INSERT INTO manuscripts(id,section,revision,body,citations_json,edited_at) VALUES (?1,?2,?3,?4,?5,?6)",
                        params![manuscript_id, section, next, body, citations, now],
                    )
                    .map_err(|_| "manuscript restore failed")?;
                    Ok(next)
                },
            )?;
            Ok(json!({
                "manuscript_id":manuscript_id,
                "section":section,
                "restored_from":source_revision,
                "section_revision":section_revision,
                "project_revision":project_revision
            }))
        }
        "writing.claim_add" => {
            let statement = required_text(args, "statement")?.trim();
            if statement.is_empty() || statement.chars().count() > 20_000 {
                return Err("invalid claim statement".into());
            }
            let note_id = args
                .get("note_id")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty());
            let anchor_id = args
                .get("anchor_id")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty());
            if note_id.is_none() && anchor_id.is_none() {
                return Err("claim requires note_id or anchor_id support".into());
            }
            if note_id.is_some_and(|value| value.len() > 128)
                || anchor_id.is_some_and(|value| value.len() > 128)
            {
                return Err("invalid claim support id".into());
            }
            let interpretation = args
                .get("interpretation")
                .and_then(Value::as_bool)
                .ok_or("interpretation boolean required")?;
            let claim_id = uuid::Uuid::new_v4().to_string();
            let payload = json!({
                "claim_id":claim_id,
                "statement_sha256":digest(statement.as_bytes()),
                "note_id":note_id,
                "anchor_id":anchor_id,
                "interpretation":interpretation
            });
            let (_, project_revision) = mutate(store, operation, ctx, &payload, |tx, _now| {
                if let Some(note_id) = note_id {
                    let count: i64 = tx
                        .query_row("SELECT count(*) FROM notes WHERE id=?1", [note_id], |row| {
                            row.get(0)
                        })
                        .map_err(|_| "note support query failed")?;
                    if count != 1 {
                        return Err("supporting note not found".into());
                    }
                }
                if let Some(anchor_id) = anchor_id {
                    let count: i64 = tx
                        .query_row(
                            "SELECT count(*) FROM anchors WHERE id=?1 AND verified=1",
                            [anchor_id],
                            |row| row.get(0),
                        )
                        .map_err(|_| "anchor support query failed")?;
                    if count != 1 {
                        return Err("supporting verified anchor not found".into());
                    }
                }
                tx.execute(
                    "INSERT INTO claims(id,note_id,anchor_id,statement,interpretation) VALUES (?1,?2,?3,?4,?5)",
                    params![
                        claim_id,
                        note_id,
                        anchor_id,
                        statement,
                        i64::from(interpretation)
                    ],
                )
                .map_err(|_| "claim insert failed")?;
                Ok(())
            })?;
            Ok(json!({
                "claim_id":claim_id,
                "project_revision":project_revision,
                "interpretation":interpretation,
                "support":{"note_id":note_id,"anchor_id":anchor_id}
            }))
        }
        _ => Err("unsupported writing mutation".into()),
    }
}

fn writing_read(store: &ProjectStore, operation: &str, args: &Value) -> Result<Value, String> {
    match operation {
        "writing.section_history" => {
            let manuscript_id = required_text(args, "manuscript_id")?;
            let section = required_text(args, "section")?;
            let mut statement = store
                .connection()
                .prepare(
                    "SELECT revision,body,citations_json,edited_at FROM manuscripts
                     WHERE id=?1 AND section=?2 ORDER BY revision",
                )
                .map_err(|_| "manuscript history unavailable")?;
            let rows = statement
                .query_map(params![manuscript_id, section], |row| {
                    Ok((
                        row.get::<_, i64>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                    ))
                })
                .map_err(|_| "manuscript history unavailable")?;
            let mut revisions = Vec::new();
            for row in rows {
                let (revision, body, citations, edited_at) =
                    row.map_err(|_| "manuscript history corrupted")?;
                let citations: Value =
                    serde_json::from_str(&citations).map_err(|_| "invalid manuscript citations")?;
                revisions.push(json!({
                    "revision":revision,
                    "body":body,
                    "citations":citations,
                    "edited_at":edited_at,
                    "body_sha256":digest(body.as_bytes())
                }));
            }
            Ok(json!({
                "manuscript_id":manuscript_id,
                "section":section,
                "revisions":revisions,
                "count":revisions.len()
            }))
        }
        "writing.inspect" | "writing.manuscript_export" => {
            let manuscript_id = required_text(args, "manuscript_id")?;
            let format = if operation == "writing.manuscript_export" {
                let value = args
                    .get("format")
                    .and_then(Value::as_str)
                    .unwrap_or("markdown");
                if !matches!(value, "markdown" | "html" | "docx" | "pdf") {
                    return Err("unsupported manuscript export format".into());
                }
                value
            } else {
                "markdown"
            };
            let mut statement = store
                .connection()
                .prepare(
                    "SELECT m.section,m.revision,m.body,m.citations_json,m.edited_at
                     FROM manuscripts m
                     JOIN (
                         SELECT section,MAX(revision) revision
                         FROM manuscripts WHERE id=?1 GROUP BY section
                     ) latest ON latest.section=m.section AND latest.revision=m.revision
                     WHERE m.id=?1 ORDER BY m.section",
                )
                .map_err(|_| "manuscript unavailable")?;
            let rows = statement
                .query_map([manuscript_id], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, i64>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, String>(4)?,
                    ))
                })
                .map_err(|_| "manuscript unavailable")?;
            let mut sections = Vec::new();
            let mut markdown = Vec::new();
            let mut content = Vec::new();
            for row in rows {
                let (section, revision, body, citations, edited_at) =
                    row.map_err(|_| "manuscript data corrupted")?;
                let citations: Value =
                    serde_json::from_str(&citations).map_err(|_| "invalid manuscript citations")?;
                if operation == "writing.manuscript_export" {
                    markdown.push(format!("## {section}\n\n{body}\n"));
                    content.push((section.clone(), body.clone()));
                }
                sections.push(json!({
                    "section":section,
                    "revision":revision,
                    "body":body,
                    "citations":citations,
                    "edited_at":edited_at,
                    "body_sha256":digest(body.as_bytes())
                }));
            }
            if sections.is_empty() {
                return Err("manuscript not found".into());
            }
            if operation == "writing.manuscript_export" {
                let formatted = publishing_formats::export(format, &content, &markdown.join("\n"))?;
                let mut receipt = json!({
                    "manuscript_id":manuscript_id,
                    "text":markdown.join("\n"),
                    "sections":sections.len(),
                    "verified_from_persisted_revisions":true,
                    "section_revisions":sections.iter().map(|section| json!({
                        "section":section["section"],"revision":section["revision"],
                        "body_sha256":section["body_sha256"]
                    })).collect::<Vec<_>>()
                });
                receipt
                    .as_object_mut()
                    .unwrap()
                    .extend(formatted.as_object().unwrap().clone());
                let extension = match format {
                    "markdown" => "md",
                    "html" => "html",
                    "docx" => "docx",
                    "pdf" => "pdf",
                    _ => unreachable!("format was validated above"),
                };
                receipt["suggested_filename"] = json!(format!("{manuscript_id}.{extension}"));
                Ok(receipt)
            } else {
                Ok(json!({
                    "manuscript_id":manuscript_id,
                    "sections":sections,
                    "count":sections.len()
                }))
            }
        }
        "writing.claim_check" => {
            let claim_id = required_text(args, "claim_id")?;
            let (note_id, anchor_id, statement, interpretation): (
                Option<String>,
                Option<String>,
                String,
                i64,
            ) = store
                .connection()
                .query_row(
                    "SELECT note_id,anchor_id,statement,interpretation FROM claims WHERE id=?1",
                    [claim_id],
                    |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
                )
                .map_err(|_| "claim not found")?;
            let note_exists = if let Some(note_id) = note_id.as_deref() {
                store
                    .connection()
                    .query_row("SELECT count(*) FROM notes WHERE id=?1", [note_id], |row| {
                        row.get::<_, i64>(0)
                    })
                    .map_err(|_| "note support query failed")?
                    == 1
            } else {
                false
            };
            let anchor_verified = if let Some(anchor_id) = anchor_id.as_deref() {
                store
                    .connection()
                    .query_row(
                        "SELECT count(*) FROM anchors WHERE id=?1 AND verified=1",
                        [anchor_id],
                        |row| row.get::<_, i64>(0),
                    )
                    .map_err(|_| "anchor support query failed")?
                    == 1
            } else {
                false
            };
            Ok(json!({
                "claim_id":claim_id,
                "statement":statement,
                "statement_sha256":digest(statement.as_bytes()),
                "interpretation":interpretation != 0,
                "support":{
                    "note_id":note_id,
                    "note_exists":note_exists,
                    "anchor_id":anchor_id,
                    "anchor_verified":anchor_verified
                },
                "supported":note_exists || anchor_verified
            }))
        }
        _ => Err("unsupported writing read".into()),
    }
}

impl OperationHandler for EvidenceHandler {
    fn preview(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        let result = if matches!(
            operation,
            "protocol.create"
                | "protocol.amend"
                | "question.create"
                | "question.amend"
                | "evidence.note"
                | "evidence.note_revise"
                | "evidence.note_delete"
                | "ui.notebook.save"
                | "evidence.anchor"
                | "evidence.highlight_create"
                | "evidence.highlight_relocate"
                | "qualitative.add_code"
                | "qualitative.update_code"
                | "qualitative.delete_code"
                | "qualitative.annotate"
                | "qualitative.transcript_register"
                | "qualitative.transcript_update"
                | "writing.section_save"
                | "writing.section_restore"
                | "writing.claim_add"
                | "review.record_add"
                | "review.vote"
                | "review.screen"
                | "review.adjudicate"
                | "review.advance"
                | "review.extract"
                | "review.form_create"
                | "review.form_revise"
                | "review.form_record"
        ) {
            self.preview_write(operation, arguments, context)
        } else {
            self.run(operation, arguments, context)
        };
        match result {
            Ok(data) => json!({"status":"ok","data":data}),
            Err(error) => {
                json!({"status":"error","error":{"code":"INVALID_INPUT","message":error}})
            }
        }
    }
    fn execute(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        match self.run(operation, arguments, context) {
            Ok(data) => json!({"status":"ok","data":data}),
            Err(error) => {
                json!({"status":"error","error":{"code":"INVALID_INPUT","message":error}})
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_project::ProjectInfo;
    use uuid::Uuid;

    #[test]
    fn host_bound_handler_preserves_exact_project_path_and_preview_is_read_only() {
        let folder = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let path = folder.path().join("Chosen Evidence Folder");
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Bound evidence".into(),
                question: "Question".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        let handler = EvidenceHandler::bound(project_id, &path).unwrap();
        let ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "desktop-host".into(),
            expected_revision: Some(0),
        };
        let args = json!({
            "project_id":project_id.to_string(),
            "title":"Protocol",
            "author":"researcher",
            "body":{"design":"observational","objective":"Bound path proof"}
        });
        let preview = handler.preview("protocol.create", &args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["authoritative_revision"], 0);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let created = handler.execute("protocol.create", &args, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            1
        );

        let wrong_id = Uuid::new_v4();
        let wrong = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: wrong_id,
            actor: "desktop-host".into(),
            expected_revision: None,
        };
        assert_eq!(
            handler.execute(
                "protocol.history",
                &json!({"project_id":wrong_id.to_string(),"protocol_id":"missing"}),
                &wrong
            )["status"],
            "error"
        );
    }

    #[test]
    fn review_registration_and_independent_screening_are_persistent_and_revision_guarded() {
        let folder = tempfile::tempdir().unwrap();
        let id = Uuid::new_v4();
        let path = folder.path().join(id.to_string());
        let store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: id.to_string(),
                title: "Screening".into(),
                question: "Review".into(),
                design: "systematic_review".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        store.connection().execute(
            "INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES (?1,'Real record','[]',2024,NULL,'article','bibtex','', '{}','unverified',?2)",
            params!["ref-1", timestamp()],
        ).unwrap();
        drop(store);
        let handler = EvidenceHandler::new(folder.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: id,
            actor: "screening-tester".into(),
            expected_revision: Some(0),
        };
        let base =
            json!({"project_id": id.to_string(), "review_id": "review-A", "reference_id": "ref-1"});
        let preview = handler.preview("review.record_add", &base, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let created = handler.execute("review.record_add", &base, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        let record = created["data"]["record_id"].as_str().unwrap();
        assert_eq!(created["data"]["project_revision"], 1);
        let duplicate = handler.execute("review.record_add", &base, &ctx);
        assert_eq!(duplicate["status"], "error");
        let list = handler.execute(
            "review.records",
            &json!({"project_id":id.to_string(),"review_id":"review-A"}),
            &ctx,
        );
        assert_eq!(list["data"]["records"].as_array().unwrap().len(), 1);
        ctx.expected_revision = Some(1);
        ctx.request_id = Uuid::new_v4();
        let vote = json!({"project_id":id.to_string(),"review_id":"review-A","record_id":record,
          "reviewer":"reviewer-1","stage":"title_abstract","decision":"exclude","reason":"Wrong population"});
        assert_eq!(handler.execute("review.vote", &vote, &ctx)["status"], "ok");
        ctx.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute("review.vote", &vote, &ctx)["status"],
            "error"
        );
        let votes = handler.execute(
            "review.votes",
            &json!({"project_id":id.to_string(),"review_id":"review-A","record_id":record}),
            &ctx,
        );
        assert_eq!(votes["data"]["votes"][0]["decision"], "exclude");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            2
        );
        assert_eq!(
            ProjectStore::open(&path)
                .unwrap()
                .connection()
                .query_row("SELECT count(*) FROM events", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            2
        );
    }

    #[test]
    fn review_screen_blinds_peer_vote_until_two_and_prisma_exposes_unresolved_conflict() {
        let folder = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let path = folder.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Blinded review".into(),
                question: "Screen independently".into(),
                design: "systematic_review".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at)
                 VALUES ('ref-1','Article','[]',2026,NULL,'article','bibtex','','{}','unverified',?1)",
                [timestamp()],
            )
            .unwrap();
        drop(store);
        let handler = EvidenceHandler::new(folder.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "reviewer".into(),
            expected_revision: Some(0),
        };
        let record = handler.execute(
            "review.record_add",
            &json!({"project_id":project_id.to_string(),"review_id":"r","reference_id":"ref-1"}),
            &ctx,
        );
        let record_id = record["data"]["record_id"].as_str().unwrap().to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let alice = handler.execute(
            "review.screen",
            &json!({
                "project_id":project_id.to_string(),
                "review_id":"r",
                "record_id":record_id,
                "reviewer":"Alice",
                "stage":"title_abstract",
                "decision":"include",
                "reason":"Relevant"
            }),
            &ctx,
        );
        assert_eq!(alice["status"], "ok", "{alice}");
        let hidden = handler.execute(
            "review.status",
            &json!({
                "project_id":project_id.to_string(),
                "review_id":"r",
                "record_id":record_id,
                "stage":"title_abstract"
            }),
            &ctx,
        );
        assert_eq!(hidden["data"]["status"], "pending_second_vote");
        assert_eq!(hidden["data"]["votes"], json!([]));
        assert_eq!(hidden["data"]["blinded"], true);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let bob = handler.execute(
            "review.screen",
            &json!({
                "project_id":project_id.to_string(),
                "review_id":"r",
                "record_id":record_id,
                "reviewer":"Bob",
                "stage":"title_abstract",
                "decision":"exclude",
                "reason":"Wrong population"
            }),
            &ctx,
        );
        assert_eq!(bob["status"], "ok", "{bob}");
        let conflict = handler.execute(
            "review.status",
            &json!({
                "project_id":project_id.to_string(),
                "review_id":"r",
                "record_id":record_id,
                "stage":"title_abstract"
            }),
            &ctx,
        );
        assert_eq!(conflict["data"]["status"], "conflict");
        assert_eq!(conflict["data"]["votes"].as_array().unwrap().len(), 2);
        assert_eq!(conflict["data"]["blinded"], false);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(3);
        let third = handler.execute(
            "review.screen",
            &json!({
                "project_id":project_id.to_string(),
                "review_id":"r",
                "record_id":record_id,
                "reviewer":"Charlie",
                "stage":"title_abstract",
                "decision":"include",
                "reason":"Also relevant"
            }),
            &ctx,
        );
        assert_eq!(third["status"], "error");
        assert!(third["error"]["message"]
            .as_str()
            .unwrap()
            .contains("two reviewers"));
        let prisma = handler.execute(
            "review.prisma",
            &json!({"project_id":project_id.to_string(),"review_id":"r"}),
            &ctx,
        );
        assert_eq!(prisma["data"]["records_identified"], 1);
        assert_eq!(prisma["data"]["unresolved_title"], 1);
        assert_eq!(prisma["data"]["complete_prisma_2020"], false);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            3
        );
    }

    #[test]
    fn review_disagreement_adjudication_advance_and_extraction_persist() {
        let folder = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let path = folder.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Review".into(),
                question: "Evidence".into(),
                design: "systematic_review".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        store.connection().execute("INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at) VALUES ('ref-1','Article','[]',2025,NULL,'article','bibtex','','{}','unverified',?1)",[timestamp()]).unwrap();
        drop(store);
        let handler = EvidenceHandler::new(folder.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "reviewer".into(),
            expected_revision: Some(0),
        };
        let common = json!({"project_id":project_id.to_string(),"review_id":"rev"});
        let record = handler.execute(
            "review.record_add",
            &json!({"project_id":project_id.to_string(),"review_id":"rev","reference_id":"ref-1"}),
            &ctx,
        );
        assert_eq!(record["status"], "ok", "{record}");
        let rid = record["data"]["record_id"].as_str().unwrap();
        let advance =
            json!({"project_id":project_id.to_string(),"review_id":"rev","record_id":rid});
        ctx.expected_revision = Some(1);
        ctx.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute("review.advance", &advance, &ctx)["status"],
            "error"
        );
        for (reviewer, decision) in [("Alice", "include"), ("Bob", "exclude")] {
            let args = json!({"project_id":project_id.to_string(),"review_id":"rev","record_id":rid,"reviewer":reviewer,"stage":"title_abstract","decision":decision,"reason":"Independent assessment"});
            ctx.request_id = Uuid::new_v4();
            assert_eq!(handler.execute("review.vote", &args, &ctx)["status"], "ok");
            ctx.expected_revision = Some(ctx.expected_revision.unwrap() + 1);
        }
        let adjudicate = json!({"project_id":project_id.to_string(),"review_id":"rev","record_id":rid,"stage":"title_abstract","decision":"include","reason":"Full text should be assessed","adjudicator":"Lead"});
        ctx.request_id = Uuid::new_v4();
        let preview = handler.preview("review.adjudicate", &adjudicate, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            3
        );
        assert_eq!(
            handler.execute("review.adjudicate", &adjudicate, &ctx)["status"],
            "ok"
        );
        ctx.expected_revision = Some(4);
        ctx.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute("review.advance", &advance, &ctx)["status"],
            "ok"
        );
        ctx.expected_revision = Some(5);
        ctx.request_id = Uuid::new_v4();
        let extract = json!({"project_id":project_id.to_string(),"review_id":"rev","record_id":rid,"field_name":"sample_size","value":120,"reviewer":"Alice","unit":"people"});
        let result = handler.execute("review.extract", &extract, &ctx);
        assert_eq!(result["status"], "ok", "{result}");
        let results = handler.execute(
            "review.extractions",
            &json!({"project_id":project_id.to_string(),"review_id":"rev","record_id":rid}),
            &ctx,
        );
        assert_eq!(results["data"]["extractions"][0]["value"], 120);
        let decisions = handler.execute(
            "review.adjudications",
            &json!({"project_id":project_id.to_string(),"review_id":"rev","record_id":rid}),
            &ctx,
        );
        assert_eq!(decisions["data"]["adjudications"][0]["decision"], "include");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            6
        );
        assert_eq!(
            ProjectStore::open(&path)
                .unwrap()
                .connection()
                .query_row("SELECT count(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            6
        );
        let _ = common;
    }

    fn context() -> DispatchContext {
        DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "researcher".into(),
            expected_revision: None,
        }
    }

    #[test]
    fn questions_notes_anchor_history_cas_unicode() {
        let root = std::env::temp_dir().join(format!("rw-evidence-more-{}", Uuid::new_v4()));
        std::fs::create_dir(&root).unwrap();
        let mut ctx = context();
        let id = ctx.project_id.to_string();
        let store = ProjectStore::create(
            root.join(&id),
            &ProjectInfo {
                id: id.clone(),
                title: "آزمایش".into(),
                question: "بررسی".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        let text = "پژوهش و داده‌های ساختگی";
        let hash = store.put_object(text.as_bytes()).unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO sources VALUES (?,?,?,?,?,?,?)",
                params![
                    "source-1",
                    "منبع",
                    "text/plain",
                    hash,
                    timestamp(),
                    "synthetic",
                    0
                ],
            )
            .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO document_text VALUES (?,?,?,?)",
                params!["source-1", text, "test-extraction", digest(text.as_bytes())],
            )
            .unwrap();
        drop(store);
        let handler = EvidenceHandler::new(root.clone());
        ctx.expected_revision = Some(0);
        let question = json!({"project_id":id,"question":"آیا این داده‌ها معتبر هستند؟",
            "framework":"EXPLORATORY","fields":{"topic":"علوم شناختی","population":"بزرگسالان"},"author":"پژوهشگر"});
        let created = handler.execute("question.create", &question, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        let qid = created["data"]["question_id"].as_str().unwrap();
        assert_eq!(
            handler.execute("question.create", &question, &ctx)["status"],
            "error"
        );
        let mut stale = context();
        stale.project_id = ctx.project_id;
        stale.expected_revision = Some(0);
        assert_eq!(
            handler.execute("question.create", &question, &stale)["status"],
            "error"
        );
        let mut qctx = context();
        qctx.project_id = ctx.project_id;
        qctx.expected_revision = Some(1);
        let amended=handler.execute("question.amend",&json!({"project_id":id,"question_id":qid,
            "question":"آیا داده‌های شناختی تکرارپذیر هستند؟","framework":"EXPLORATORY",
            "fields":{"topic":"شناخت","population":"بزرگسالان"},"author":"پژوهشگر","rationale":"دقت بیشتر"}),&qctx);
        assert_eq!(amended["status"], "ok", "{amended}");
        let history = handler.execute(
            "question.history",
            &json!({"project_id":id,"question_id":qid}),
            &qctx,
        );
        assert_eq!(history["data"]["history"].as_array().unwrap().len(), 2);
        let mut actx = context();
        actx.project_id = ctx.project_id;
        actx.expected_revision = Some(2);
        let anchor = handler.execute(
            "evidence.anchor",
            &json!({"project_id":id,"source_id":"source-1",
            "quote":"پژوهش","start":0,"end":5}),
            &actx,
        );
        assert_eq!(anchor["data"]["quote_verified"], true, "{anchor}");
        let mut nctx = context();
        nctx.project_id = ctx.project_id;
        nctx.expected_revision = Some(3);
        let note = handler.execute(
            "evidence.note",
            &json!({"project_id":id,"source_id":"source-1",
            "title":"یادداشت نخست","body":"برداشت انسانی"}),
            &nctx,
        );
        assert_eq!(note["status"], "ok", "{note}");
        let nid = note["data"]["note_id"].as_str().unwrap();
        let mut rctx = context();
        rctx.project_id = ctx.project_id;
        rctx.expected_revision = Some(4);
        let revised = handler.execute(
            "evidence.note_revise",
            &json!({"project_id":id,"note_id":nid,
            "title":"یادداشت دوم","body":"برداشت بازبینی‌شده","actor":"محقق","rationale":"تصحیح"}),
            &rctx,
        );
        assert_eq!(revised["status"], "ok", "{revised}");
        let revisions = handler.execute(
            "evidence.note_history",
            &json!({"project_id":id,"note_id":nid}),
            &rctx,
        );
        assert_eq!(revisions["data"]["revisions"].as_array().unwrap().len(), 2);
        let mut dctx = context();
        dctx.project_id = ctx.project_id;
        dctx.expected_revision = Some(5);
        let deleted = handler.execute(
            "evidence.note_delete",
            &json!({"project_id":id,"note_id":nid,
            "actor":"محقق","reason":"تکراری"}),
            &dctx,
        );
        assert_eq!(deleted["status"], "ok", "{deleted}");
        let h = handler.execute(
            "evidence.note_history",
            &json!({"project_id":id,"note_id":nid}),
            &dctx,
        );
        assert_eq!(h["data"]["deleted"], true);
        assert_eq!(h["data"]["revisions"].as_array().unwrap().len(), 2);
        let notebook =
            handler.execute("evidence.notebook_export", &json!({"project_id":id}), &dctx);
        assert!(!notebook["data"]["text"]
            .as_str()
            .unwrap()
            .contains("یادداشت دوم"));
        let reopened = ProjectStore::open(root.join(&id)).unwrap();
        assert_eq!(reopened.info().unwrap().revision, 6);
        assert_eq!(
            reopened
                .connection()
                .query_row("SELECT count(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            6
        );
        let mut stmt=reopened.connection().prepare("SELECT sequence,request_id,operation,actor,payload_json,payload_hash,previous_hash,event_hash,timestamp FROM events ORDER BY sequence").unwrap();
        let rows = stmt
            .query_map([], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                    r.get::<_, String>(4)?,
                    r.get::<_, String>(5)?,
                    r.get::<_, String>(6)?,
                    r.get::<_, String>(7)?,
                    r.get::<_, String>(8)?,
                ))
            })
            .unwrap();
        let mut previous = "0".repeat(64);
        for (index, row) in rows.enumerate() {
            let (
                seq,
                request_id,
                operation,
                actor,
                payload_json,
                payload_hash,
                previous_hash,
                event_hash,
                timestamp,
            ) = row.unwrap();
            assert_eq!(seq, index as i64 + 1);
            assert_eq!(payload_hash, digest(payload_json.as_bytes()));
            assert_eq!(previous_hash, previous);
            let expected = digest(
                serde_json::to_string(&json!([
                    seq,
                    request_id,
                    operation,
                    actor,
                    payload_hash,
                    previous_hash,
                    timestamp
                ]))
                .unwrap()
                .as_bytes(),
            );
            assert_eq!(event_hash, expected);
            previous = event_hash;
        }
        drop(stmt);
        drop(reopened);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn protocol_writes_reopen_cas_replay_unicode_and_diff() {
        let root = std::env::temp_dir().join(format!("rw-evidence-{}", Uuid::new_v4()));
        std::fs::create_dir(&root).unwrap();
        let mut ctx = context();
        let id = ctx.project_id.to_string();
        let store = ProjectStore::create(
            root.join(&id),
            &ProjectInfo {
                id: id.clone(),
                title: "پژوهش".into(),
                question: "آزمون".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        drop(store);
        let handler = EvidenceHandler::new(root.clone());
        ctx.expected_revision = Some(0);
        let input = json!({"project_id":id,"title":"پروتکل","author":"پژوهشگر",
            "body":{"design":"observational","objective":"بررسی داده‌ها"}});
        let preview = handler.preview("protocol.create", &input, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["preview"], true);
        assert_eq!(preview["data"]["authoritative_revision"], 0);
        assert_eq!(preview["data"]["simulated_revision"], 1);
        let unchanged = ProjectStore::open(root.join(&id)).unwrap();
        assert_eq!(unchanged.info().unwrap().revision, 0);
        assert_eq!(
            unchanged
                .connection()
                .query_row("SELECT count(*) FROM protocols", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            0
        );
        assert_eq!(
            unchanged
                .connection()
                .query_row("SELECT count(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            0
        );
        drop(unchanged);
        let created = handler.execute("protocol.create", &input, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        let protocol_id = created["data"]["protocol_id"].as_str().unwrap().to_owned();
        assert_eq!(
            handler.execute("protocol.create", &input, &ctx)["status"],
            "error"
        );
        let mut stale = context();
        stale.project_id = ctx.project_id;
        stale.expected_revision = Some(0);
        assert_eq!(
            handler.execute("protocol.create", &input, &stale)["status"],
            "error"
        );
        let mut next = context();
        next.project_id = ctx.project_id;
        next.expected_revision = Some(1);
        let amended = handler.execute(
            "protocol.amend",
            &json!({"project_id":id,"protocol_id":protocol_id,
            "author":"پژوهشگر","rationale":"اضافه کردن روش","body":{
            "design":"observational","objective":"بررسی داده‌ها","analysis":"آزمون"}}),
            &next,
        );
        assert_eq!(amended["status"], "ok", "{amended}");
        let opened = handler.execute("project.open", &json!({"project_id":id}), &next);
        assert_eq!(opened["data"]["revision"], 2);
        let diff = handler.execute(
            "protocol.diff",
            &json!({"project_id":id,"protocol_id":protocol_id,
            "from_version":1,"to_version":2}),
            &next,
        );
        assert_eq!(diff["data"]["changed_fields"], json!(["analysis"]));
        let conn = ProjectStore::open(root.join(&id)).unwrap();
        let events: i64 = conn
            .connection()
            .query_row("SELECT count(*) FROM events", [], |r| r.get(0))
            .unwrap();
        assert_eq!(events, 2);
        drop(conn);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn persian_question_feedback_matches_python_and_generates_no_hypothesis() {
        let handler = EvidenceHandler::new(PathBuf::from("unused"));
        let args = json!({"question":"آیا توجه با پیامدهای شناختی رابطه دارد؟",
            "framework":"PECO","fields":{"population":"بزرگسالان","exposure":"آزمایش",
            "comparison":"گروه شاهد","outcome":"دقت"}});
        let result = handler.execute("question.feedback", &args, &context());
        assert_eq!(result["status"], "ok");
        assert_eq!(result["data"]["ready_to_record"], true);
        assert_eq!(result["data"]["hypotheses_generated"], 0);
        assert_eq!(result["data"]["missing_fields"], json!([]));
    }

    #[test]
    fn incomplete_questions_are_read_only_and_identified() {
        let handler = EvidenceHandler::new(PathBuf::from("unused"));
        let result = handler.preview(
            "question.feedback",
            &json!({"question":"Tiny",
            "framework":"PICO","fields":{"population":"adults"}}),
            &context(),
        );
        assert_eq!(result["data"]["ready_to_record"], false);
        assert_eq!(
            result["data"]["missing_fields"],
            json!(["intervention", "comparison", "outcome"])
        );
        let caps = EvidenceHandler::capabilities();
        assert!(caps
            .iter()
            .filter(|cap| cap.operation.starts_with("protocol.")
                && matches!(cap.effect, Effect::LocalWrite))
            .all(|cap| cap.manifest["approval_required"] == true));
        assert!(caps
            .iter()
            .any(|cap| cap.operation == "protocol.create" && cap.effect == Effect::LocalWrite));
        assert!(!caps.iter().any(|cap| cap.operation == "project.migrate"));
    }

    #[test]
    fn manuscript_revision_restore_export_and_claim_support_are_persistent() {
        let root = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let project_path = root.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Writing".into(),
                question: "Can claims stay auditable?".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        let object_digest = store.put_object(b"source text").unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted)
                 VALUES ('source-1','Source','text/plain',?1,?2,'test',0)",
                params![object_digest, timestamp()],
            )
            .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO notes(id,source_id,title,body,created_at)
                 VALUES ('note-1','source-1','Evidence','Observed result',?1)",
                [timestamp()],
            )
            .unwrap();
        drop(store);

        let handler = EvidenceHandler::new(root.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "writer".into(),
            expected_revision: Some(0),
        };
        let first = json!({
            "project_id":project_id.to_string(),
            "manuscript_id":"paper-1",
            "section":"Results",
            "body":"First result.",
            "citations":["ref-a"]
        });
        let preview = handler.preview("writing.section_save", &first, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            0
        );
        let saved = handler.execute("writing.section_save", &first, &ctx);
        assert_eq!(saved["data"]["section_revision"], 1);
        assert_eq!(saved["data"]["project_revision"], 1);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let second = handler.execute(
            "writing.section_save",
            &json!({
                "project_id":project_id.to_string(),
                "manuscript_id":"paper-1",
                "section":"Results",
                "body":"Second result.",
                "citations":["ref-a","ref-b"]
            }),
            &ctx,
        );
        assert_eq!(second["data"]["section_revision"], 2);
        let history = handler.execute(
            "writing.section_history",
            &json!({
                "project_id":project_id.to_string(),
                "manuscript_id":"paper-1",
                "section":"Results"
            }),
            &ctx,
        );
        assert_eq!(history["data"]["count"], 2);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let restored = handler.execute(
            "writing.section_restore",
            &json!({
                "project_id":project_id.to_string(),
                "manuscript_id":"paper-1",
                "section":"Results",
                "source_revision":1
            }),
            &ctx,
        );
        assert_eq!(restored["data"]["section_revision"], 3);
        let exported = handler.execute(
            "writing.manuscript_export",
            &json!({
                "project_id":project_id.to_string(),
                "manuscript_id":"paper-1"
            }),
            &ctx,
        );
        assert!(exported["data"]["text"]
            .as_str()
            .unwrap()
            .contains("First result."));
        assert!(!exported["data"]["text"]
            .as_str()
            .unwrap()
            .contains("Second result."));

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(3);
        let claim = handler.execute(
            "writing.claim_add",
            &json!({
                "project_id":project_id.to_string(),
                "statement":"Observed result supports the claim.",
                "interpretation":true,
                "note_id":"note-1"
            }),
            &ctx,
        );
        assert_eq!(claim["status"], "ok", "{claim}");
        let claim_id = claim["data"]["claim_id"].as_str().unwrap();
        let checked = handler.execute(
            "writing.claim_check",
            &json!({
                "project_id":project_id.to_string(),
                "claim_id":claim_id
            }),
            &ctx,
        );
        assert_eq!(checked["data"]["supported"], true);
        assert_eq!(checked["data"]["support"]["note_exists"], true);
        let reopened = ProjectStore::open(&project_path).unwrap();
        assert_eq!(reopened.info().unwrap().revision, 4);
        assert_eq!(
            reopened
                .connection()
                .query_row("SELECT count(*) FROM events", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            4
        );
    }

    #[test]
    fn extraction_forms_validate_values_and_migrate_prior_records_explicitly() {
        let root = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let project_path = root.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Extraction".into(),
                question: "What was reported?".into(),
                design: "systematic_review".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO reference(id,title,authors_json,year,doi,kind,format,raw,metadata_json,status,imported_at)
                 VALUES ('ref-form','Study','[]',2026,NULL,'article','bibtex','','{}','unverified',?1)",
                [timestamp()],
            )
            .unwrap();
        drop(store);
        let handler = EvidenceHandler::new(root.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "extractor".into(),
            expected_revision: Some(0),
        };
        let record = handler.execute(
            "review.record_add",
            &json!({
                "project_id":project_id.to_string(),
                "review_id":"review-form",
                "reference_id":"ref-form"
            }),
            &ctx,
        );
        assert_eq!(record["status"], "ok", "{record}");
        let record_id = record["data"]["record_id"].as_str().unwrap().to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let create_args = json!({
            "project_id":project_id.to_string(),
            "name":"Core extraction",
            "author":"reviewer",
            "fields":[
                {
                    "name":"outcome",
                    "datatype":"category",
                    "required":true,
                    "permitted_values":["improved","unchanged"]
                },
                {
                    "name":"age",
                    "datatype":"integer",
                    "required":false,
                    "minimum":0,
                    "maximum":120,
                    "unit":"years"
                },
                {
                    "name":"note",
                    "datatype":"string",
                    "required":false
                }
            ]
        });
        let preview = handler.preview("review.form_create", &create_args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            1
        );
        let created = handler.execute("review.form_create", &create_args, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        let form_id = created["data"]["form_id"].as_str().unwrap().to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let recorded = handler.execute(
            "review.form_record",
            &json!({
                "project_id":project_id.to_string(),
                "form_id":form_id,
                "record_id":record_id,
                "reviewer":"reviewer-a",
                "values":{
                    "outcome":{"value":"improved","missingness":"present","original_text":"Improved"},
                    "age":{"value":42,"missingness":"present","unit":"years","original_text":"42 years"},
                    "note":{"value":null,"missingness":"not_reported","original_text":""}
                }
            }),
            &ctx,
        );
        assert_eq!(recorded["status"], "ok", "{recorded}");
        assert_eq!(recorded["data"]["form_version"], 1);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(3);
        let revised = handler.execute(
            "review.form_revise",
            &json!({
                "project_id":project_id.to_string(),
                "form_id":form_id,
                "author":"reviewer-b",
                "rationale":"Rename outcome and add optional quality note",
                "fields":[
                    {
                        "name":"decision",
                        "datatype":"category",
                        "required":true,
                        "permitted_values":["improved","unchanged"]
                    },
                    {
                        "name":"age",
                        "datatype":"integer",
                        "required":false,
                        "minimum":0,
                        "maximum":120,
                        "unit":"years"
                    },
                    {"name":"quality","datatype":"string","required":false}
                ],
                "migration":{"outcome":"decision","age":"age","note":null}
            }),
            &ctx,
        );
        assert_eq!(revised["status"], "ok", "{revised}");
        assert_eq!(revised["data"]["version"], 2);
        assert_eq!(revised["data"]["migrated_records"], 1);

        let history = handler.execute(
            "review.form_history",
            &json!({"project_id":project_id.to_string(),"form_id":form_id}),
            &ctx,
        );
        assert_eq!(history["data"]["count"], 2);
        let migrated = handler.execute(
            "review.form_values",
            &json!({
                "project_id":project_id.to_string(),
                "form_id":form_id,
                "version":2
            }),
            &ctx,
        );
        assert_eq!(migrated["data"]["count"], 1, "{migrated}");
        assert_eq!(
            migrated["data"]["values"][0]["values"]["decision"]["value"],
            "improved"
        );
        assert_eq!(
            migrated["data"]["values"][0]["values"]["quality"]["missingness"],
            "not_extracted"
        );
        assert!(!migrated["data"]["values"][0]["migrated_from"].is_null());
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            4
        );
    }

    #[test]
    fn qualitative_codebook_hash_guard_anchor_and_kappa_match_fixed_unit_semantics() {
        let root = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let project_path = root.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Qualitative".into(),
                question: "How is experience described?".into(),
                design: "qualitative".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        let body = "calm focus and sustained attention";
        let object_digest = store.put_object(body.as_bytes()).unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted)
                 VALUES ('source-qual','Transcript','text/plain',?1,?2,'test',0)",
                params![object_digest, timestamp()],
            )
            .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO document_text(source_id,body,extraction_version,body_hash)
                 VALUES ('source-qual',?1,'test',?2)",
                params![body, digest(body.as_bytes())],
            )
            .unwrap();
        drop(store);

        let handler = EvidenceHandler::new(root.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "coder".into(),
            expected_revision: Some(0),
        };
        let initial = handler.execute(
            "qualitative.inspect",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(initial["status"], "ok", "{initial}");
        let initial_hash = initial["data"]["content_hash"].as_str().unwrap().to_owned();

        let add_args = json!({
            "project_id":project_id.to_string(),
            "expected_content_hash":initial_hash,
            "code_id":"attention",
            "name":"Attention",
            "description":"Sustained focus",
            "actor":"coder"
        });
        let preview = handler.preview("qualitative.add_code", &add_args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            0
        );
        let added = handler.execute("qualitative.add_code", &add_args, &ctx);
        assert_eq!(added["status"], "ok", "{added}");
        assert_eq!(added["data"]["project_revision"], 1);
        let after_code = added["data"]["content_hash"].as_str().unwrap().to_owned();
        assert_ne!(after_code, initial_hash);

        let mut stale = ctx.clone();
        stale.request_id = Uuid::new_v4();
        stale.expected_revision = Some(1);
        let stale_hash = handler.execute(
            "qualitative.update_code",
            &json!({
                "project_id":project_id.to_string(),
                "expected_content_hash":initial_hash,
                "code_id":"attention",
                "actor":"coder",
                "name":"Changed"
            }),
            &stale,
        );
        assert_eq!(stale_hash["status"], "error");
        assert!(stale_hash["error"]["message"]
            .as_str()
            .unwrap()
            .contains("changed since it was read"));

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let annotated = handler.execute(
            "qualitative.annotate",
            &json!({
                "project_id":project_id.to_string(),
                "expected_content_hash":after_code,
                "source_id":"source-qual",
                "start":5,
                "end":10,
                "code_id":"attention",
                "coder":"coder-a",
                "unit_id":"unit-1"
            }),
            &ctx,
        );
        assert_eq!(annotated["status"], "ok", "{annotated}");
        assert_eq!(annotated["data"]["quote"], "focus");
        assert_eq!(annotated["data"]["quote_verified"], true);
        let after_annotation = annotated["data"]["content_hash"]
            .as_str()
            .unwrap()
            .to_owned();

        let inspected = handler.execute(
            "qualitative.inspect",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(
            inspected["data"]["state"]["codes"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            inspected["data"]["state"]["annotations"][0]["body_hash"],
            digest(body.as_bytes())
        );
        assert_eq!(inspected["data"]["content_hash"], after_annotation);
        let provenance = handler.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(provenance["status"], "ok", "{provenance}");
        assert_eq!(provenance["data"]["coding_hash"], after_annotation);
        assert_eq!(provenance["data"]["codebook_ids"], json!(["attention"]));
        assert_eq!(
            provenance["data"]["verified_annotations"][0]["quote_sha256"],
            digest(b"focus")
        );
        assert_eq!(provenance["data"]["case_mapping_available"], false);
        assert_eq!(provenance["data"]["quotes_disclosed"], false);
        let forged = handler.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string(),"coding_hash":"forged"}),
            &ctx,
        );
        assert_eq!(forged["status"], "error");
        let reopened = EvidenceHandler::new(root.path().to_path_buf());
        let restarted = reopened.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(restarted["data"], provenance["data"]);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let delete_referenced = handler.execute(
            "qualitative.delete_code",
            &json!({
                "project_id":project_id.to_string(),
                "expected_content_hash":after_annotation,
                "code_id":"attention",
                "actor":"coder"
            }),
            &ctx,
        );
        assert_eq!(delete_referenced["status"], "error");
        assert!(delete_referenced["error"]["message"]
            .as_str()
            .unwrap()
            .contains("still referenced"));

        let kappa = handler.execute(
            "qualitative.kappa",
            &json!({
                "first":{"u1":"a","u2":"a","u3":"b","u4":"b"},
                "second":{"u1":"a","u2":"b","u3":"b","u4":"b"}
            }),
            &ctx,
        );
        assert_eq!(kappa["status"], "ok", "{kappa}");
        assert!((kappa["data"]["observed_agreement"].as_f64().unwrap() - 0.75).abs() < 1e-12);
        assert!((kappa["data"]["expected_agreement"].as_f64().unwrap() - 0.5).abs() < 1e-12);
        assert!((kappa["data"]["kappa"].as_f64().unwrap() - 0.5).abs() < 1e-12);
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            2
        );
    }

    #[test]
    fn transcript_mapping_six_case_golden_restart_replay_and_privacy() {
        let root = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let path = root.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Synthetic qualitative cases".into(),
                question: "What patterns occur?".into(),
                design: "mixed".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO qualitative_codes(id,name,description,parent_id,active,created_at)
             VALUES ('theme','Theme','',NULL,1,?1)",
                [timestamp()],
            )
            .unwrap();
        let mut bodies = Vec::new();
        for i in 1..=7 {
            let source = format!("transcript-{i}");
            let body = format!("note λ private-participant-token-{i}");
            let object_hash = store.put_object(body.as_bytes()).unwrap();
            let body_hash = digest(body.as_bytes());
            store
                .connection()
                .execute(
                    "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted)
                 VALUES (?1,'Synthetic','text/plain',?2,?3,'test',0)",
                    params![source, object_hash, timestamp()],
                )
                .unwrap();
            store
                .connection()
                .execute(
                    "INSERT INTO document_text(source_id,body,extraction_version,body_hash)
                 VALUES (?1,?2,'test',?3)",
                    params![source, body, body_hash],
                )
                .unwrap();
            if i <= 3 || i == 7 {
                store.connection().execute(
                    "INSERT INTO qualitative_annotations(id,source_id,code_id,coder,start,end,quote,body_hash,recorded_at)
                     VALUES (?1,?2,'theme','coder',0,4,'note',?3,?4)",
                    params![format!("unit-{i}"),source,body_hash,timestamp()]
                ).unwrap();
            }
            bodies.push((source, body_hash));
        }
        drop(store);
        let handler = EvidenceHandler::new(root.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "coder".into(),
            expected_revision: Some(0),
        };
        let initial = handler.execute(
            "qualitative.inspect",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        let mut hash = initial["data"]["content_hash"].as_str().unwrap().to_owned();
        let absent = handler.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(absent["data"]["case_mapping_available"], false);
        assert_eq!(absent["data"]["qualitative_cases"], json!([]));
        let bad = handler.execute(
            "qualitative.transcript_register",
            &json!({"project_id":project_id.to_string(),"source_id":"transcript-1","case_id":" ",
                "confidential":true,"expected_body_hash":bodies[0].1,"expected_content_hash":hash}),
            &ctx,
        );
        assert_eq!(bad["status"], "error");
        for (index, (source, body_hash)) in bodies.iter().enumerate() {
            let case = if index == 6 { 1 } else { index + 1 };
            let args = json!({"project_id":project_id.to_string(),"source_id":source,
                "case_id":format!("case-{case}"),"confidential":true,
                "expected_body_hash":body_hash,"expected_content_hash":hash});
            if index == 0 {
                let preview = handler.preview("qualitative.transcript_register", &args, &ctx);
                assert_eq!(preview["status"], "ok", "{preview}");
                assert_eq!(
                    handler.execute(
                        "qualitative.inspect",
                        &json!({"project_id":project_id.to_string()}),
                        &ctx
                    )["data"]["content_hash"],
                    hash
                );
            }
            let result = handler.execute("qualitative.transcript_register", &args, &ctx);
            assert_eq!(result["status"], "ok", "{result}");
            hash = result["data"]["content_hash"].as_str().unwrap().to_owned();
            let replay = handler.execute("qualitative.transcript_register", &args, &ctx);
            assert_eq!(replay["status"], "error");
            ctx.expected_revision = Some((index + 1) as u64);
            ctx.request_id = Uuid::new_v4();
        }
        let provenance = handler.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(provenance["status"], "ok", "{provenance}");
        assert_eq!(provenance["data"]["case_mapping_available"], true);
        assert_eq!(
            provenance["data"]["qualitative_cases"]
                .as_array()
                .unwrap()
                .len(),
            6
        );
        assert_eq!(provenance["data"]["case_counts"]["case-1"]["theme"], 2);
        assert_eq!(provenance["data"]["case_counts"]["case-2"]["theme"], 1);
        assert_eq!(provenance["data"]["case_counts"]["case-4"]["theme"], 0);
        assert_eq!(provenance["data"]["quotes_disclosed"], false);
        assert!(!provenance.to_string().contains("private-participant-token"));
        let events: Vec<String> = {
            let store = ProjectStore::open(&path).unwrap();
            let mut stmt = store
                .connection()
                .prepare("SELECT payload_json FROM events ORDER BY sequence")
                .unwrap();
            let values = stmt
                .query_map([], |r| r.get::<_, String>(0))
                .unwrap()
                .collect::<Result<Vec<_>, _>>()
                .unwrap();
            values
        };
        assert_eq!(events.len(), 7);
        assert!(events.iter().all(|entry| !entry.contains("case-1")
            && !entry.contains("private-participant-token")
            && !entry.contains("transcript-1")));
        let reopened = EvidenceHandler::new(root.path().to_path_buf());
        assert_eq!(
            reopened.execute(
                "qualitative.mixed_provenance",
                &json!({"project_id":project_id.to_string()}),
                &ctx
            ),
            provenance
        );
        let duplicate = handler.execute(
            "qualitative.transcript_register",
            &json!({"project_id":project_id.to_string(),"source_id":"transcript-1",
                "case_id":"case-1","confidential":true,"expected_content_hash":hash,
                "expected_body_hash":bodies[0].1}),
            &ctx,
        );
        assert_eq!(duplicate["status"], "error");
        let stale=handler.execute("qualitative.transcript_update",
            &json!({"project_id":project_id.to_string(),"source_id":"transcript-1",
                "case_id":"changed","confidential":true,"expected_content_hash":initial["data"]["content_hash"],
                "expected_body_hash":bodies[0].1}),&ctx);
        assert_eq!(stale["status"], "error");
        // Explicit remapping of transcript-6 changes the authoritative
        // coding hash and produces an unmatched case for the Python 1..6
        // quantitative fixture; no source ID is guessed as a case ID.
        let changed = handler.execute(
            "qualitative.transcript_update",
            &json!({"project_id":project_id.to_string(),"source_id":"transcript-6",
                "case_id":"unknown","confidential":true,"expected_content_hash":hash,
                "expected_body_hash":bodies[5].1}),
            &ctx,
        );
        assert_eq!(changed["status"], "ok", "{changed}");
        assert_ne!(changed["data"]["content_hash"], hash);
        let remapped = handler.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(remapped["status"], "ok", "{remapped}");
        assert!(remapped["data"]["qualitative_cases"]
            .as_array()
            .unwrap()
            .iter()
            .any(|case| case["case_id"] == "unknown"));
        assert!(!remapped["data"]["qualitative_cases"]
            .as_array()
            .unwrap()
            .iter()
            .any(|case| case["case_id"] == "case-6"));
        assert!(!remapped.to_string().contains("private-participant-token"));
        ProjectStore::open(&path)
            .unwrap()
            .connection()
            .execute(
                "UPDATE document_text SET body_hash=?1 WHERE source_id='transcript-1'",
                ["f".repeat(64)],
            )
            .unwrap();
        let tampered = handler.execute(
            "qualitative.mixed_provenance",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(tampered["status"], "error");
        assert!(!tampered.to_string().contains("private-participant-token"));
    }

    #[test]
    fn notebook_autosave_is_revisioned_preview_safe_and_restart_persistent() {
        let root = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let project_path = root.path().join(project_id.to_string());
        ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Notebook".into(),
                question: "What changed?".into(),
                design: "exploratory".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: timestamp(),
            },
        )
        .unwrap();
        let handler = EvidenceHandler::new(root.path().to_path_buf());
        let mut ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "author".into(),
            expected_revision: Some(0),
        };
        let first_args =
            json!({"project_id":project_id.to_string(),"notebook":"Initial observation."});
        let preview = handler.preview("ui.notebook.save", &first_args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            0
        );
        let first = handler.execute("ui.notebook.save", &first_args, &ctx);
        assert_eq!(first["status"], "ok", "{first}");
        assert_eq!(first["data"]["notebook_revision"], 1);
        assert_eq!(first["data"]["autosave_safe"], true);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let second = handler.execute(
            "ui.notebook.save",
            &json!({
                "project_id":project_id.to_string(),
                "notebook":"Initial observation.\n\nFollow-up observation."
            }),
            &ctx,
        );
        assert_eq!(second["status"], "ok", "{second}");
        assert_eq!(second["data"]["notebook_revision"], 2);

        let restarted = EvidenceHandler::new(root.path().to_path_buf());
        let history = restarted.execute(
            "evidence.notebook_history",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        assert_eq!(history["data"]["count"], 2);
        assert_eq!(
            history["data"]["revisions"][0]["body"],
            "Initial observation."
        );
        let exported = restarted.execute(
            "evidence.notebook_export",
            &json!({"project_id":project_id.to_string()}),
            &ctx,
        );
        let text = exported["data"]["text"].as_str().unwrap();
        assert!(text.contains("Saved revision 2"));
        assert!(text.contains("Follow-up observation."));

        let mut stale = ctx.clone();
        stale.request_id = Uuid::new_v4();
        stale.expected_revision = Some(1);
        let stale_result = restarted.execute(
            "ui.notebook.save",
            &json!({"project_id":project_id.to_string(),"notebook":"Stale overwrite"}),
            &stale,
        );
        assert_eq!(stale_result["status"], "error");
        assert!(stale_result["error"]["message"]
            .as_str()
            .unwrap()
            .contains("stale project revision"));

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let unchanged = restarted.execute(
            "ui.notebook.save",
            &json!({
                "project_id":project_id.to_string(),
                "notebook":"Initial observation.\n\nFollow-up observation."
            }),
            &ctx,
        );
        assert_eq!(unchanged["status"], "error");
        assert!(unchanged["error"]["message"]
            .as_str()
            .unwrap()
            .contains("no changes"));
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            2
        );
    }

    #[test]
    fn unknown_operations_and_cross_project_access_fail_closed() {
        let handler = EvidenceHandler::new(PathBuf::from("unused"));
        assert_eq!(
            handler.execute("protocol.create", &json!({}), &context())["status"],
            "error"
        );
        let bad = handler.execute(
            "project.open",
            &json!({"project_id":Uuid::new_v4().to_string()}),
            &context(),
        );
        assert_eq!(bad["status"], "error");
    }
}
