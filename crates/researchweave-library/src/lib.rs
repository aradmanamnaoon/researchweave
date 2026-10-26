//! Offline project-scoped source ingest and literal search against the shared project schema.
use chrono::{SecondsFormat, Utc};
use researchweave_core::{Capability, DispatchContext, Effect, OperationHandler};
use researchweave_project::ProjectStore;
use rusqlite::{params, OptionalExtension};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Component, Path, PathBuf},
};
use uuid::Uuid;
mod bibliography;
mod collections;
mod references;
mod relations;

const MAX_TEXT_BYTES: usize = 4 * 1024 * 1024;
const MAX_READ_CHARS: usize = 32_000;

enum LibraryLocation {
    WorkspaceRoot(PathBuf),
    Bound { project_id: Uuid, path: PathBuf },
}

pub struct LibraryHandler {
    location: LibraryLocation,
}

impl LibraryHandler {
    pub fn new(workspace: PathBuf) -> Self {
        Self {
            location: LibraryLocation::WorkspaceRoot(workspace),
        }
    }

    /// Bind library operations to one exact project path selected by the trusted host.
    ///
    /// Filesystem paths are intentionally not command arguments: commands stay
    /// UUID-scoped while desktop/native hosts can support arbitrary project folder names.
    pub fn bound(project_id: Uuid, path: impl AsRef<Path>) -> Result<Self, String> {
        let path = path.as_ref();
        if !path.is_absolute()
            || path.file_name().is_none()
            || path
                .components()
                .any(|component| matches!(component, Component::ParentDir))
        {
            return Err("bound library path must be an absolute normalized directory".into());
        }
        let metadata = fs::symlink_metadata(path).map_err(|_| "bound library path unavailable")?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err("bound library path must be a real project directory".into());
        }
        let path = path
            .canonicalize()
            .map_err(|_| "bound library path unavailable")?;
        Ok(Self {
            location: LibraryLocation::Bound { project_id, path },
        })
    }

    pub fn capabilities() -> Vec<Capability> {
        [
            ("library.source_add", Effect::LocalWrite),
            ("library.list", Effect::Read),
            ("library.source_get", Effect::Read),
            ("source.full_text", Effect::Read),
            ("search.query", Effect::Read),
            ("library.reference_add", Effect::LocalWrite),
            ("library.references", Effect::Read),
            ("library.reference_export", Effect::Read),
            ("library.bibliography_preview", Effect::Read),
            ("library.bibliography_import", Effect::LocalWrite),
            ("library.collection_create", Effect::LocalWrite),
            ("library.collection_tree", Effect::Read),
            ("library.collection_add", Effect::LocalWrite),
            ("library.collection_remove", Effect::LocalWrite),
            ("library.reference_tag", Effect::LocalWrite),
            ("library.collection_search", Effect::Read),
            ("library.collection_export", Effect::Read),
            ("reference.resolve", Effect::Read),
            ("reference.validate", Effect::Read),
            ("reference.merge", Effect::LocalWrite),
            ("reference.unmerge", Effect::LocalWrite),
            ("reference.identity_record", Effect::LocalWrite),
            ("reference.identity_history", Effect::Read),
            ("reference.citation_add", Effect::LocalWrite),
            ("reference.citation_link", Effect::LocalWrite),
            ("reference.citation_revoke", Effect::LocalWrite),
            ("reference.citation_graph", Effect::Read),
            ("reference.citation_graphml", Effect::Read),
        ]
        .into_iter()
        .map(|(op, effect)| {
            Capability::new(
                op,
                effect,
                json!({
                    "project_scoped":true,
                    "effect":effect.as_str(),
                    "approval_required":effect.requires_approval(),
                    "revision_guarded":effect == Effect::LocalWrite,
                    "offline":true
                }),
            )
        })
        .collect()
    }

    fn store(&self, args: &Value, context: &DispatchContext) -> Result<ProjectStore, &'static str> {
        let id = args
            .get("project_id")
            .and_then(Value::as_str)
            .ok_or("project_id required")?;
        let parsed = Uuid::parse_str(id).map_err(|_| "invalid project id")?;
        if parsed != context.project_id {
            return Err("project scope mismatch");
        }
        let path = match &self.location {
            LibraryLocation::WorkspaceRoot(workspace) => {
                let root = workspace.canonicalize().map_err(|_| "workspace missing")?;
                let path = workspace
                    .join(parsed.to_string())
                    .canonicalize()
                    .map_err(|_| "project missing")?;
                if !path.starts_with(&root) || path.parent() != Some(root.as_path()) {
                    return Err("unsafe project path");
                }
                path
            }
            LibraryLocation::Bound { project_id, path } => {
                if *project_id != parsed {
                    return Err("project scope mismatch");
                }
                path.clone()
            }
        };
        let store = ProjectStore::open(path).map_err(|_| "project integrity or schema invalid")?;
        if store.info().map_err(|_| "project invalid")?.id != parsed.to_string() {
            return Err("project identity mismatch");
        }
        if !verify_events(&store).map_err(|_| "event timeline invalid")? {
            return Err("event timeline invalid");
        }
        Ok(store)
    }

    fn run(
        &self,
        operation: &str,
        args: &Value,
        ctx: &DispatchContext,
        preview: bool,
    ) -> Result<Value, String> {
        let mut store = self.store(args, ctx).map_err(str::to_owned)?;
        if matches!(
            operation,
            "library.bibliography_preview" | "library.bibliography_import"
        ) {
            return bibliography::run(&mut store, operation, args, ctx, preview);
        }
        if matches!(
            operation,
            "library.reference_add" | "library.references" | "library.reference_export"
        ) {
            return references::run(&mut store, operation, args, ctx, preview);
        }
        if matches!(
            operation,
            "library.collection_create"
                | "library.collection_tree"
                | "library.collection_add"
                | "library.collection_remove"
                | "library.reference_tag"
                | "library.collection_search"
                | "library.collection_export"
        ) {
            return collections::run(&mut store, operation, args, ctx, preview);
        }
        if matches!(
            operation,
            "reference.resolve"
                | "reference.validate"
                | "reference.merge"
                | "reference.unmerge"
                | "reference.identity_record"
                | "reference.identity_history"
                | "reference.citation_add"
                | "reference.citation_link"
                | "reference.citation_revoke"
                | "reference.citation_graph"
                | "reference.citation_graphml"
        ) {
            return relations::run(&mut store, operation, args, ctx, preview);
        }
        match operation {
            "library.source_add" => {
                let title = required(args, "title", 300)?;
                let body = required(args, "text", MAX_TEXT_BYTES)?;
                if body.len() > MAX_TEXT_BYTES {
                    return Err("text exceeds size limit".into());
                }
                let origin = args
                    .get("origin")
                    .and_then(Value::as_str)
                    .unwrap_or("local-input");
                if origin.len() > 300 || origin.chars().any(char::is_control) {
                    return Err("invalid origin".into());
                }
                let media = args
                    .get("media_type")
                    .and_then(Value::as_str)
                    .unwrap_or("text/plain");
                if media != "text/plain" && media != "text/markdown" {
                    return Err("only UTF-8 plain text and Markdown are supported".into());
                }
                let digest = hex::encode(Sha256::digest(body.as_bytes()));
                let id = Uuid::new_v4().to_string();
                let info = store.info().map_err(|_| "project unavailable")?;
                let revision = u64::try_from(info.revision).map_err(|_| "invalid revision")?;
                if ctx.expected_revision != Some(revision) {
                    return Err("expected_revision required and must match current revision".into());
                }
                let duplicate: i64 = store
                    .connection()
                    .query_row(
                        "SELECT count(*) FROM events WHERE request_id=?1",
                        [ctx.request_id.to_string()],
                        |r| r.get(0),
                    )
                    .map_err(|_| "event query failed")?;
                if duplicate != 0 {
                    return Err("request already applied".into());
                }
                if preview {
                    return Ok(
                        json!({"preview":true,"would_import":{"title":title,"media_type":media,"sha256":digest,"bytes":body.len()},"revision":revision}),
                    );
                }
                // Content-addressed objects may remain unreferenced after a failed transaction.
                // All visible SQL entities, revision and event are committed atomically.
                let stored_digest = store
                    .put_object(body.as_bytes())
                    .map_err(|_| "object storage failed")?;
                let tx = store.transaction().map_err(|_| "transaction failed")?;
                let current: i64 = tx
                    .query_row("SELECT revision FROM project", [], |r| r.get(0))
                    .map_err(|_| "revision unavailable")?;
                if current != info.revision {
                    return Err("stale project revision".into());
                }
                let seen: i64 = tx
                    .query_row(
                        "SELECT count(*) FROM events WHERE request_id=?1",
                        [ctx.request_id.to_string()],
                        |r| r.get(0),
                    )
                    .map_err(|_| "replay check failed")?;
                if seen != 0 {
                    return Err("request already applied".into());
                }
                let now = Utc::now().to_rfc3339_opts(SecondsFormat::Micros, true);
                tx.execute("INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted) VALUES (?1,?2,?3,?4,?5,?6,0)",
                    params![id,title,media,stored_digest,now,origin]).map_err(|_| "source insertion failed")?;
                tx.execute("INSERT INTO document_text(source_id,body,extraction_version,body_hash) VALUES (?1,?2,'rust-utf8-v1',?3)",
                    params![id,body,digest]).map_err(|_| "text insertion failed")?;
                let payload = json!({"source_id":id,"content_sha256":digest,"media_type":media});
                let payload_json =
                    serde_json::to_string(&payload).map_err(|_| "payload serialization failed")?;
                let payload_hash = hex::encode(Sha256::digest(payload_json.as_bytes()));
                let previous: String = tx
                    .query_row(
                        "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1",
                        [],
                        |r| r.get(0),
                    )
                    .optional()
                    .map_err(|_| "event lookup failed")?
                    .unwrap_or_else(|| "0".repeat(64));
                let next = current.checked_add(1).ok_or("revision overflow")?;
                let event_bytes = serde_json::to_vec(&json!([
                    next,
                    ctx.request_id.to_string(),
                    operation,
                    ctx.actor,
                    payload_hash,
                    previous,
                    now
                ]))
                .map_err(|_| "event encoding failed")?;
                let event_hash = hex::encode(Sha256::digest(event_bytes));
                tx.execute(
                    "INSERT INTO events VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
                    params![
                        next,
                        ctx.request_id.to_string(),
                        operation,
                        ctx.actor,
                        payload_json,
                        payload_hash,
                        previous,
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
                tx.commit().map_err(|_| "transaction commit failed")?;
                Ok(
                    json!({"source_id":id,"sha256":digest,"characters":body.chars().count(),"revision":next}),
                )
            }
            "library.list" => {
                let limit = bounded(args, "limit", 50, 200)?;
                let offset = bounded_offset(args)?;
                let mut stmt = store.connection().prepare("SELECT id,title,media_type,digest,origin,imported_at FROM sources WHERE deleted=0 ORDER BY imported_at,id LIMIT ?1 OFFSET ?2").map_err(|_| "source query failed")?;
                let rows = stmt.query_map(params![limit,offset], |r| Ok(json!({"source_id":r.get::<_,String>(0)?,"title":r.get::<_,String>(1)?,"media_type":r.get::<_,String>(2)?,"sha256":r.get::<_,String>(3)?,"origin":r.get::<_,String>(4)?,"imported_at":r.get::<_,String>(5)?}))).map_err(|_| "source query failed")?;
                let sources = rows
                    .collect::<Result<Vec<_>, _>>()
                    .map_err(|_| "source read failed")?;
                Ok(json!({"sources":sources,"count":sources.len(),"limit":limit,"offset":offset}))
            }
            "library.source_get" | "source.full_text" => {
                let source_id = required(args, "source_id", 128)?;
                let row: Option<(String,String,String,String,String)> = store.connection().query_row(
                    "SELECT s.title,s.media_type,s.digest,d.body,d.body_hash FROM sources s JOIN document_text d ON d.source_id=s.id WHERE s.id=?1 AND s.deleted=0",
                    [source_id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?,r.get(4)?))
                ).optional().map_err(|_| "source query failed")?;
                let (title, media, digest, body, body_hash) = row.ok_or("source not found")?;
                if hex::encode(Sha256::digest(body.as_bytes())) != body_hash {
                    return Err("document text checksum mismatch".into());
                }
                if operation == "library.source_get" {
                    Ok(
                        json!({"source_id":source_id,"title":title,"media_type":media,"sha256":digest,"characters":body.chars().count()}),
                    )
                } else {
                    let start = bounded_offset(args)? as usize;
                    let count =
                        bounded(args, "limit", MAX_READ_CHARS as i64, MAX_READ_CHARS as i64)?
                            as usize;
                    let text: String = body.chars().skip(start).take(count).collect();
                    Ok(
                        json!({"source_id":source_id,"text":text,"offset":start,"returned_characters":text.chars().count(),"total_characters":body.chars().count(),"truncated":start+text.chars().count()<body.chars().count()}),
                    )
                }
            }
            "search.query" => {
                let query = required(args, "query", 200)?;
                let limit = bounded(args, "limit", 50, 200)?;
                // Deliberately bounded local scan: SQLite LIKE lacks dependable Persian case folding.
                let mut stmt = store.connection().prepare("SELECT s.id,s.title,d.body FROM sources s JOIN document_text d ON d.source_id=s.id WHERE s.deleted=0 ORDER BY s.title,s.id LIMIT 10000").map_err(|_| "search failed")?;
                let rows = stmt
                    .query_map([], |r| {
                        Ok((
                            r.get::<_, String>(0)?,
                            r.get::<_, String>(1)?,
                            r.get::<_, String>(2)?,
                        ))
                    })
                    .map_err(|_| "search failed")?;
                let needle = query.to_lowercase();
                let mut results = Vec::new();
                for row in rows {
                    let (id, title, body) = row.map_err(|_| "search read failed")?;
                    if title.to_lowercase().contains(&needle)
                        || body.to_lowercase().contains(&needle)
                    {
                        results.push(json!({"source_id":id,"title":title,"snippet":body.chars().take(240).collect::<String>()}));
                        if results.len() >= limit as usize {
                            break;
                        }
                    }
                }
                Ok(
                    json!({"records":results,"count":results.len(),"source":"local","remote_queries":0,"scan_cap":10000,"limitations":"Maximum 10000 sources scanned, literal Unicode lowercase substring matching; no semantic or FTS ranking"}),
                )
            }
            _ => Err("unsupported operation".into()),
        }
    }
}

