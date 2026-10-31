use super::{
    archive_project, archive_project_encrypted, inspect_schema, migrate_project, restore_archive,
    restore_encrypted_archive, sha256, validate_info, verify_archive, verify_encrypted_archive,
    ArchiveVerification, EncryptedArchiveVerification, ProjectError, ProjectInfo, ProjectStore,
};
use researchweave_core::{Capability, DispatchContext, Effect, OperationHandler};
use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Component, Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};
use uuid::Uuid;

const MAX_TIMELINE_LIMIT: usize = 1_000;
const MAX_TIMELINE_OFFSET: usize = 1_000_000;
const MAX_RECOVERY_SNAPSHOTS: usize = 20;
const MAX_RECOVERY_LABEL_CHARS: usize = 40;
const MAX_RECOVERY_AGE_MINUTES: u64 = 24 * 60 * 30;

enum ProjectLocation {
    WorkspaceRoot(PathBuf),
    Bound { project_id: Uuid, path: PathBuf },
}

pub struct ProjectHandler {
    location: ProjectLocation,
}

impl ProjectHandler {
    pub fn new(workspace_root: impl AsRef<Path>) -> Self {
        Self {
            location: ProjectLocation::WorkspaceRoot(workspace_root.as_ref().to_path_buf()),
        }
    }

    /// Bind project operations to an exact path selected by the trusted host.
    ///
    /// The path is deliberately not accepted through command arguments. This
    /// lets desktop/native hosts preserve an existing user-selected project
    /// location while commands remain scoped only by the project UUID.
    pub fn bound(project_id: Uuid, path: impl AsRef<Path>) -> Result<Self, String> {
        let path = path.as_ref();
        if !path.is_absolute()
            || path.file_name().is_none()
            || path
                .components()
                .any(|component| matches!(component, Component::ParentDir))
        {
            return Err("bound project path must be an absolute normalized directory".into());
        }
        let bound = if path.exists() {
            let metadata =
                fs::symlink_metadata(path).map_err(|_| "bound project path unavailable")?;
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err("bound project path must be a real directory".into());
            }
            path.canonicalize()
                .map_err(|_| "bound project path unavailable")?
        } else {
            path.to_path_buf()
        };
        Ok(Self {
            location: ProjectLocation::Bound {
                project_id,
                path: bound,
            },
        })
    }

    pub fn capabilities() -> Vec<Capability> {
        [
            ("project.create", Effect::LocalWrite),
            ("project.open", Effect::Read),
            ("project.profile", Effect::Read),
            ("project.update_metadata", Effect::LocalWrite),
            ("project.migration_preview", Effect::Read),
            ("project.migrate", Effect::LocalWrite),
            ("project.integrity", Effect::Read),
            ("project.diagnostics", Effect::Read),
            ("project.activity", Effect::Read),
            ("project.timeline", Effect::Read),
            ("project.timeline_export", Effect::Read),
            ("project.archive", Effect::LocalWrite),
            ("project.archive_verify", Effect::Read),
            ("project.restore", Effect::LocalWrite),
            ("project.archive_encrypted", Effect::LocalWrite),
            ("project.archive_encrypted_verify", Effect::Read),
            ("project.restore_encrypted", Effect::LocalWrite),
            ("project.recovery_snapshot", Effect::LocalWrite),
            ("project.recovery_list", Effect::Read),
            ("project.recovery_status", Effect::Read),
            ("project.recovery_journal", Effect::Read),
            ("project.recovery_restore", Effect::LocalWrite),
        ]
        .into_iter()
        .map(|(operation, effect)| {
            Capability::new(
                operation,
                effect,
                json!({
                    "version":"1.0.0",
                    "offline":true,
                    "project_scoped":true,
                    "approval_required":effect.requires_approval(),
                    "revision_guarded":matches!(
                        operation,
                        "project.update_metadata"
                            | "project.migrate"
                            | "project.archive"
                            | "project.archive_encrypted"
                            | "project.recovery_snapshot"
                            | "project.recovery_restore"
                    ),
                    "sensitive_arguments":if operation.contains("encrypted") {
                        json!(["password"])
                    } else {
                        json!([])
                    }
                }),
            )
        })
        .collect()
    }

    fn project_path(
        &self,
        arguments: &Value,
        context: &DispatchContext,
    ) -> Result<PathBuf, String> {
        let argument_id = required_text(arguments, "project_id")?;
        let parsed = Uuid::parse_str(argument_id).map_err(|_| "invalid project id")?;
        if parsed != context.project_id {
            return Err("project scope mismatch".into());
        }
        match &self.location {
            ProjectLocation::WorkspaceRoot(workspace_root) => {
                Ok(workspace_root.join(parsed.to_string()))
            }
            ProjectLocation::Bound { project_id, path } => {
                if *project_id != parsed {
                    return Err("project scope mismatch".into());
                }
                Ok(path.clone())
            }
        }
    }

    fn create_info(
        &self,
        arguments: &Value,
        context: &DispatchContext,
    ) -> Result<ProjectInfo, String> {
        let created_at = OffsetDateTime::now_utc()
            .format(&Rfc3339)
            .map_err(|_| "clock formatting failed")?;
        let info = ProjectInfo {
            id: context.project_id.to_string(),
            title: required_text(arguments, "title")?.to_owned(),
            question: required_text(arguments, "question")?.to_owned(),
            design: required_text(arguments, "design")?.to_owned(),
            locale: arguments
                .get("locale")
                .and_then(Value::as_str)
                .unwrap_or("en")
                .to_owned(),
            privacy: arguments
                .get("privacy")
                .and_then(Value::as_str)
                .unwrap_or("private")
                .to_owned(),
            revision: 0,
            created_at,
        };
        validate_info(&info).map_err(project_error)?;
        Ok(info)
    }

    fn preview_write(
        &self,
        operation: &str,
        arguments: &Value,
        context: &DispatchContext,
    ) -> Result<Value, String> {
        match operation {
            "project.create" => {
                let path = self.project_path(arguments, context)?;
                let info = self.create_info(arguments, context)?;
                if path.exists() {
                    return Err("project already exists".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":info.id,
                    "title":info.title,
                    "privacy":info.privacy,
                    "destination":path,
                    "writes":1
                }))
            }
            "project.update_metadata" => {
                let path = self.project_path(arguments, context)?;
                let expected = context
                    .expected_revision
                    .ok_or("expected project revision required")?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let current = store.info().map_err(project_error)?;
                if current.revision < 0 || expected != current.revision as u64 {
                    return Err("stale project revision".into());
                }
                let updated = metadata_candidate(&current, arguments)?;
                let changed_fields = metadata_changed_fields(&current, &updated);
                if changed_fields.is_empty() {
                    return Err("project metadata unchanged".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":current.id,
                    "project_revision":current.revision,
                    "next_revision":current.revision + 1,
                    "changed_fields":changed_fields,
                    "writes":1
                }))
            }
            "project.migrate" => {
                let path = self.project_path(arguments, context)?;
                enforce_expected_revision(&path, context.expected_revision)?;
                let inspection = inspect_schema(&path).map_err(project_error)?;
                Ok(json!({
                    "preview":true,
                    "inspection":inspection,
                    "writes":inspection.migration_path.len()
                }))
            }
            "project.archive" => {
                let path = self.project_path(arguments, context)?;
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let info = store.info().map_err(project_error)?;
                let destination = archive_destination(arguments)?;
                if destination.exists() {
                    return Err("archive destination already exists".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":info.id,
                    "project_revision":info.revision,
                    "destination":destination,
                    "writes":1
                }))
            }
            "project.restore" => {
                let destination = self.project_path(arguments, context)?;
                if destination.exists() {
                    return Err("restore destination already exists".into());
                }
                let archive = archive_input(arguments)?;
                let verified = verify_archive(&archive).map_err(project_error)?;
                if verified.project_id != context.project_id.to_string() {
                    return Err("archive project scope mismatch".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":verified.project_id,
                    "project_revision":verified.project_revision,
                    "manifest_sha256":verified.manifest_sha256,
                    "destination":destination,
                    "writes":1
                }))
            }
            "project.archive_encrypted" => {
                let path = self.project_path(arguments, context)?;
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let info = store.info().map_err(project_error)?;
                let destination = encrypted_archive_destination(arguments)?;
                encrypted_password(arguments)?;
                if destination.exists() {
                    return Err("archive destination already exists".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":info.id,
                    "project_revision":info.revision,
                    "destination":destination,
                    "encrypted":true,
                    "cipher":"AES-256-GCM",
                    "kdf":"scrypt",
                    "writes":1
                }))
            }
            "project.restore_encrypted" => {
                let destination = self.project_path(arguments, context)?;
                if destination.exists() {
                    return Err("restore destination already exists".into());
                }
                let archive = encrypted_archive_input(arguments)?;
                encrypted_password(arguments)?;
                Ok(json!({
                    "preview":true,
                    "project_id":context.project_id,
                    "archive":archive,
                    "destination":destination,
                    "encrypted":true,
                    "writes":1
                }))
            }
            "project.recovery_snapshot" => {
                let path = self.project_path(arguments, context)?;
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let info = store.info().map_err(project_error)?;
                let label = recovery_label(arguments)?;
                let snapshot = recovery_snapshot_name(info.revision, &label);
                let recovery = recovery_directory(&path, false)?;
                let count = recovery_snapshot_paths(&path)?.len();
                if count >= MAX_RECOVERY_SNAPSHOTS {
                    return Err("recovery snapshot limit reached".into());
                }
                if recovery
                    .as_ref()
                    .is_some_and(|directory| directory.join(&snapshot).exists())
                {
                    return Err("recovery snapshot already exists".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":info.id,
                    "project_revision":info.revision,
                    "label":label,
                    "snapshot":snapshot,
                    "snapshot_count":count,
                    "writes":1
                }))
            }
            "project.recovery_restore" => {
                let path = self.project_path(arguments, context)?;
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let info = store.info().map_err(project_error)?;
                let snapshot = recovery_snapshot_input(&path, arguments)?;
                let verified = verify_archive(&snapshot).map_err(project_error)?;
                if verified.project_id != info.id {
                    return Err("recovery snapshot project scope mismatch".into());
                }
                let destination = recovery_restore_destination(arguments)?;
                if destination.exists() {
                    return Err("recovery restore destination already exists".into());
                }
                Ok(json!({
                    "preview":true,
                    "project_id":verified.project_id,
                    "project_revision":verified.project_revision,
                    "snapshot":snapshot.file_name().and_then(|name| name.to_str()),
                    "manifest_sha256":verified.manifest_sha256,
                    "destination":destination,
                    "writes":1
                }))
            }
            _ => Err("unsupported write preview".into()),
        }
    }

    fn execute_inner(
        &self,
        operation: &str,
        arguments: &Value,
        context: &DispatchContext,
    ) -> Result<Value, String> {
        let path = self.project_path(arguments, context)?;
        match operation {
            "project.create" => {
                if context
                    .expected_revision
                    .is_some_and(|revision| revision != 0)
                {
                    return Err("new project expected revision must be zero".into());
                }
                if let ProjectLocation::WorkspaceRoot(workspace_root) = &self.location {
                    fs::create_dir_all(workspace_root)
                        .map_err(|_| "workspace unavailable".to_owned())?;
                }
                let info = self.create_info(arguments, context)?;
                let store = ProjectStore::create(&path, &info).map_err(project_error)?;
                let persisted = store.info().map_err(project_error)?;
                Ok(json!({"project":persisted,"path":path}))
            }
            "project.open" => {
                let store = ProjectStore::open(&path).map_err(project_error)?;
                Ok(json!({"project":store.info().map_err(project_error)?,"path":path}))
            }
            "project.profile" => profile(&path),
            "project.update_metadata" => update_metadata(&path, arguments, context),
            "project.migration_preview" => Ok(serde_json::to_value(
                inspect_schema(&path).map_err(project_error)?,
            )
            .map_err(|_| "serialization failed")?),
            "project.migrate" => {
                enforce_expected_revision(&path, context.expected_revision)?;
                Ok(
                    serde_json::to_value(migrate_project(&path).map_err(project_error)?)
                        .map_err(|_| "serialization failed")?,
                )
            }
            "project.integrity" => project_integrity(&path),
            "project.diagnostics" => project_diagnostics(&path),
            "project.activity" => project_activity(&path, arguments),
            "project.timeline" => timeline(&path, arguments),
            "project.timeline_export" => {
                let report = timeline(&path, arguments)?;
                let text = serde_json::to_string_pretty(&report)
                    .map_err(|_| "timeline serialization failed")?
                    + "\n";
                Ok(json!({"format":"json","text":text,"verified":true,"total":report["total"]}))
            }
            "project.archive" => {
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let destination = archive_destination(arguments)?;
                let verified = archive_project(&store, &destination).map_err(project_error)?;
                Ok(archive_verification_json(&verified, Some(&destination)))
            }
            "project.archive_verify" => {
                let archive = archive_input(arguments)?;
                let verified = verify_archive(&archive).map_err(project_error)?;
                if verified.project_id != context.project_id.to_string() {
                    return Err("archive project scope mismatch".into());
                }
                Ok(archive_verification_json(&verified, Some(&archive)))
            }
            "project.restore" => {
                if context
                    .expected_revision
                    .is_some_and(|revision| revision != 0)
                {
                    return Err("restore expected revision must be zero".into());
                }
                if path.exists() {
                    return Err("restore destination already exists".into());
                }
                if let ProjectLocation::WorkspaceRoot(workspace_root) = &self.location {
                    fs::create_dir_all(workspace_root)
                        .map_err(|_| "workspace unavailable".to_owned())?;
                }
                let archive = archive_input(arguments)?;
                let preflight = verify_archive(&archive).map_err(project_error)?;
                if preflight.project_id != context.project_id.to_string() {
                    return Err("archive project scope mismatch".into());
                }
                let restored = restore_archive(&archive, &path).map_err(project_error)?;
                Ok(archive_verification_json(&restored, Some(&path)))
            }
            "project.archive_encrypted" => {
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let destination = encrypted_archive_destination(arguments)?;
                let password = encrypted_password(arguments)?;
                let verified = archive_project_encrypted(&store, &destination, password)
                    .map_err(project_error)?;
                Ok(encrypted_archive_verification_json(
                    &verified,
                    Some(&destination),
                ))
            }
            "project.archive_encrypted_verify" => {
                let archive = encrypted_archive_input(arguments)?;
                let password = encrypted_password(arguments)?;
                let verified =
                    verify_encrypted_archive(&archive, password).map_err(project_error)?;
                if verified.project_id != context.project_id.to_string()
                    && verified.project_id != context.project_id.simple().to_string()
                {
                    return Err("archive project scope mismatch".into());
                }
                Ok(encrypted_archive_verification_json(
                    &verified,
                    Some(&archive),
                ))
            }
            "project.restore_encrypted" => {
                if context
                    .expected_revision
                    .is_some_and(|revision| revision != 0)
                {
                    return Err("restore expected revision must be zero".into());
                }
                if path.exists() {
                    return Err("restore destination already exists".into());
                }
                if let ProjectLocation::WorkspaceRoot(workspace_root) = &self.location {
                    fs::create_dir_all(workspace_root)
                        .map_err(|_| "workspace unavailable".to_owned())?;
                }
                let archive = encrypted_archive_input(arguments)?;
                let password = encrypted_password(arguments)?;
                let preflight =
                    verify_encrypted_archive(&archive, password).map_err(project_error)?;
                if preflight.project_id != context.project_id.to_string()
                    && preflight.project_id != context.project_id.simple().to_string()
                {
                    return Err("archive project scope mismatch".into());
                }
                let restored =
                    restore_encrypted_archive(&archive, &path, password).map_err(project_error)?;
                Ok(encrypted_archive_verification_json(&restored, Some(&path)))
            }
            "project.recovery_snapshot" => {
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let info = store.info().map_err(project_error)?;
                let label = recovery_label(arguments)?;
                let existing = recovery_snapshot_paths(&path)?;
                if existing.len() >= MAX_RECOVERY_SNAPSHOTS {
                    return Err("recovery snapshot limit reached".into());
                }
                let recovery = recovery_directory(&path, true)?
                    .ok_or_else(|| "recovery directory unavailable".to_owned())?;
                let snapshot_name = recovery_snapshot_name(info.revision, &label);
                let destination = recovery.join(&snapshot_name);
                if destination.exists() {
                    return Err("recovery snapshot already exists".into());
                }
                let verified = archive_project(&store, &destination).map_err(project_error)?;
                Ok(json!({
                    "kind":"recovery_snapshot",
                    "project_id":verified.project_id,
                    "project_revision":verified.project_revision,
                    "manifest_sha256":verified.manifest_sha256,
                    "files":verified.files,
                    "expanded_bytes":verified.expanded_bytes,
                    "verified":true,
                    "snapshot":snapshot_name,
                    "label":label,
                    "writes":1
                }))
            }
            "project.recovery_list" => recovery_list(&path),
            "project.recovery_journal" => recovery_journal(&path, arguments),
            "project.recovery_status" => recovery_status(&path, arguments),
            "project.recovery_restore" => {
                enforce_expected_revision(&path, context.expected_revision)?;
                let store = ProjectStore::open(&path).map_err(project_error)?;
                let info = store.info().map_err(project_error)?;
                let snapshot = recovery_snapshot_input(&path, arguments)?;
                let verified = verify_archive(&snapshot).map_err(project_error)?;
                if verified.project_id != info.id {
                    return Err("recovery snapshot project scope mismatch".into());
                }
                let destination = recovery_restore_destination(arguments)?;
                if destination.exists() {
                    return Err("recovery restore destination already exists".into());
                }
                let restored = restore_archive(&snapshot, &destination).map_err(project_error)?;
                Ok(json!({
                    "kind":"recovery_restore",
                    "project_id":restored.project_id,
                    "project_revision":restored.project_revision,
                    "manifest_sha256":restored.manifest_sha256,
                    "files":restored.files,
                    "expanded_bytes":restored.expanded_bytes,
                    "verified":true,
                    "snapshot":snapshot.file_name().and_then(|name| name.to_str()),
                    "destination":destination,
                    "writes":1
                }))
            }
            _ => Err("operation not implemented".into()),
        }
    }
}