fn verify_events(store: &ProjectStore) -> Result<bool, rusqlite::Error> {
    let mut statement = store.connection().prepare(
        "SELECT sequence,request_id,operation,actor,payload_json,payload_hash,previous_hash,event_hash,timestamp FROM events ORDER BY sequence"
    )?;
    let rows = statement.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
            row.get::<_, String>(6)?,
            row.get::<_, String>(7)?,
            row.get::<_, String>(8)?,
        ))
    })?;
    let mut previous = "0".repeat(64);
    let mut count = 0_i64;
    for row in rows {
        let (
            sequence,
            request_id,
            operation,
            actor,
            payload,
            payload_hash,
            prior,
            event_hash,
            timestamp,
        ) = row?;
        count += 1;
        let computed_payload = hex::encode(Sha256::digest(payload.as_bytes()));
        let bytes = serde_json::to_vec(&json!([
            sequence,
            request_id,
            operation,
            actor,
            computed_payload,
            previous,
            timestamp
        ]))
        .map_err(|_| rusqlite::Error::InvalidQuery)?;
        if sequence != count
            || payload_hash != computed_payload
            || prior != previous
            || event_hash != hex::encode(Sha256::digest(bytes))
        {
            return Ok(false);
        }
        previous = event_hash;
    }
    let revision = store
        .info()
        .map_err(|_| rusqlite::Error::InvalidQuery)?
        .revision;
    Ok(revision == count)
}