impl OperationHandler for ProjectHandler {
    fn preview(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        let result = if matches!(
            operation,
            "project.create"
                | "project.update_metadata"
                | "project.migrate"
                | "project.archive"
                | "project.restore"
                | "project.archive_encrypted"
                | "project.restore_encrypted"
                | "project.recovery_snapshot"
                | "project.recovery_restore"
        ) {
            self.preview_write(operation, arguments, context)
        } else {
            self.execute_inner(operation, arguments, context)
        };
        wire(result)
    }

    fn execute(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        wire(self.execute_inner(operation, arguments, context))
    }
}

fn required_text<'a>(arguments: &'a Value, key: &str) -> Result<&'a str, String> {
    arguments
        .get(key)
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| format!("{key} required"))
}

fn optional_metadata_text(arguments: &Value, key: &str, current: &str) -> Result<String, String> {
    match arguments.get(key) {
        None => Ok(current.to_owned()),
        Some(value) => value
            .as_str()
            .filter(|text| !text.trim().is_empty())
            .map(str::to_owned)
            .ok_or_else(|| format!("{key} must be non-empty text")),
    }
}

fn metadata_candidate(current: &ProjectInfo, arguments: &Value) -> Result<ProjectInfo, String> {
    let updated = ProjectInfo {
        id: current.id.clone(),
        title: optional_metadata_text(arguments, "title", &current.title)?,
        question: optional_metadata_text(arguments, "question", &current.question)?,
        design: optional_metadata_text(arguments, "design", &current.design)?,
        locale: optional_metadata_text(arguments, "locale", &current.locale)?,
        privacy: optional_metadata_text(arguments, "privacy", &current.privacy)?,
        revision: current.revision,
        created_at: current.created_at.clone(),
    };
    validate_info(&updated).map_err(project_error)?;
    Ok(updated)
}

fn metadata_changed_fields(current: &ProjectInfo, updated: &ProjectInfo) -> Vec<&'static str> {
    let mut fields = Vec::new();
    if current.title != updated.title {
        fields.push("title");
    }
    if current.question != updated.question {
        fields.push("question");
    }
    if current.design != updated.design {
        fields.push("design");
    }
    if current.locale != updated.locale {
        fields.push("locale");
    }
    if current.privacy != updated.privacy {
        fields.push("privacy");
    }
    fields
}

fn update_metadata(
    path: &Path,
    arguments: &Value,
    context: &DispatchContext,
) -> Result<Value, String> {
    let expected = context
        .expected_revision
        .ok_or("expected project revision required")?;
    let mut store = ProjectStore::open(path).map_err(project_error)?;
    let current = store.info().map_err(project_error)?;
    if current.revision < 0 || expected != current.revision as u64 {
        return Err("stale project revision".into());
    }
    let updated = metadata_candidate(&current, arguments)?;
    let changed_fields = metadata_changed_fields(&current, &updated);
    if changed_fields.is_empty() {
        return Err("project metadata unchanged".into());
    }

    let tx = store.transaction().map_err(project_error)?;
    let request_id = context.request_id.to_string();
    let replay: i64 = tx
        .query_row(
            "SELECT count(*) FROM events WHERE request_id=?1",
            [&request_id],
            |row| row.get(0),
        )
        .map_err(|_| "request replay check failed")?;
    if replay != 0 {
        return Err("request already applied".into());
    }
    let revision: i64 = tx
        .query_row("SELECT revision FROM project", [], |row| row.get(0))
        .map_err(|_| "project unavailable")?;
    if revision < 0 || revision as u64 != expected {
        return Err("stale project revision".into());
    }
    let next = revision.checked_add(1).ok_or("revision overflow")?;
    let now = OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .map_err(|_| "clock formatting failed")?;
    let field_hashes = json!({
        "title":sha256(updated.title.as_bytes()),
        "question":sha256(updated.question.as_bytes()),
        "design":sha256(updated.design.as_bytes()),
        "locale":sha256(updated.locale.as_bytes()),
        "privacy":sha256(updated.privacy.as_bytes())
    });
    let payload = json!({
        "project_id":updated.id,
        "changed_fields":changed_fields,
        "field_sha256":field_hashes
    });
    let payload_json =
        serde_json::to_string(&payload).map_err(|_| "metadata payload serialization failed")?;
    let payload_hash = sha256(payload_json.as_bytes());
    let predecessor: String = tx
        .query_row(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1",
            [],
            |row| row.get(0),
        )
        .unwrap_or_else(|_| "0".repeat(64));
    let event_hash = sha256(
        serde_json::to_vec(&json!([
            next,
            request_id,
            "project.update_metadata",
            context.actor,
            payload_hash,
            predecessor,
            now
        ]))
        .map_err(|_| "event serialization failed")?
        .as_slice(),
    );
    let updated_rows = tx
        .execute(
            "UPDATE project SET title=?1,question=?2,design=?3,locale=?4,privacy=?5,revision=?6 WHERE revision=?7",
            params![
                updated.title,
                updated.question,
                updated.design,
                updated.locale,
                updated.privacy,
                next,
                revision
            ],
        )
        .map_err(|_| "project metadata update failed")?;
    if updated_rows != 1 {
        return Err("stale project revision".into());
    }
    tx.execute(
        "INSERT INTO events(sequence,request_id,operation,actor,payload_json,payload_hash,previous_hash,event_hash,timestamp) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
        params![
            next,
            context.request_id.to_string(),
            "project.update_metadata",
            context.actor,
            payload_json,
            payload_hash,
            predecessor,
            event_hash,
            now
        ],
    )
    .map_err(|_| "project metadata event insertion failed")?;
    tx.commit().map_err(|_| "project metadata commit failed")?;
    let persisted = ProjectStore::open(path)
        .and_then(|store| store.info())
        .map_err(project_error)?;
    Ok(json!({
        "project":persisted,
        "changed_fields":payload["changed_fields"],
        "field_sha256":payload["field_sha256"]
    }))
}

fn project_error(error: ProjectError) -> String {
    error.to_string()
}

fn archive_destination(arguments: &Value) -> Result<PathBuf, String> {
    let destination = PathBuf::from(required_text(arguments, "destination")?);
    if !destination.is_absolute()
        || destination.extension().and_then(|value| value.to_str()) != Some("rwproj")
        || destination.file_name().is_none()
        || destination
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("invalid archive destination".into());
    }
    let parent = destination
        .parent()
        .ok_or_else(|| "invalid archive destination".to_owned())?;
    let metadata =
        fs::symlink_metadata(parent).map_err(|_| "archive destination parent unavailable")?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("archive destination parent unavailable".into());
    }
    Ok(destination)
}

fn archive_input(arguments: &Value) -> Result<PathBuf, String> {
    let archive = PathBuf::from(required_text(arguments, "archive")?);
    if !archive.is_absolute()
        || archive.extension().and_then(|value| value.to_str()) != Some("rwproj")
        || archive.file_name().is_none()
        || archive
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("invalid archive path".into());
    }
    let metadata = fs::symlink_metadata(&archive).map_err(|_| "archive not found")?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("archive not found".into());
    }
    Ok(archive)
}

fn encrypted_archive_destination(arguments: &Value) -> Result<PathBuf, String> {
    let destination = PathBuf::from(required_text(arguments, "destination")?);
    if !destination.is_absolute()
        || !destination
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.ends_with(".rwproj.enc"))
        || destination
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("invalid encrypted archive destination".into());
    }
    let parent = destination
        .parent()
        .ok_or_else(|| "invalid encrypted archive destination".to_owned())?;
    let metadata = fs::symlink_metadata(parent)
        .map_err(|_| "encrypted archive destination parent unavailable")?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("encrypted archive destination parent unavailable".into());
    }
    Ok(destination)
}

fn encrypted_archive_input(arguments: &Value) -> Result<PathBuf, String> {
    let archive = PathBuf::from(required_text(arguments, "archive")?);
    if !archive.is_absolute()
        || !archive
            .file_name()
            .and_then(|name| name.to_str())
            .is_some_and(|name| name.ends_with(".rwproj.enc"))
        || archive
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("invalid encrypted archive path".into());
    }
    let metadata = fs::symlink_metadata(&archive).map_err(|_| "archive not found")?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("archive not found".into());
    }
    Ok(archive)
}

fn encrypted_password(arguments: &Value) -> Result<&str, String> {
    arguments
        .get("password")
        .and_then(Value::as_str)
        .filter(|password| !password.is_empty() && password.len() <= 1024)
        .ok_or_else(|| "encryption password required".into())
}

fn recovery_label(arguments: &Value) -> Result<String, String> {
    let label = arguments
        .get("label")
        .and_then(Value::as_str)
        .unwrap_or("autosave")
        .trim();
    let count = label.chars().count();
    if count == 0 || count > MAX_RECOVERY_LABEL_CHARS {
        return Err("recovery label must contain 1 to 40 characters".into());
    }
    let safe: String = label
        .chars()
        .map(|character| {
            if character.is_alphanumeric() || matches!(character, '-' | '_') {
                character
            } else {
                '-'
            }
        })
        .collect();
    if safe.is_empty() {
        return Err("recovery label has no safe characters".into());
    }
    Ok(safe)
}

fn recovery_snapshot_name(revision: i64, label: &str) -> String {
    format!("{revision:012}-{label}.rwproj")
}

fn recovery_directory(root: &Path, create: bool) -> Result<Option<PathBuf>, String> {
    let directory = root.join(".recovery");
    if !directory.exists() {
        if !create {
            return Ok(None);
        }
        match fs::create_dir(&directory) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(_) => return Err("recovery directory unavailable".into()),
        }
    }
    let metadata = fs::symlink_metadata(&directory)
        .map_err(|_| "recovery directory unavailable".to_owned())?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("recovery directory is unsafe".into());
    }
    Ok(Some(directory))
}

fn recovery_snapshot_paths(root: &Path) -> Result<Vec<PathBuf>, String> {
    let Some(directory) = recovery_directory(root, false)? else {
        return Ok(Vec::new());
    };
    let mut snapshots = Vec::new();
    for entry in fs::read_dir(&directory).map_err(|_| "recovery directory unavailable")? {
        let entry = entry.map_err(|_| "recovery directory unavailable")?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("rwproj") {
            continue;
        }
        let metadata =
            fs::symlink_metadata(&path).map_err(|_| "recovery snapshot metadata unavailable")?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err("recovery snapshot path is unsafe".into());
        }
        snapshots.push(path);
    }
    snapshots.sort_by(|left, right| left.file_name().cmp(&right.file_name()));
    Ok(snapshots)
}

fn recovery_snapshot_input(root: &Path, arguments: &Value) -> Result<PathBuf, String> {
    let snapshot = required_text(arguments, "snapshot")?;
    let candidate = Path::new(snapshot);
    if candidate.components().count() != 1
        || candidate.extension().and_then(|value| value.to_str()) != Some("rwproj")
        || matches!(snapshot, "." | "..")
        || snapshot.contains(['/', '\\'])
        || snapshot.chars().any(char::is_control)
    {
        return Err("invalid recovery snapshot name".into());
    }
    let directory =
        recovery_directory(root, false)?.ok_or_else(|| "recovery snapshot not found".to_owned())?;
    let path = directory.join(candidate);
    let metadata = fs::symlink_metadata(&path).map_err(|_| "recovery snapshot not found")?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("recovery snapshot not found".into());
    }
    Ok(path)
}