fn required<'a>(args: &'a Value, field: &str, max: usize) -> Result<&'a str, String> {
    args.get(field)
        .and_then(Value::as_str)
        .filter(|s| !s.trim().is_empty() && s.len() <= max && !s.contains('\0'))
        .ok_or_else(|| format!("invalid or missing {field}"))
}
fn bounded(args: &Value, field: &str, default: i64, max: i64) -> Result<i64, String> {
    let value = args
        .get(field)
        .map(Value::as_i64)
        .unwrap_or(Some(default))
        .ok_or("invalid limit")?;
    if !(1..=max).contains(&value) {
        return Err(format!("invalid {field}"));
    }
    Ok(value)
}
fn bounded_offset(args: &Value) -> Result<i64, String> {
    let value = args
        .get("offset")
        .map(Value::as_i64)
        .unwrap_or(Some(0))
        .ok_or("invalid offset")?;
    if !(0..=10_000_000).contains(&value) {
        return Err("invalid offset".into());
    }
    Ok(value)
}
impl OperationHandler for LibraryHandler {
    fn preview(&self, operation: &str, args: &Value, context: &DispatchContext) -> Value {
        self.wrap(operation, args, context, true)
    }
    fn execute(&self, operation: &str, args: &Value, context: &DispatchContext) -> Value {
        self.wrap(operation, args, context, false)
    }
}
impl LibraryHandler {
    fn wrap(&self, op: &str, args: &Value, ctx: &DispatchContext, preview: bool) -> Value {
        match self.run(op, args, ctx, preview) {
            Ok(data) => {
                let local_writes: Vec<&str> = if preview {
                    vec![]
                } else {
                    match op {
                        "library.source_add" => {
                            vec!["sources", "document_text", "objects", "events", "project"]
                        }
                        "library.reference_add" => vec!["reference", "events", "project"],
                        "library.bibliography_import" => {
                            vec!["reference", "events", "project"]
                        }
                        "library.collection_create" => {
                            vec!["library_collections", "events", "project"]
                        }
                        "library.collection_add" | "library.collection_remove" => {
                            vec!["collection_members", "events", "project"]
                        }
                        "library.reference_tag" => vec!["reference_tags", "events", "project"],
                        "reference.merge" | "reference.unmerge" => {
                            vec!["reference_alias", "events", "project"]
                        }
                        "reference.identity_record" => {
                            vec!["reference_identity_checks", "events", "project"]
                        }
                        "reference.citation_add" => {
                            vec!["citation_assertions", "events", "project"]
                        }
                        "reference.citation_link" | "reference.citation_revoke" => {
                            vec!["reference_citations", "events", "project"]
                        }
                        _ => vec![],
                    }
                };
                json!({"status":"ok","data":data,"artifacts":[],"provenance":[],"impact":{"local_writes":local_writes,"network_hosts":[],"irreversible":false}})
            }
            Err(message) => {
                json!({"status":"failed","error":{"code":"LIBRARY_ERROR","message":message},"data":{}})
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::{engine::general_purpose::STANDARD, Engine};
    use researchweave_project::ProjectInfo;
    use tempfile::TempDir;

    #[test]
    fn host_bound_handler_supports_arbitrary_project_folder_without_path_arguments() {
        let temp = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let path = temp.path().join("Human readable project folder");
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Bound library".into(),
                question: "Question".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: Utc::now().to_rfc3339(),
            },
        )
        .unwrap();
        let handler = LibraryHandler::bound(project_id, &path).unwrap();
        let ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "desktop-host".into(),
            expected_revision: Some(0),
        };
        let args = json!({
            "project_id":project_id.to_string(),
            "title":"Bound source",
            "text":"Real persisted source text"
        });
        let preview = handler.preview("library.source_add", &args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let inserted = handler.execute("library.source_add", &args, &ctx);
        assert_eq!(inserted["status"], "ok", "{inserted}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            1
        );

        let other = Uuid::new_v4();
        let wrong = DispatchContext {
            project_id: other,
            request_id: Uuid::new_v4(),
            actor: "desktop-host".into(),
            expected_revision: Some(1),
        };
        assert_eq!(
            handler.execute(
                "library.list",
                &json!({"project_id":other.to_string()}),
                &wrong
            )["status"],
            "failed"
        );
    }

    #[test]
    fn reference_registration_preview_replay_cas_and_lossless_export() {
        let (temp, handler, mut ctx, _) = fixture();
        let args = json!({"project_id":ctx.project_id.to_string(),"title":"Cognitive science فارسی","format":"bibtex","raw":"@article{key, title={فارسی}}","authors":["A. Researcher"],"year":2024,"kind":"article","metadata":{"language":"fa"}});
        let path = temp.path().join(ctx.project_id.to_string());
        assert_eq!(
            handler.preview("library.reference_add", &args, &ctx)["status"],
            "ok"
        );
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let created = handler.execute("library.reference_add", &args, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        let rid = created["data"]["reference_id"].as_str().unwrap();
        assert_eq!(
            handler.execute("library.reference_add", &args, &ctx)["status"],
            "failed"
        );
        ctx.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute("library.reference_add", &args, &ctx)["status"],
            "failed"
        );
        let list = handler.execute(
            "library.references",
            &json!({"project_id":ctx.project_id.to_string()}),
            &ctx,
        );
        assert_eq!(list["data"]["references"][0]["authors"][0], "A. Researcher");
        let exported = handler.execute(
            "library.reference_export",
            &json!({"project_id":ctx.project_id.to_string(),"reference_id":rid}),
            &ctx,
        );
        assert_eq!(exported["data"]["raw"], "@article{key, title={فارسی}}");
        assert_eq!(exported["data"]["status"], "unverified");
        let store = ProjectStore::open(path).unwrap();
        assert_eq!(store.info().unwrap().revision, 1);
        assert_eq!(
            store
                .connection()
                .query_row("SELECT count(*) FROM events", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            1
        );
    }

    #[test]
    fn bibliography_preview_import_restart_duplicates_and_fail_closed() {
        let (temp, handler, ctx, _) = fixture();
        let project_id = ctx.project_id.to_string();
        let path = temp.path().join(&project_id);
        let ris = concat!(
            "TY  - JOUR\n",
            "TI  - حافظه و شناخت\n",
            "AU  - A. Researcher\n",
            "PY  - 2026\n",
            "DO  - https://doi.org/10.1234/ABC\n",
            "ER  - \n"
        );
        let ris_args = json!({
            "project_id":project_id,
            "format":"ris",
            "data_base64":STANDARD.encode(ris.as_bytes())
        });

        let preview = handler.execute("library.bibliography_preview", &ris_args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["count"], 1);
        assert_eq!(preview["data"]["records"][0]["title"], "حافظه و شناخت");
        assert_eq!(preview["data"]["records"][0]["doi"], "10.1234/abc");
        assert_eq!(preview["data"]["records"][0]["raw"], ris);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );

        let write_preview = handler.preview("library.bibliography_import", &ris_args, &ctx);
        assert_eq!(write_preview["status"], "ok", "{write_preview}");
        assert_eq!(write_preview["data"]["preview"], true);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );

        let imported = handler.execute("library.bibliography_import", &ris_args, &ctx);
        assert_eq!(imported["status"], "ok", "{imported}");
        assert_eq!(imported["data"]["receipt"]["inserted"], 1);
        assert_eq!(imported["data"]["project_revision"], 1);
        let reference_id = imported["data"]["references"][0]["reference_id"]
            .as_str()
            .unwrap()
            .to_owned();
        assert_eq!(imported["data"]["references"][0]["raw"], ris);

        let replay = handler.execute("library.bibliography_import", &ris_args, &ctx);
        assert_eq!(replay["status"], "failed");
        let mut stale = ctx.clone();
        stale.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute("library.bibliography_import", &ris_args, &stale)["status"],
            "failed"
        );