fn recovery_restore_destination(arguments: &Value) -> Result<PathBuf, String> {
    let destination = PathBuf::from(required_text(arguments, "destination")?);
    if !destination.is_absolute()
        || destination.file_name().is_none()
        || destination
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("invalid recovery restore destination".into());
    }
    let parent = destination
        .parent()
        .ok_or_else(|| "invalid recovery restore destination".to_owned())?;
    let metadata = fs::symlink_metadata(parent)
        .map_err(|_| "recovery restore parent unavailable".to_owned())?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("recovery restore parent unavailable".into());
    }
    Ok(destination)
}

fn verified_recovery_snapshots(
    root: &Path,
    project_id: &str,
) -> Result<Vec<(PathBuf, ArchiveVerification, u64, SystemTime)>, String> {
    let mut verified = Vec::new();
    for path in recovery_snapshot_paths(root)? {
        let Ok(receipt) = verify_archive(&path) else {
            continue;
        };
        if receipt.project_id != project_id {
            continue;
        }
        let metadata = fs::metadata(&path).map_err(|_| "recovery snapshot metadata unavailable")?;
        let modified = metadata
            .modified()
            .map_err(|_| "recovery snapshot timestamp unavailable")?;
        verified.push((path, receipt, metadata.len(), modified));
    }
    Ok(verified)
}

fn recovery_list(root: &Path) -> Result<Value, String> {
    let store = ProjectStore::open(root).map_err(project_error)?;
    let info = store.info().map_err(project_error)?;
    drop(store);
    let mut snapshots = Vec::new();
    for path in recovery_snapshot_paths(root)? {
        let metadata = fs::metadata(&path).map_err(|_| "recovery snapshot metadata unavailable")?;
        let name = path
            .file_name()
            .and_then(|value| value.to_str())
            .ok_or_else(|| "invalid recovery snapshot name".to_owned())?;
        match verify_archive(&path) {
            Ok(verified) if verified.project_id == info.id => snapshots.push(json!({
                "snapshot":name,
                "ok":true,
                "project_id":verified.project_id,
                "revision":verified.project_revision,
                "bytes":metadata.len(),
                "manifest_sha256":verified.manifest_sha256
            })),
            Ok(_) => snapshots.push(json!({
                "snapshot":name,
                "ok":false,
                "error":"recovery snapshot belongs to another project",
                "bytes":metadata.len()
            })),
            Err(_) => snapshots.push(json!({
                "snapshot":name,
                "ok":false,
                "error":"recovery snapshot verification failed",
                "bytes":metadata.len()
            })),
        }
    }
    Ok(json!({
        "project_id":info.id,
        "snapshots":snapshots,
        "count":snapshots.len(),
        "writes":0,
        "network_queries":0
    }))
}

fn recovery_journal(root: &Path, arguments: &Value) -> Result<Value, String> {
    let (info, events, _) = verified_events(root)?;
    let explicit = arguments.get("after_revision");
    let base_revision = if let Some(value) = explicit {
        let revision = value
            .as_u64()
            .ok_or_else(|| "after_revision must be a non-negative integer".to_owned())?;
        if revision > info.revision as u64 {
            return Err("recovery journal revision is outside project history".into());
        }
        revision as i64
    } else {
        verified_recovery_snapshots(root, &info.id)?
            .into_iter()
            .filter(|(_, verified, _, _)| verified.project_revision <= info.revision)
            .map(|(_, verified, _, _)| verified.project_revision)
            .max()
            .unwrap_or(0)
    };
    let entries: Vec<Value> = events
        .into_iter()
        .filter(|event| {
            event["sequence"]
                .as_i64()
                .is_some_and(|sequence| sequence > base_revision)
        })
        .map(|event| {
            json!({
                "sequence":event["sequence"],
                "request_id":event["request_id"],
                "operation":event["operation"],
                "actor":event["actor"],
                "payload_digest":event["payload_sha256"],
                "predecessor_hash":event["predecessor_sha256"],
                "event_hash":event["event_sha256"],
                "recorded_at":event["timestamp_utc"]
            })
        })
        .collect();
    Ok(json!({
        "project_id":info.id,
        "base_revision":base_revision,
        "current_revision":info.revision,
        "entries":entries,
        "count":entries.len(),
        "all_entries_committed":true,
        "replay_required_for_current_workspace":false,
        "verified":true,
        "network_queries":0,
        "writes":0
    }))
}

fn recovery_status(root: &Path, arguments: &Value) -> Result<Value, String> {
    let store = ProjectStore::open(root).map_err(project_error)?;
    let info = store.info().map_err(project_error)?;
    drop(store);
    let max_age_minutes = match arguments.get("max_age_minutes") {
        Some(value) => value
            .as_u64()
            .filter(|value| (1..=MAX_RECOVERY_AGE_MINUTES).contains(value))
            .ok_or_else(|| "recovery max age must be between 1 minute and 30 days".to_owned())?,
        None => 15,
    };
    let now = match arguments.get("now") {
        Some(value) => {
            let text = value
                .as_str()
                .ok_or_else(|| "recovery clock must be an RFC3339 string".to_owned())?;
            OffsetDateTime::parse(text, &Rfc3339)
                .map_err(|_| "invalid recovery clock timestamp".to_owned())?
        }
        None => OffsetDateTime::now_utc(),
    };
    let latest = verified_recovery_snapshots(root, &info.id)?
        .into_iter()
        .filter(|(_, verified, _, _)| verified.project_revision <= info.revision)
        .max_by(|left, right| {
            left.1
                .project_revision
                .cmp(&right.1.project_revision)
                .then_with(|| left.3.cmp(&right.3))
        });
    let latest_revision = latest
        .as_ref()
        .map(|(_, verified, _, _)| verified.project_revision);
    let age_minutes = latest
        .as_ref()
        .map(|(_, _, _, modified)| {
            let modified_seconds = modified
                .duration_since(UNIX_EPOCH)
                .map_err(|_| "recovery snapshot timestamp unavailable")?
                .as_secs() as i64;
            Ok::<f64, String>((now.unix_timestamp() - modified_seconds) as f64 / 60.0)
        })
        .transpose()?;
    let revision_changed = latest_revision.is_some_and(|revision| revision != info.revision);
    // A clock correction, copied timestamp or future-dated snapshot must not
    // suppress the next recovery checkpoint indefinitely.
    let future_timestamp = age_minutes.is_some_and(|age| age < -5.0);
    let age_due = age_minutes.is_some_and(|age| age >= max_age_minutes as f64);
    let autosave_due = latest.is_none() || revision_changed || age_due || future_timestamp;
    let mut reasons = Vec::new();
    if latest.is_none() {
        reasons.push("no_verified_snapshot");
    }
    if revision_changed {
        reasons.push("project_revision_changed");
    }
    if age_due {
        reasons.push("snapshot_age_exceeded");
    }
    if future_timestamp {
        reasons.push("snapshot_timestamp_in_future");
    }
    let journal = recovery_journal(
        root,
        &json!({"after_revision":latest_revision.unwrap_or(0)}),
    )?;
    let count = journal["count"].as_u64().unwrap_or(0);
    let latest_json = latest.as_ref().map(|(path, verified, bytes, _)| {
        json!({
            "snapshot":path.file_name().and_then(|name| name.to_str()),
            "ok":true,
            "project_id":verified.project_id,
            "revision":verified.project_revision,
            "bytes":bytes,
            "manifest_sha256":verified.manifest_sha256
        })
    });
    Ok(json!({
        "project_id":info.id,
        "current_revision":info.revision,
        "latest_verified_snapshot":latest_json,
        "latest_snapshot_revision":latest_revision,
        "latest_snapshot_age_minutes":age_minutes,
        "max_age_minutes":max_age_minutes,
        "autosave_due":autosave_due,
        "committed_edits_since_snapshot":count,
        "journal":journal["entries"],
        "unsaved_to_recovery_snapshot":count > 0,
        "unsaved_message":if count > 0 {
            format!("{count} committed edit(s) are durable in the current project but are not included in the latest verified recovery snapshot.")
        } else {
            "All committed edits are included in the latest verified recovery snapshot.".to_owned()
        },
        "reasons":reasons,
        "network_queries":0,
        "writes":0,
        "host_must_explicitly_create_snapshot":true
    }))
}

fn archive_verification_json(verified: &ArchiveVerification, path: Option<&Path>) -> Value {
    json!({
        "project_id":verified.project_id,
        "project_revision":verified.project_revision,
        "manifest_sha256":verified.manifest_sha256,
        "files":verified.files,
        "expanded_bytes":verified.expanded_bytes,
        "verified":true,
        "path":path
    })
}

fn encrypted_archive_verification_json(
    verified: &EncryptedArchiveVerification,
    path: Option<&Path>,
) -> Value {
    json!({
        "project_id":verified.project_id,
        "project_revision":verified.project_revision,
        "plaintext_sha256":verified.plaintext_sha256,
        "files":verified.files,
        "encrypted_bytes":verified.encrypted_bytes,
        "encrypted":true,
        "cipher":"AES-256-GCM",
        "kdf":"scrypt",
        "verified":true,
        "path":path
    })
}

fn wire(result: Result<Value, String>) -> Value {
    match result {
        Ok(data) => json!({"data":data}),
        Err(message) => {
            json!({"status":"failed","error":{"code":"INVALID_INPUT","message":message},"data":{}})
        }
    }
}

fn open_read_only_database(root: &Path) -> Result<Connection, String> {
    let database = root.join("data/project.sqlite");
    if !database.is_file() || database.is_symlink() {
        return Err("project not found".into());
    }
    Connection::open_with_flags(
        database,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|_| "project database unavailable".into())
}

fn project_revision_any_schema(root: &Path) -> Result<i64, String> {
    let connection = open_read_only_database(root)?;
    connection
        .query_row("SELECT revision FROM project LIMIT 1", [], |row| row.get(0))
        .map_err(|_| "project revision unavailable".into())
}

fn enforce_expected_revision(root: &Path, expected: Option<u64>) -> Result<(), String> {
    if let Some(expected) = expected {
        let revision = project_revision_any_schema(root)?;
        if revision < 0 || revision as u64 != expected {
            return Err("stale project revision".into());
        }
    }
    Ok(())
}

fn profile(root: &Path) -> Result<Value, String> {
    let connection = open_read_only_database(root)?;
    let exists: Option<i64> = connection
        .query_row(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_profile'",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|_| "profile inspection failed")?;
    if exists.is_none() {
        return Ok(json!({
            "mode":"legacy",
            "stage":"unknown",
            "description":"",
            "tags":[],
            "advanced":{},
            "profile_available":false
        }));
    }
    connection
        .query_row(
            "SELECT mode,stage,description,tags_json,advanced_json,created_at FROM project_profile WHERE singleton=1",
            [],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                ))
            },
        )
        .map_err(|_| "project profile is incomplete".to_owned())
        .and_then(|(mode, stage, description, tags, advanced, created_at)| {
            Ok(json!({
                "mode":mode,
                "stage":stage,
                "description":description,
                "tags":serde_json::from_str::<Value>(&tags).map_err(|_|"invalid profile tags")?,
                "advanced":serde_json::from_str::<Value>(&advanced).map_err(|_|"invalid profile advanced settings")?,
                "created_at":created_at,
                "profile_available":true
            }))
        })
}

fn verified_events(root: &Path) -> Result<(ProjectInfo, Vec<Value>, String), String> {
    let store = ProjectStore::open(root).map_err(project_error)?;
    let info = store.info().map_err(project_error)?;
    let mut statement = store
        .connection()
        .prepare(
            "SELECT sequence,request_id,operation,actor,payload_json,payload_hash,previous_hash,event_hash,timestamp FROM events ORDER BY sequence",
        )
        .map_err(|_| "timeline query failed")?;
    let rows = statement
        .query_map([], |row| {
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
        })
        .map_err(|_| "timeline query failed")?;
    let mut predecessor = "0".repeat(64);
    let mut events = Vec::new();
    for (index, row) in rows.enumerate() {
        let (
            sequence,
            request_id,
            operation,
            actor,
            payload_json,
            payload_hash,
            previous_hash,
            event_hash,
            timestamp,
        ) = row.map_err(|_| "timeline row failed")?;
        let expected_sequence = index as i64 + 1;
        let expected_payload_hash = sha256(payload_json.as_bytes());
        let expected_event_hash = sha256(
            serde_json::to_vec(&json!([
                sequence,
                request_id,
                operation,
                actor,
                expected_payload_hash,
                predecessor,
                timestamp
            ]))
            .map_err(|_| "timeline serialization failed")?
            .as_slice(),
        );
        if sequence != expected_sequence
            || payload_hash != expected_payload_hash
            || previous_hash != predecessor
            || event_hash != expected_event_hash
        {
            return Err("event timeline verification failed".into());
        }
        predecessor = event_hash.clone();
        events.push(json!({
            "sequence":sequence,
            "request_id":request_id,
            "operation":operation,
            "actor":actor,
            "timestamp_utc":timestamp,
            "payload_sha256":payload_hash,
            "predecessor_sha256":previous_hash,
            "event_sha256":event_hash
        }));
    }
    if info.revision != events.len() as i64 {
        return Err("event count differs from project revision".into());
    }
    Ok((info, events, predecessor))
}

fn timeline(root: &Path, arguments: &Value) -> Result<Value, String> {
    let limit = arguments
        .get("limit")
        .and_then(Value::as_u64)
        .unwrap_or(100) as usize;
    let offset = arguments.get("offset").and_then(Value::as_u64).unwrap_or(0) as usize;
    if !(1..=MAX_TIMELINE_LIMIT).contains(&limit) || offset > MAX_TIMELINE_OFFSET {
        return Err("invalid timeline bounds".into());
    }
    let prefix = arguments.get("operation_prefix").and_then(Value::as_str);
    if prefix.is_some_and(|value| value.is_empty() || value.len() > 100) {
        return Err("invalid operation filter".into());
    }
    let (info, events, predecessor) = verified_events(root)?;
    let filtered: Vec<_> = events
        .into_iter()
        .filter(|event| {
            prefix.is_none_or(|prefix| {
                event["operation"]
                    .as_str()
                    .is_some_and(|operation| operation.starts_with(prefix))
            })
        })
        .collect();
    let selected: Vec<_> = filtered.iter().skip(offset).take(limit).cloned().collect();
    Ok(json!({
        "project_id":info.id,
        "revision":info.revision,
        "total":filtered.len(),
        "offset":offset,
        "limit":limit,
        "events":selected,
        "verified":true,
        "last_event_sha256":predecessor,
        "format":"researchweave-timeline-v1"
    }))
}

fn project_integrity(root: &Path) -> Result<Value, String> {
    let (info, events, last_event) = verified_events(root)?;
    let store = ProjectStore::open(root).map_err(project_error)?;
    let mut statement = store
        .connection()
        .prepare("SELECT digest,size FROM objects ORDER BY digest")
        .map_err(|_| "object inventory failed")?;
    let objects = statement
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })
        .map_err(|_| "object inventory failed")?;
    let mut object_count = 0usize;
    let mut object_bytes = 0u64;
    for object in objects {
        let (digest, size) = object.map_err(|_| "object inventory failed")?;
        if digest.len() != 64 || size < 0 {
            return Err("invalid object inventory".into());
        }
        let path = root.join("objects").join(&digest[..2]).join(&digest);
        let metadata = fs::metadata(&path).map_err(|_| "project object missing")?;
        if metadata.len() != size as u64 {
            return Err("project object size mismatch".into());
        }
        let bytes = fs::read(&path).map_err(|_| "project object unreadable")?;
        if sha256(&bytes) != digest {
            return Err("project object hash mismatch".into());
        }
        object_count += 1;
        object_bytes = object_bytes.saturating_add(metadata.len());
    }
    Ok(json!({
        "ok":true,
        "project_id":info.id,
        "revision":info.revision,
        "events":events.len(),
        "objects":object_count,
        "object_bytes":object_bytes,
        "last_event_sha256":last_event
    }))
}

fn project_activity(root: &Path, args: &Value) -> Result<Value, String> {
    let allowed = ["project_id", "limit", "offset", "operation_filter"];
    if args
        .as_object()
        .is_none_or(|o| o.keys().any(|k| !allowed.contains(&k.as_str())))
    {
        return Err("unsupported activity arguments".into());
    }
    let number = |name: &str, default: u64| -> Result<usize, String> {
        args.get(name).map_or(Ok(default as usize), |v| {
            v.as_u64()
                .and_then(|n| usize::try_from(n).ok())
                .ok_or_else(|| format!("invalid {name}"))
        })
    };
    let limit = number("limit", 100)?;
    let offset = number("offset", 0)?;
    if !(1..=500).contains(&limit) || offset > 1000 {
        return Err("invalid activity bounds".into());
    }
    let filter = args
        .get("operation_filter")
        .map(|v| {
            v.as_str()
                .filter(|s| s.len() <= 200)
                .ok_or("invalid operation filter")
        })
        .transpose()?;
    let (info, events, _) = verified_events(root)?;
    let filtered: Vec<_> = events
        .into_iter()
        .filter(|e| filter.is_none_or(|f| f.is_empty() || e["operation"].as_str() == Some(f)))
        .map(|e| {
            json!({
                "sequence":e["sequence"], "request_id":e["request_id"],
                "operation":e["operation"], "timestamp_utc":e["timestamp_utc"],
                "event_sha256":e["event_sha256"],"source":"project_event_chain"
            })
        })
        .collect();
    Ok(json!({"project_id":info.id,"revision":info.revision,
        "total":filtered.len(),"offset":offset,"limit":limit,
        "events":filtered.iter().skip(offset).take(limit).collect::<Vec<_>>(),
        "verified":true,"actor_authenticated":false,
        "limitation":"Project events are local provenance, not authenticated identities; private payloads and changed-field/target details are withheld"}))
}