        let reopened = LibraryHandler::new(temp.path().to_path_buf());
        let mut read_ctx = ctx.clone();
        read_ctx.request_id = Uuid::new_v4();
        read_ctx.expected_revision = Some(1);
        let exported = reopened.execute(
            "library.reference_export",
            &json!({"project_id":project_id,"reference_id":reference_id}),
            &read_ctx,
        );
        assert_eq!(exported["status"], "ok", "{exported}");
        assert_eq!(exported["data"]["raw"], ris);

        let csl = concat!(
            "[{\"title\":\"Memory follow-up فارسی\",",
            "\"author\":[{\"given\":\"Ada\",\"family\":\"Researcher\"}],",
            "\"issued\":{\"date-parts\":[[2026]]},",
            "\"DOI\":\"doi:10.1234/ABC\",\"type\":\"article-journal\"}]"
        );
        let csl_args = json!({
            "project_id":project_id,
            "format":"csl-json",
            "data_base64":STANDARD.encode(csl.as_bytes())
        });
        let duplicate_preview =
            reopened.preview("library.bibliography_import", &csl_args, &read_ctx);
        assert_eq!(duplicate_preview["status"], "ok", "{duplicate_preview}");
        assert_eq!(
            duplicate_preview["data"]["duplicate_suggestions"][0]["candidates"][0]["same_doi"],
            true
        );
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            1
        );

        let imported_csl = reopened.execute("library.bibliography_import", &csl_args, &read_ctx);
        assert_eq!(imported_csl["status"], "ok", "{imported_csl}");
        assert_eq!(imported_csl["data"]["project_revision"], 2);
        assert_eq!(
            imported_csl["data"]["references"][0]["authors"][0],
            "Ada Researcher"
        );
        assert_eq!(imported_csl["data"]["references"][0]["doi"], "10.1234/abc");

        let bibtex = concat!(
            "@article{nested-key,\n",
            "  title={A {Nested} عنوان},\n",
            "  author={First Author and Second Author},\n",
            "  year={2025},\n",
            "  doi={10.5555/BIB}\n",
            "}\n"
        );
        let bibtex_preview = reopened.execute(
            "library.bibliography_preview",
            &json!({
                "project_id":project_id,
                "format":"bibtex",
                "data_base64":STANDARD.encode(bibtex.as_bytes())
            }),
            &read_ctx,
        );
        assert_eq!(bibtex_preview["status"], "ok", "{bibtex_preview}");
        assert_eq!(
            bibtex_preview["data"]["records"][0]["title"],
            "A {Nested} عنوان"
        );
        assert_eq!(
            bibtex_preview["data"]["records"][0]["authors"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        assert_eq!(
            bibtex_preview["data"]["records"][0]["metadata"]["key"],
            "nested-key"
        );

        let malformed = reopened.execute(
            "library.bibliography_preview",
            &json!({
                "project_id":project_id,
                "format":"ris",
                "data_base64":STANDARD.encode(b"TY  - JOUR\nTI - malformed\n")
            }),
            &read_ctx,
        );
        assert_eq!(malformed["status"], "failed");
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
    fn collections_tags_search_export_and_membership_are_revision_guarded() {
        let (temp, handler, mut ctx, _) = fixture();
        let path = temp.path().join(ctx.project_id.to_string());
        let project_id = ctx.project_id.to_string();
        let reference = |title: &str, year: i64| {
            json!({
                "project_id":project_id,
                "title":title,
                "format":"bibtex",
                "raw":format!("@article{{key{year}, title={{{title}}}}}"),
                "authors":["Researcher"],
                "year":year,
                "kind":"article",
                "metadata":{}
            })
        };

        let first = handler.execute(
            "library.reference_add",
            &reference("Memory study", 2024),
            &ctx,
        );
        assert_eq!(first["status"], "ok", "{first}");
        let first_id = first["data"]["reference_id"].as_str().unwrap().to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let second = handler.execute(
            "library.reference_add",
            &reference("Attention study", 2025),
            &ctx,
        );
        assert_eq!(second["status"], "ok", "{second}");
        let second_id = second["data"]["reference_id"].as_str().unwrap().to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let create_args = json!({"project_id":project_id,"name":"Core evidence","parent_id":null});
        let preview = handler.preview("library.collection_create", &create_args, &ctx);
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            2
        );
        let created = handler.execute("library.collection_create", &create_args, &ctx);
        assert_eq!(created["status"], "ok", "{created}");
        let collection_id = created["data"]["collection_id"]
            .as_str()
            .unwrap()
            .to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(3);
        let added = handler.execute(
            "library.collection_add",
            &json!({
                "project_id":project_id,
                "collection_id":collection_id,
                "reference_ids":[first_id,second_id]
            }),
            &ctx,
        );
        assert_eq!(added["status"], "ok", "{added}");

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(4);
        let tagged = handler.execute(
            "library.reference_tag",
            &json!({
                "project_id":project_id,
                "reference_ids":[first_id,second_id],
                "tags":["Neuroscience"]
            }),
            &ctx,
        );
        assert_eq!(tagged["status"], "ok", "{tagged}");
        assert_eq!(tagged["data"]["tags"][0], "neuroscience");

        let tree = handler.execute(
            "library.collection_tree",
            &json!({"project_id":project_id}),
            &ctx,
        );
        assert_eq!(tree["data"]["collections"][0]["member_count"], 2);
        let tagged_search = handler.execute(
            "library.collection_search",
            &json!({
                "project_id":project_id,
                "collection_id":collection_id,
                "tag":"NEUROSCIENCE",
                "year_from":2024,
                "year_to":2025
            }),
            &ctx,
        );
        assert_eq!(tagged_search["data"]["count"], 2, "{tagged_search}");
        let exported = handler.execute(
            "library.collection_export",
            &json!({"project_id":project_id,"collection_id":collection_id}),
            &ctx,
        );
        assert_eq!(exported["data"]["format"], "csv");
        let csv = exported["data"]["text"].as_str().unwrap();
        assert!(csv.contains("Memory study"));
        assert!(csv.contains("Attention study"));

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(5);
        let removed = handler.execute(
            "library.collection_remove",
            &json!({
                "project_id":project_id,
                "collection_id":collection_id,
                "reference_ids":[second_id]
            }),
            &ctx,
        );
        assert_eq!(removed["status"], "ok", "{removed}");
        let remaining = handler.execute(
            "library.collection_search",
            &json!({"project_id":project_id,"collection_id":collection_id}),
            &ctx,
        );
        assert_eq!(remaining["data"]["count"], 1);
        assert_eq!(remaining["data"]["records"][0]["id"], first_id);

        let mut stale = ctx.clone();
        stale.request_id = Uuid::new_v4();
        stale.expected_revision = Some(5);
        let rejected = handler.execute(
            "library.reference_tag",
            &json!({
                "project_id":project_id,
                "reference_ids":[first_id],
                "tags":["stale"]
            }),
            &stale,
        );
        assert_eq!(rejected["status"], "failed");
        let reopened = ProjectStore::open(&path).unwrap();
        assert_eq!(reopened.info().unwrap().revision, 6);
        assert_eq!(
            reopened
                .connection()
                .query_row("SELECT count(*) FROM events", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            6
        );
    }

    #[test]
    fn reference_identity_merge_and_citation_graph_are_reversible_and_anchored() {
        let (temp, handler, mut ctx, source_args) = fixture();
        let project_id = ctx.project_id.to_string();
        let path = temp.path().join(&project_id);
        let reference = |title: &str, doi: &str| {
            json!({
                "project_id":project_id,
                "title":title,
                "format":"bibtex",
                "raw":format!("@article{{key,title={{{title}}},doi={{{doi}}}}}"),
                "authors":["Ada Researcher"],
                "year":2026,
                "doi":doi,
                "kind":"article",
                "metadata":{}
            })
        };
        let first = handler.execute(
            "library.reference_add",
            &reference("Canonical article", "10.1000/example"),
            &ctx,
        );
        assert_eq!(first["status"], "ok", "{first}");
        let first_id = first["data"]["reference_id"].as_str().unwrap().to_owned();
        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(1);
        let second = handler.execute(
            "library.reference_add",
            &reference("Duplicate article", "10.1000/example"),
            &ctx,
        );
        assert_eq!(second["status"], "ok", "{second}");
        let second_id = second["data"]["reference_id"].as_str().unwrap().to_owned();

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(2);
        let merge_args = json!({
            "project_id":project_id,
            "canonical_id":first_id,
            "duplicate_id":second_id,
            "rationale":"Reviewer confirmed duplicate DOI and authors"
        });
        let merge_preview = handler.preview("reference.merge", &merge_args, &ctx);
        assert_eq!(merge_preview["status"], "ok", "{merge_preview}");
        let merged = handler.execute("reference.merge", &merge_args, &ctx);
        assert_eq!(merged["status"], "ok", "{merged}");
        assert_eq!(merged["data"]["reversible"], true);
        let resolved = handler.execute(
            "reference.resolve",
            &json!({"project_id":project_id,"reference_id":second_id}),
            &ctx,
        );
        assert_eq!(resolved["data"]["canonical_id"], first_id);
        assert_eq!(resolved["data"]["is_alias"], true);
        assert_eq!(
            ProjectStore::open(&path)
                .unwrap()
                .connection()
                .query_row("SELECT count(*) FROM reference", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            2
        );

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(3);
        let unmerged = handler.execute(
            "reference.unmerge",
            &json!({
                "project_id":project_id,
                "duplicate_id":second_id,
                "rationale":"Reviewer reconsidered identity decision"
            }),
            &ctx,
        );
        assert_eq!(unmerged["status"], "ok", "{unmerged}");
        assert_eq!(unmerged["data"]["reverted"], true);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(4);
        let identity = handler.execute(
            "reference.identity_record",
            &json!({
                "project_id":project_id,
                "reference_id":first_id,
                "provider":"local-fixture",
                "observed":{
                    "doi":"https://doi.org/10.1000/example",
                    "title":"Canonical article",
                    "year":2026,
                    "authors":["Ada Researcher"]
                }
            }),
            &ctx,
        );
        assert_eq!(identity["status"], "ok", "{identity}");
        assert_eq!(identity["data"]["identity"], "bibliographic_consistency");
        let identity_history = handler.execute(
            "reference.identity_history",
            &json!({"project_id":project_id,"reference_id":first_id}),
            &ctx,
        );
        assert_eq!(
            identity_history["data"]["records"]
                .as_array()
                .unwrap()
                .len(),
            1
        );

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(5);
        let source = handler.execute("library.source_add", &source_args, &ctx);
        assert_eq!(source["status"], "ok", "{source}");
        let source_id = source["data"]["source_id"].as_str().unwrap().to_owned();
        let body = source_args["text"].as_str().unwrap();
        let quote = "Neuroscience";
        let byte_start = body.find(quote).unwrap();
        let start = body[..byte_start].chars().count();
        let end = start + quote.chars().count();
        let anchor_id = Uuid::new_v4().to_string();
        let store = ProjectStore::open(&path).unwrap();
        store
            .connection()
            .execute(
                "INSERT INTO anchors(id,source_id,quote,start,end,page,body_hash,verified)
                 SELECT ?1,source_id,?2,?3,?4,NULL,body_hash,1
                 FROM document_text WHERE source_id=?5",
                params![anchor_id, quote, start as i64, end as i64, source_id],
            )
            .unwrap();
        drop(store);

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(6);
        let linked = handler.execute(
            "reference.citation_link",
            &json!({
                "project_id":project_id,
                "citing_id":first_id,
                "cited_id":second_id,
                "anchor_id":anchor_id,
                "actor":"reviewer",
                "rationale":"Exact imported source passage records this citation"
            }),
            &ctx,
        );
        assert_eq!(linked["status"], "ok", "{linked}");
        assert_eq!(linked["data"]["status"], "human_attested_exact_anchor");
        let edge_id = linked["data"]["id"].as_str().unwrap().to_owned();
        let graph = handler.execute(
            "reference.citation_graph",
            &json!({"project_id":project_id}),
            &ctx,
        );
        assert_eq!(graph["data"]["verified"], true, "{graph}");
        assert_eq!(graph["data"]["active_edges"], 1);
        assert_eq!(graph["data"]["paper_read_inferred"], false);
        let graphml = handler.execute(
            "reference.citation_graphml",
            &json!({"project_id":project_id}),
            &ctx,
        );
        assert_eq!(graphml["status"], "ok", "{graphml}");
        assert!(graphml["data"]["text"]
            .as_str()
            .unwrap()
            .contains("researchweave-citations"));

        ctx.request_id = Uuid::new_v4();
        ctx.expected_revision = Some(7);
        let revoked = handler.execute(
            "reference.citation_revoke",
            &json!({
                "project_id":project_id,
                "edge_id":edge_id,
                "actor":"reviewer",
                "rationale":"Source interpretation was withdrawn"
            }),
            &ctx,
        );
        assert_eq!(revoked["status"], "ok", "{revoked}");
        let active = handler.execute(
            "reference.citation_graph",
            &json!({"project_id":project_id}),
            &ctx,
        );
        assert_eq!(active["data"]["active_edges"], 0);
        let historical = handler.execute(
            "reference.citation_graph",
            &json!({"project_id":project_id,"include_revoked":true}),
            &ctx,
        );
        assert_eq!(historical["data"]["edges"].as_array().unwrap().len(), 1);
        assert!(!historical["data"]["edges"][0]["revoked_at"].is_null());
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            8
        );
    }

    fn fixture() -> (TempDir, LibraryHandler, DispatchContext, Value) {
        let temp = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let id = project_id.to_string();
        ProjectStore::create(
            temp.path().join(&id),
            &ProjectInfo {
                id: id.clone(),
                title: "آزمایش".into(),
                question: "Neuroscience study".into(),
                design: "computational".into(),
                locale: "fa".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: Utc::now().to_rfc3339(),
            },
        )
        .unwrap();
        let ctx = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "test".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":id,"title":"علوم اعصاب","text":"سلام دنیا! Neuroscience and cognition","media_type":"text/plain"});
        let handler = LibraryHandler::new(temp.path().to_path_buf());
        (temp, handler, ctx, args)
    }

    #[test]
    fn preview_import_reopen_search_and_hash_chain() {
        let (temp, handler, ctx, args) = fixture();
        let preview = handler.preview("library.source_add", &args, &ctx);
        assert_eq!(preview["status"], "ok");
        let path = temp.path().join(ctx.project_id.to_string());
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );
        let inserted = handler.execute("library.source_add", &args, &ctx);
        assert_eq!(inserted["status"], "ok");
        assert_eq!(
            handler.execute("library.source_add", &args, &ctx)["status"],
            "failed"
        );
        let mut stale = ctx.clone();
        stale.request_id = Uuid::new_v4();
        assert_eq!(
            handler.execute("library.source_add", &args, &stale)["status"],
            "failed"
        );
        let mut fresh = ctx.clone();
        fresh.expected_revision = Some(1);
        let searched = handler.execute(
            "search.query",
            &json!({"project_id":ctx.project_id.to_string(),"query":"سلام","limit":2}),
            &fresh,
        );
        assert_eq!(searched["data"]["count"], 1);
        let source_id = inserted["data"]["source_id"].as_str().unwrap();
        let read = handler.execute(
            "source.full_text",
            &json!({"project_id":ctx.project_id.to_string(),"source_id":source_id,"limit":5}),
            &fresh,
        );
        assert_eq!(read["data"]["text"], "سلام ");
        let store = ProjectStore::open(&path).unwrap();
        assert_eq!(store.info().unwrap().revision, 1);
        let (payload, hash, previous, event): (String, String, String, String) = store
            .connection()
            .query_row(
                "SELECT payload_json,payload_hash,previous_hash,event_hash FROM events",
                [],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
            )
            .unwrap();
        assert_eq!(hash, hex::encode(Sha256::digest(payload.as_bytes())));
        assert_eq!(previous, "0".repeat(64));
        assert_eq!(event.len(), 64);
    }

    #[test]
    fn rejects_cross_project_and_invalid_limits() {
        let (_temp, handler, ctx, args) = fixture();
        let mut other = args.clone();
        other["project_id"] = json!(Uuid::new_v4().to_string());
        assert_eq!(
            handler.execute("library.list", &other, &ctx)["status"],
            "failed"
        );
        assert_eq!(
            handler.execute(
                "search.query",
                &json!({"project_id":ctx.project_id.to_string(),"query":"x","limit":201}),
                &ctx
            )["status"],
            "failed"
        );
    }

    #[test]
    fn rejects_tampered_event_history() {
        let (temp, handler, ctx, args) = fixture();
        assert_eq!(
            handler.execute("library.source_add", &args, &ctx)["status"],
            "ok"
        );
        let path = temp.path().join(ctx.project_id.to_string());
        let store = ProjectStore::open(path).unwrap();
        store
            .connection()
            .execute("UPDATE events SET actor='attacker'", [])
            .unwrap();
        drop(store);
        assert_eq!(
            handler.execute(
                "library.list",
                &json!({"project_id":ctx.project_id.to_string()}),
                &ctx
            )["status"],
            "failed"
        );
    }
}