fn project_diagnostics(root: &Path) -> Result<Value, String> {
    const MAX_FINDINGS: usize = 400;
    let mut findings = Vec::new();
    let mut checked = vec![
        "event_chain",
        "cas_object_hash",
        "document_body_sha256",
        "annotation_anchors",
        "protocol_presence",
    ];
    let mut add = |code: &str, location: &str, recovery: &str| {
        if findings.len() < MAX_FINDINGS {
            findings.push(json!({"code":code,"severity":"error","location":location,
                "message":"Persisted integrity condition failed","recovery":recovery}));
        }
    };
    let (info, events, _) = match verified_events(root) {
        Ok(data) => data,
        Err(_) => {
            let store = ProjectStore::open(root).map_err(project_error)?;
            let info = store.info().map_err(project_error)?;
            add(
                "EVENT_CHAIN_INVALID",
                "project:events",
                "Restore from a verified project backup and review audit history.",
            );
            (info, Vec::new(), String::new())
        }
    };
    let store = ProjectStore::open(root).map_err(project_error)?;
    if project_integrity(root).is_err() {
        add(
            "CAS_OR_EVENT_INTEGRITY",
            "project:objects",
            "Inspect project integrity and recover affected objects from a verified backup.",
        );
    }
    let mut stmt = store
        .connection()
        .prepare("SELECT source_id,body,body_hash FROM document_text ORDER BY source_id")
        .map_err(|_| "document audit unavailable")?;
    let docs = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| "document audit unavailable")?;
    for row in docs {
        let (id, body, hash) = row.map_err(|_| "document audit unavailable")?;
        if sha256(body.as_bytes()) != hash {
            add(
                "DOCUMENT_HASH_MISMATCH",
                &format!("source:{}", sha256(id.as_bytes())),
                "Re-extract source text from its verified object; recheck annotations.",
            );
        }
    }
    let mut stmt=store.connection().prepare(
        "SELECT a.id,a.start,a.end,a.quote,a.body_hash,d.body,d.body_hash FROM qualitative_annotations a JOIN document_text d ON d.source_id=a.source_id ORDER BY a.id")
        .map_err(|_|"annotation audit unavailable")?;
    let annotations = stmt
        .query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, i64>(1)?,
                r.get::<_, i64>(2)?,
                r.get::<_, String>(3)?,
                r.get::<_, String>(4)?,
                r.get::<_, String>(5)?,
                r.get::<_, String>(6)?,
            ))
        })
        .map_err(|_| "annotation audit unavailable")?;
    for row in annotations {
        let (id, start, end, quote, anchor_hash, body, body_hash) =
            row.map_err(|_| "annotation audit unavailable")?;
        let valid = start >= 0
            && end > start
            && usize::try_from(end).is_ok_and(|n| n <= body.chars().count())
            && body
                .chars()
                .skip(start.max(0) as usize)
                .take((end - start).max(0) as usize)
                .collect::<String>()
                == quote
            && sha256(body.as_bytes()) == body_hash
            && anchor_hash == body_hash;
        if !valid {
            add(
                "ANNOTATION_ANCHOR_INVALID",
                &format!("annotation:{}", sha256(id.as_bytes())),
                "Review the anchor against its exact source text revision.",
            );
        }
    }
    let protocols: i64 = store
        .connection()
        .query_row("SELECT count(*) FROM protocols", [], |r| r.get(0))
        .map_err(|_| "protocol audit unavailable")?;
    if protocols == 0 && findings.len() < MAX_FINDINGS {
        findings.push(json!({"code":"PROTOCOL_NOT_RECORDED","severity":"warning","location":"protocol",
            "message":"No persisted protocol version found","recovery":"Record and review a research protocol as applicable."}));
    }
    checked.sort_unstable();
    let errors = findings.iter().filter(|f| f["severity"] == "error").count();
    let warnings = findings
        .iter()
        .filter(|f| f["severity"] == "warning")
        .count();
    Ok(
        json!({"schema_version":1,"project_id":info.id,"project_revision":info.revision,
        "status":if errors>0 {"integrity-issues"} else if warnings>0 {"review-recommended"} else {"no-detected-integrity-issues"},
        "summary":{"errors":errors,"warnings":warnings,"findings_shown":findings.len(),
            "findings_truncated":findings.len()>=MAX_FINDINGS},
        "findings":findings,"checks_run":checked,
        "unavailable_checks":["dataset_rectangularity","scientific_claim_validation","protocol_semantic_completeness","external_source_integrity"],
        "event_count_verified":events.len(),"scientific_certification":false,
        "limitation":"Structural checks only. No scientific, ethics, identity, or external source certification."}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_core::{AuditStore, Authority, Command, CommandRouter};
    use rusqlite::params;
    use std::sync::Arc;

    fn append_verified_test_event(path: &Path, operation: &str) {
        let store = ProjectStore::open(path).unwrap();
        let info = store.info().unwrap();
        let sequence = info.revision + 1;
        let request_id = Uuid::new_v4().to_string();
        let actor = "recovery-test";
        let payload_json = serde_json::to_string(&json!({"synthetic":true})).unwrap();
        let payload_hash = sha256(payload_json.as_bytes());
        let predecessor = if info.revision == 0 {
            "0".repeat(64)
        } else {
            store
                .connection()
                .query_row(
                    "SELECT event_hash FROM events WHERE sequence=?1",
                    [info.revision],
                    |row| row.get::<_, String>(0),
                )
                .unwrap()
        };
        let timestamp = "2026-10-25T12:00:00Z";
        let event_hash = sha256(
            serde_json::to_vec(&json!([
                sequence,
                request_id,
                operation,
                actor,
                payload_hash,
                predecessor,
                timestamp
            ]))
            .unwrap()
            .as_slice(),
        );
        store
            .connection()
            .execute(
                "INSERT INTO events(sequence,request_id,operation,actor,payload_json,payload_hash,previous_hash,event_hash,timestamp) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9)",
                params![
                    sequence,
                    request_id,
                    operation,
                    actor,
                    payload_json,
                    payload_hash,
                    predecessor,
                    event_hash,
                    timestamp
                ],
            )
            .unwrap();
        store
            .connection()
            .execute("UPDATE project SET revision=?1", [sequence])
            .unwrap();
    }

    #[test]
    fn preview_create_is_read_only_then_router_approval_creates_project() {
        let root = tempfile::tempdir().unwrap();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::open(root.path().join("audit.sqlite")).unwrap());
        let mut router = CommandRouter::new(authority, audit);
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let project = Uuid::new_v4();
        let arguments = json!({
            "project_id":project.to_string(),
            "title":"پژوهش",
            "question":"آیا داده‌ها پایدار هستند؟",
            "design":"observational",
            "locale":"fa",
            "privacy":"private"
        });
        let mut preview = Command::new(project, "project.create", arguments.clone());
        preview.preview = true;
        let result = router.dispatch(&preview, None, 11.0).unwrap();
        assert_eq!(result["data"]["preview"], true);
        assert!(!projects.join(project.to_string()).exists());

        let command = Command::new(project, "project.create", arguments);
        let denied = router.dispatch(&command, None, 12.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        let approval = router.issue_approval(&command, 60, 12.0).unwrap();
        let created = router.dispatch(&command, Some(&approval), 13.0).unwrap();
        assert_eq!(created["data"]["project"]["title"], "پژوهش");
        assert!(projects.join(project.to_string()).is_dir());
    }

    #[test]
    fn metadata_update_is_preview_safe_revision_guarded_replay_safe_and_persistent() {
        let root = tempfile::tempdir().unwrap();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let project = Uuid::new_v4();
        let path = projects.join(project.to_string());
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Original title".into(),
                question: "Original question".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-26T00:00:00Z".into(),
            },
        )
        .unwrap();

        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::open(root.path().join("metadata-audit.sqlite")).unwrap());
        let mut router = CommandRouter::new(authority, audit);
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let arguments = json!({
            "project_id":project.to_string(),
            "title":"Revised title",
            "question":"Revised private question",
            "design":"mixed_methods",
            "locale":"fa",
            "privacy":"restricted"
        });
        let mut preview = Command::new(project, "project.update_metadata", arguments.clone());
        preview.preview = true;
        preview.expected_revision = Some(0);
        let previewed = router.dispatch(&preview, None, 1.0).unwrap();
        assert_eq!(previewed["data"]["preview"], true);
        assert_eq!(previewed["data"]["project_revision"], 0);
        assert_eq!(previewed["data"]["next_revision"], 1);
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().revision,
            0
        );

        let mut update = Command::new(project, "project.update_metadata", arguments);
        update.expected_revision = Some(0);
        let denied = router.dispatch(&update, None, 2.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        let approval = router.issue_approval(&update, 60, 2.0).unwrap();
        let applied = router.dispatch(&update, Some(&approval), 3.0).unwrap();
        assert_eq!(applied["data"]["project"]["title"], "Revised title");
        assert_eq!(applied["data"]["project"]["revision"], 1);
        assert_eq!(
            applied["data"]["changed_fields"],
            json!(["title", "question", "design", "locale", "privacy"])
        );

        let reopened = ProjectStore::open(&path).unwrap();
        let info = reopened.info().unwrap();
        assert_eq!(info.title, "Revised title");
        assert_eq!(info.question, "Revised private question");
        assert_eq!(info.design, "mixed_methods");
        assert_eq!(info.locale, "fa");
        assert_eq!(info.privacy, "restricted");
        assert_eq!(info.revision, 1);
        let payload: String = reopened
            .connection()
            .query_row(
                "SELECT payload_json FROM events WHERE sequence=1",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(!payload.contains("Revised title"));
        assert!(!payload.contains("Revised private question"));

        let handler = ProjectHandler::new(&projects);
        let stale_context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: project,
            actor: "test".into(),
            expected_revision: Some(0),
        };
        let stale = handler.execute(
            "project.update_metadata",
            &json!({"project_id":project.to_string(),"title":"Stale overwrite"}),
            &stale_context,
        );
        assert!(stale["error"]["message"]
            .as_str()
            .unwrap()
            .contains("stale project revision"));

        let replay_context = DispatchContext {
            request_id: update.request_id,
            project_id: project,
            actor: update.actor.clone(),
            expected_revision: Some(1),
        };
        let replay = handler.execute(
            "project.update_metadata",
            &json!({"project_id":project.to_string(),"title":"Replay overwrite"}),
            &replay_context,
        );
        assert!(replay["error"]["message"]
            .as_str()
            .unwrap()
            .contains("request already applied"));
        assert_eq!(
            ProjectStore::open(&path).unwrap().info().unwrap().title,
            "Revised title"
        );

        let timeline_context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: project,
            actor: "test".into(),
            expected_revision: None,
        };
        let timeline = handler.execute(
            "project.timeline",
            &json!({"project_id":project.to_string()}),
            &timeline_context,
        );
        assert_eq!(timeline["data"]["total"], 1);
        assert_eq!(
            timeline["data"]["events"][0]["operation"],
            "project.update_metadata"
        );
        assert_eq!(timeline["data"]["revision"], 1);
        let activity_args = json!({"project_id":project.to_string(),"operation_filter":"project.update_metadata","limit":1,"offset":0});
        let activity = handler.execute("project.activity", &activity_args, &timeline_context);
        assert_eq!(activity["data"]["total"], 1);
        assert_eq!(activity["data"]["actor_authenticated"], false);
        assert!(!activity.to_string().contains("Revised title"));
        assert_eq!(
            handler.execute(
                "project.activity",
                &json!({"project_id":project.to_string(),"operation_filter":"project.open"}),
                &timeline_context
            )["data"]["total"],
            0
        );
        assert!(handler
            .execute(
                "project.activity",
                &json!({"project_id":project.to_string(),"limit":501}),
                &timeline_context
            )
            .get("error")
            .is_some());
        assert!(handler
            .execute(
                "project.activity",
                &json!({"project_id":project.to_string(),"offset":1001}),
                &timeline_context
            )
            .get("error")
            .is_some());
        let diagnostics = handler.execute(
            "project.diagnostics",
            &json!({"project_id":project.to_string()}),
            &timeline_context,
        );
        assert_eq!(diagnostics["data"]["scientific_certification"], false);
        assert!(!diagnostics.to_string().contains("Revised title"));
        let reopened = ProjectHandler::new(&projects);
        assert_eq!(
            reopened.execute("project.activity", &activity_args, &timeline_context),
            activity
        );
        // A checksum-breaking mutation of persisted event data must never
        // appear as a verified activity record or a clean diagnostic.
        ProjectStore::open(&path)
            .unwrap()
            .connection()
            .execute("UPDATE events SET payload_json='private token payload'", [])
            .unwrap();
        let corrupt_activity =
            reopened.execute("project.activity", &activity_args, &timeline_context);
        assert!(corrupt_activity.get("error").is_some());
        let corrupt_diagnostics = reopened.execute(
            "project.diagnostics",
            &json!({"project_id":project.to_string()}),
            &timeline_context,
        );
        assert_eq!(
            corrupt_diagnostics["data"]["scientific_certification"],
            false
        );
        assert!(corrupt_diagnostics["data"]["findings"]
            .as_array()
            .unwrap()
            .iter()
            .any(|issue| issue["code"] == "EVENT_CHAIN_INVALID"));
        assert!(!corrupt_diagnostics
            .to_string()
            .contains("private token payload"));
    }

    #[test]
    fn profile_integrity_timeline_and_current_migration_are_read_only_or_noop() {
        let root = tempfile::tempdir().unwrap();
        let project = Uuid::new_v4();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let path = projects.join(project.to_string());
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Study".into(),
                question: "Question".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();
        let handler = ProjectHandler::new(&projects);
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: project,
            actor: "test".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":project.to_string()});
        let profile = handler.execute("project.profile", &args, &context);
        assert_eq!(profile["data"]["profile_available"], false);
        let integrity = handler.execute("project.integrity", &args, &context);
        assert_eq!(integrity["data"]["ok"], true);
        let timeline = handler.execute("project.timeline", &args, &context);
        assert_eq!(timeline["data"]["verified"], true);
        assert_eq!(timeline["data"]["total"], 0);
        let migration = handler.preview("project.migrate", &args, &context);
        assert_eq!(migration["data"]["inspection"]["compatibility"], "current");
        assert!(!migration["data"]["preview"].is_null());
    }

    #[test]
    fn host_bound_handler_preserves_exact_project_path_and_router_authority() {
        let root = tempfile::tempdir().unwrap();
        let exact = root.path().join("Human Selected Folder");
        let project = Uuid::new_v4();
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::open(root.path().join("host-audit.sqlite")).unwrap());
        let mut router = CommandRouter::new(authority, Arc::clone(&audit));
        router
            .register(
                "project",
                Arc::new(ProjectHandler::bound(project, &exact).unwrap()),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let arguments = json!({
            "project_id":project.to_string(),
            "title":"Exact path پژوهش",
            "question":"Does host binding preserve the chosen folder?",
            "design":"observational",
            "locale":"en",
            "privacy":"private"
        });
        let command = Command::new(project, "project.create", arguments);
        let denied = router.dispatch(&command, None, 1.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        assert!(!exact.exists());
        let approval = router.issue_approval(&command, 60, 1.0).unwrap();
        let created = router.dispatch(&command, Some(&approval), 2.0).unwrap();
        assert_eq!(created["data"]["path"], exact.to_string_lossy().as_ref());
        assert_eq!(created["data"]["project"]["id"], project.to_string());
        assert!(exact.join("data/project.sqlite").is_file());

        let open = Command::new(
            project,
            "project.open",
            json!({"project_id":project.to_string()}),
        );
        let reopened = router.dispatch(&open, None, 3.0).unwrap();
        assert_eq!(reopened["data"]["project"]["title"], "Exact path پژوهش");
        let records = audit.events().unwrap();
        assert_eq!(records.len(), 3);
        assert_eq!(records[0].status, "failed");
        assert_eq!(records[1].operation, "project.create");
        assert_eq!(records[2].operation, "project.open");
    }

    #[test]
    fn archive_export_is_approved_verified_and_project_scoped() {
        let root = tempfile::tempdir().unwrap();
        let project = Uuid::new_v4();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let path = projects.join(project.to_string());
        ProjectStore::create(
            &path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Archive پژوهش".into(),
                question: "Can this project round-trip safely?".into(),
                design: "observational".into(),
                locale: "fa".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();

        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let mut router = CommandRouter::new(Arc::clone(&authority), Arc::clone(&audit));
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();

        let destination = root.path().join("portable.rwproj");
        let arguments = json!({
            "project_id": project.to_string(),
            "destination": destination
        });
        let mut preview = Command::new(project, "project.archive", arguments.clone());
        preview.preview = true;
        preview.expected_revision = Some(0);
        let planned = router.dispatch(&preview, None, 1.0).unwrap();
        assert_eq!(planned["data"]["preview"], true);
        assert!(!destination.exists());

        let mut export = Command::new(project, "project.archive", arguments);
        export.expected_revision = Some(0);
        let denied = router.dispatch(&export, None, 2.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        assert!(!destination.exists());
        let approval = router.issue_approval(&export, 60, 2.0).unwrap();
        let archived = router.dispatch(&export, Some(&approval), 3.0).unwrap();
        assert_eq!(archived["data"]["verified"], true);
        assert_eq!(archived["data"]["project_id"], project.to_string());
        assert_eq!(archived["data"]["project_revision"], 0);
        assert!(destination.is_file());

        let verify = Command::new(
            project,
            "project.archive_verify",
            json!({
                "project_id": project.to_string(),
                "archive": destination
            }),
        );
        let verified = router.dispatch(&verify, None, 4.0).unwrap();
        assert_eq!(
            verified["data"]["manifest_sha256"],
            archived["data"]["manifest_sha256"]
        );

        let other = Uuid::new_v4();
        let cross_project = Command::new(
            other,
            "project.archive_verify",
            json!({
                "project_id": other.to_string(),
                "archive": root.path().join("portable.rwproj")
            }),
        );
        let rejected = router.dispatch(&cross_project, None, 5.0).unwrap();
        assert_eq!(rejected["status"], "failed");
        assert!(rejected["error"]["message"]
            .as_str()
            .unwrap()
            .contains("project scope mismatch"));

        let records = audit.events().unwrap();
        assert_eq!(records.len(), 5);
        assert!(records.iter().all(|record| record.input_sha256.len() == 64));
    }

    #[test]
    fn restore_imports_verified_archive_into_new_workspace_without_overwrite() {
        let source_root = tempfile::tempdir().unwrap();
        let source_projects = source_root.path().join("projects");
        fs::create_dir(&source_projects).unwrap();
        let project = Uuid::new_v4();
        let source = source_projects.join(project.to_string());
        let store = ProjectStore::create(
            &source,
            &ProjectInfo {
                id: project.to_string(),
                title: "Portable study".into(),
                question: "Can another device reopen this?".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();
        let archive = source_root.path().join("portable.rwproj");
        archive_project(&store, &archive).unwrap();
        drop(store);

        let destination_root = tempfile::tempdir().unwrap();
        let destination_projects = destination_root.path().join("projects");
        fs::create_dir(&destination_projects).unwrap();
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let mut router = CommandRouter::new(authority, audit);
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&destination_projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let arguments = json!({
            "project_id":project.to_string(),
            "archive":archive
        });
        let mut preview = Command::new(project, "project.restore", arguments.clone());
        preview.preview = true;
        preview.expected_revision = Some(0);
        let planned = router.dispatch(&preview, None, 1.0).unwrap();
        assert_eq!(planned["data"]["preview"], true);
        assert!(!destination_projects.join(project.to_string()).exists());

        let mut restore = Command::new(project, "project.restore", arguments);
        restore.expected_revision = Some(0);
        let denied = router.dispatch(&restore, None, 2.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        let approval = router.issue_approval(&restore, 60, 2.0).unwrap();
        let imported = router.dispatch(&restore, Some(&approval), 3.0).unwrap();
        assert_eq!(imported["data"]["verified"], true);
        let restored_path = destination_projects.join(project.to_string());
        assert_eq!(
            ProjectStore::open(&restored_path)
                .unwrap()
                .info()
                .unwrap()
                .title,
            "Portable study"
        );

        let replay_attempt = Command::new(
            project,
            "project.restore",
            json!({
                "project_id":project.to_string(),
                "archive":source_root.path().join("portable.rwproj")
            }),
        );
        let second = router.dispatch(&replay_attempt, None, 4.0).unwrap();
        assert_eq!(second["error"]["code"], "NEEDS_APPROVAL");
        let second_approval = router.issue_approval(&replay_attempt, 60, 4.0).unwrap();
        let refused = router
            .dispatch(&replay_attempt, Some(&second_approval), 5.0)
            .unwrap();
        assert_eq!(refused["status"], "failed");
        assert!(refused["error"]["message"]
            .as_str()
            .unwrap()
            .contains("already exists"));
    }

    #[test]
    fn recovery_snapshot_list_restore_and_corruption_are_fail_closed() {
        let root = tempfile::tempdir().unwrap();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let project = Uuid::new_v4();
        let project_path = projects.join(project.to_string());
        ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Recovery پژوهش".into(),
                question: "Can a verified local snapshot recover this project?".into(),
                design: "observational".into(),
                locale: "fa".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let mut router = CommandRouter::new(authority, audit);
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let base = json!({"project_id":project.to_string()});

        let status = router
            .dispatch(
                &Command::new(project, "project.recovery_status", base.clone()),
                None,
                1.0,
            )
            .unwrap();
        assert_eq!(status["data"]["autosave_due"], true);
        assert_eq!(status["data"]["reasons"], json!(["no_verified_snapshot"]));
        assert!(!project_path.join(".recovery").exists());

        let arguments = json!({
            "project_id":project.to_string(),
            "label":"checkpoint پژوهش"
        });
        let mut preview = Command::new(project, "project.recovery_snapshot", arguments.clone());
        preview.preview = true;
        preview.expected_revision = Some(0);
        let planned = router.dispatch(&preview, None, 2.0).unwrap();
        assert_eq!(planned["data"]["preview"], true);
        assert!(!project_path.join(".recovery").exists());

        let mut snapshot = Command::new(project, "project.recovery_snapshot", arguments);
        snapshot.expected_revision = Some(0);
        let denied = router.dispatch(&snapshot, None, 3.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        let approval = router.issue_approval(&snapshot, 60, 3.0).unwrap();
        let saved = router.dispatch(&snapshot, Some(&approval), 4.0).unwrap();
        assert_eq!(saved["data"]["verified"], true);
        assert_eq!(saved["data"]["project_revision"], 0);
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            0
        );
        let snapshot_name = saved["data"]["snapshot"].as_str().unwrap().to_owned();

        let listed = router
            .dispatch(
                &Command::new(project, "project.recovery_list", base.clone()),
                None,
                5.0,
            )
            .unwrap();
        assert_eq!(listed["data"]["count"], 1);
        assert_eq!(listed["data"]["snapshots"][0]["ok"], true);

        let restored = root.path().join("recovered-copy");
        let restore_args = json!({
            "project_id":project.to_string(),
            "snapshot":snapshot_name,
            "destination":restored
        });
        let mut restore = Command::new(project, "project.recovery_restore", restore_args);
        restore.expected_revision = Some(0);
        let restore_approval = router.issue_approval(&restore, 60, 6.0).unwrap();
        let receipt = router
            .dispatch(&restore, Some(&restore_approval), 7.0)
            .unwrap();
        assert_eq!(receipt["data"]["verified"], true);
        assert_eq!(
            ProjectStore::open(&restored).unwrap().info().unwrap().title,
            "Recovery پژوهش"
        );

        let archive = project_path
            .join(".recovery")
            .join(saved["data"]["snapshot"].as_str().expect("snapshot name"));
        let bytes = fs::read(&archive).unwrap();
        fs::write(&archive, &bytes[..bytes.len() / 2]).unwrap();
        let corrupted = router
            .dispatch(
                &Command::new(project, "project.recovery_list", base),
                None,
                8.0,
            )
            .unwrap();
        assert_eq!(corrupted["data"]["snapshots"][0]["ok"], false);
    }

    #[test]
    fn recovery_status_and_journal_track_committed_edits_after_snapshot() {
        let root = tempfile::tempdir().unwrap();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let project = Uuid::new_v4();
        let project_path = projects.join(project.to_string());
        ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Recovery status".into(),
                question: "Which durable edits are outside the snapshot?".into(),
                design: "exploratory".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let mut router = CommandRouter::new(authority, audit);
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let first_args = json!({"project_id":project.to_string(),"label":"autosave"});
        let mut first = Command::new(project, "project.recovery_snapshot", first_args);
        first.expected_revision = Some(0);
        let approval = router.issue_approval(&first, 60, 1.0).unwrap();
        router.dispatch(&first, Some(&approval), 2.0).unwrap();

        append_verified_test_event(&project_path, "evidence.note");
        let base = json!({"project_id":project.to_string()});
        let journal = router
            .dispatch(
                &Command::new(project, "project.recovery_journal", base.clone()),
                None,
                3.0,
            )
            .unwrap();
        assert_eq!(journal["data"]["base_revision"], 0);
        assert_eq!(journal["data"]["current_revision"], 1);
        assert_eq!(journal["data"]["count"], 1);
        assert_eq!(journal["data"]["entries"][0]["operation"], "evidence.note");
        assert_eq!(
            journal["data"]["entries"][0]["predecessor_hash"],
            "0".repeat(64)
        );

        let status = router
            .dispatch(
                &Command::new(project, "project.recovery_status", base.clone()),
                None,
                4.0,
            )
            .unwrap();
        assert_eq!(status["data"]["autosave_due"], true);
        assert_eq!(status["data"]["committed_edits_since_snapshot"], 1);
        assert_eq!(status["data"]["unsaved_to_recovery_snapshot"], true);
        assert!(status["data"]["reasons"]
            .as_array()
            .unwrap()
            .iter()
            .any(|reason| reason == "project_revision_changed"));
        assert_eq!(
            ProjectStore::open(&project_path)
                .unwrap()
                .info()
                .unwrap()
                .revision,
            1
        );

        let stale_args = json!({"project_id":project.to_string(),"label":"stale"});
        let mut stale = Command::new(project, "project.recovery_snapshot", stale_args);
        stale.expected_revision = Some(0);
        let stale_approval = router.issue_approval(&stale, 60, 5.0).unwrap();
        let rejected = router.dispatch(&stale, Some(&stale_approval), 6.0).unwrap();
        assert_eq!(rejected["status"], "failed");
        assert!(rejected["error"]["message"]
            .as_str()
            .unwrap()
            .contains("stale project revision"));

        let fresh_args = json!({"project_id":project.to_string(),"label":"revision-1"});
        let mut fresh = Command::new(project, "project.recovery_snapshot", fresh_args);
        fresh.expected_revision = Some(1);
        let fresh_approval = router.issue_approval(&fresh, 60, 7.0).unwrap();
        router.dispatch(&fresh, Some(&fresh_approval), 8.0).unwrap();
        let current = router
            .dispatch(
                &Command::new(project, "project.recovery_status", base.clone()),
                None,
                9.0,
            )
            .unwrap();
        assert_eq!(current["data"]["autosave_due"], false);
        assert_eq!(current["data"]["committed_edits_since_snapshot"], 0);

        let aged = router
            .dispatch(
                &Command::new(
                    project,
                    "project.recovery_status",
                    json!({
                        "project_id":project.to_string(),
                        "now":"2030-01-01T00:00:00Z",
                        "max_age_minutes":30
                    }),
                ),
                None,
                10.0,
            )
            .unwrap();
        assert_eq!(aged["data"]["autosave_due"], true);
        assert!(aged["data"]["reasons"]
            .as_array()
            .unwrap()
            .iter()
            .any(|reason| reason == "snapshot_age_exceeded"));

        // Snapshot filesystem timestamps can be ahead of the trusted clock
        // after a clock correction or copied recovery folder. Force another
        // checkpoint rather than treating it as permanently fresh.
        let future = router
            .dispatch(
                &Command::new(
                    project,
                    "project.recovery_status",
                    json!({
                        "project_id":project.to_string(),
                        "now":"2000-01-01T00:00:00Z",
                        "max_age_minutes":30
                    }),
                ),
                None,
                11.0,
            )
            .unwrap();
        assert_eq!(future["data"]["autosave_due"], true);
        assert_eq!(future["data"]["committed_edits_since_snapshot"], 0);
        assert!(future["data"]["reasons"]
            .as_array()
            .unwrap()
            .iter()
            .any(|reason| reason == "snapshot_timestamp_in_future"));
    }

    #[test]
    fn encrypted_archive_commands_require_approval_and_never_echo_password() {
        let root = tempfile::tempdir().unwrap();
        let projects = root.path().join("projects");
        fs::create_dir(&projects).unwrap();
        let project = Uuid::new_v4();
        let project_path = projects.join(project.to_string());
        ProjectStore::create(
            &project_path,
            &ProjectInfo {
                id: project.to_string(),
                title: "Encrypted study".into(),
                question: "Can the archive stay private?".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let mut router = CommandRouter::new(authority, Arc::clone(&audit));
        router
            .register(
                "project",
                Arc::new(ProjectHandler::new(&projects)),
                ProjectHandler::capabilities(),
            )
            .unwrap();
        let destination = root.path().join("private.rwproj.enc");
        let password = "archive compatibility password";
        let arguments = json!({
            "project_id":project.to_string(),
            "destination":destination,
            "password":password
        });
        let mut preview = Command::new(project, "project.archive_encrypted", arguments.clone());
        preview.preview = true;
        preview.expected_revision = Some(0);
        let planned = router.dispatch(&preview, None, 1.0).unwrap();
        assert_eq!(planned["data"]["encrypted"], true);
        assert!(!planned.to_string().contains(password));
        assert!(!destination.exists());

        let mut export = Command::new(project, "project.archive_encrypted", arguments);
        export.expected_revision = Some(0);
        let denied = router.dispatch(&export, None, 2.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        let approval = router.issue_approval(&export, 60, 2.0).unwrap();
        let archived = router.dispatch(&export, Some(&approval), 3.0).unwrap();
        assert_eq!(archived["data"]["encrypted"], true);
        assert_eq!(archived["data"]["verified"], true);
        assert!(!archived.to_string().contains(password));
        assert!(destination.is_file());

        let verify = Command::new(
            project,
            "project.archive_encrypted_verify",
            json!({
                "project_id":project.to_string(),
                "archive":destination,
                "password":password
            }),
        );
        let verified = router.dispatch(&verify, None, 4.0).unwrap();
        assert_eq!(verified["data"]["verified"], true);
        assert!(!verified.to_string().contains(password));
        let audit_text = format!("{:?}", audit.events().unwrap());
        assert!(!audit_text.contains(password));
        assert!(ProjectHandler::capabilities().iter().any(|capability| {
            capability.operation == "project.archive_encrypted"
                && capability.manifest["sensitive_arguments"] == json!(["password"])
        }));
    }
}
