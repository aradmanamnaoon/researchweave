//! Explicit, non-overwriting desktop file delivery for read-only, revision-bound
//! manuscript and draft submission artifacts. This never submits data to a journal.
use super::{evidence_read_at, now_seconds, ProjectStore};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use researchweave_core::{
    AuditStore, Authority, Capability, Command, CommandRouter, DispatchContext, Effect,
    OperationHandler,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Seek, Write},
    path::{Path, PathBuf},
    sync::Arc,
};
use uuid::Uuid;

const MAX_EXPORT_BYTES: usize = 32 * 1024 * 1024;

#[derive(Clone)]
pub(super) struct PreparedPhysicalExport {
    project: PathBuf,
    project_id: String,
    project_revision: i64,
    operation: String,
    arguments: Value,
    sha256: String,
    extension: String,
    length: usize,
}

fn export_extension(operation: &str, arguments: &Value) -> Result<&'static str, String> {
    match operation {
        "writing.manuscript_export" => match arguments["format"].as_str() {
            Some("markdown") => Ok("md"),
            Some("html") => Ok("html"),
            Some("docx") => Ok("docx"),
            Some("pdf") => Ok("pdf"),
            _ => Err("Unsupported manuscript artifact format".into()),
        },
        "writing.submission_export" => Ok("zip"),
        _ => Err("Only manuscript and draft submission artifacts can be saved".into()),
    }
}

fn checked_bytes(receipt: &Value) -> Result<(Vec<u8>, String), String> {
    let data = &receipt["data"];
    let encoded = data["base64"].as_str().ok_or("Artifact has no payload")?;
    // Bounds-check encoded length before allocating decoded bytes.
    if encoded.len() > MAX_EXPORT_BYTES.div_ceil(3) * 4 + 4 {
        return Err("Artifact exceeds the desktop export size limit".into());
    }
    let bytes = STANDARD
        .decode(encoded)
        .map_err(|_| "Artifact contains invalid base64")?;
    if bytes.is_empty() || bytes.len() > MAX_EXPORT_BYTES {
        return Err("Artifact is empty or too large to save".into());
    }
    let size = data["byte_length"]
        .as_u64()
        .ok_or("Artifact receipt has no byte length")?;
    if size != bytes.len() as u64 {
        return Err("Artifact length does not match the receipt".into());
    }
    let digest = data["sha256"]
        .as_str()
        .ok_or("Artifact receipt has no SHA-256")?;
    let actual = hex::encode(Sha256::digest(&bytes));
    if digest != actual {
        return Err("Artifact SHA-256 does not match the receipt".into());
    }
    Ok((bytes, actual))
}

pub(super) fn prepare(
    project: &Path,
    operation: &str,
    arguments: Value,
    root: &Path,
) -> Result<(PreparedPhysicalExport, Value), String> {
    let extension = export_extension(operation, &arguments)?;
    let before = ProjectStore::open(project)
        .map_err(|error| error.to_string())?
        .info()
        .map_err(|error| error.to_string())?;
    let result = evidence_read_at(project, operation, arguments.clone(), root)?;
    let after = ProjectStore::open(project)
        .map_err(|error| error.to_string())?
        .info()
        .map_err(|error| error.to_string())?;
    if before.id != after.id || before.revision != after.revision {
        return Err("Project changed during artifact preparation; prepare again".into());
    }
    let (bytes, sha256) = checked_bytes(&result)?;
    Ok((
        PreparedPhysicalExport {
            project: project.to_path_buf(),
            project_id: before.id,
            project_revision: before.revision,
            operation: operation.to_owned(),
            arguments,
            sha256,
            extension: extension.to_owned(),
            length: bytes.len(),
        },
        result,
    ))
}

/// A trusted, project-bound host capability. The only way to reach the file
/// writer from the desktop is a one-use SensitiveExport grant and audit entry.
struct PhysicalExportHandler {
    pending: PreparedPhysicalExport,
    project: PathBuf,
    root: PathBuf,
    approved_arguments: Value,
}

impl OperationHandler for PhysicalExportHandler {
    fn preview(&self, _: &str, _: &Value, _: &DispatchContext) -> Value {
        json!({"status":"ok","data":{"written_to_disk":false,"submission_performed":false}})
    }

    fn execute(&self, operation: &str, args: &Value, context: &DispatchContext) -> Value {
        if operation != "export.file_save"
            || *args != self.approved_arguments
            || Uuid::parse_str(&self.pending.project_id).ok() != Some(context.project_id)
            || context.expected_revision != u64::try_from(self.pending.project_revision).ok()
        {
            return json!({"status":"failed","error":{"code":"SCOPE_MISMATCH",
                "message":"Export approval does not match project, revision or destination"}});
        }
        let Some(destination) = args["destination"].as_str() else {
            return json!({"status":"failed","error":{"code":"INVALID_INPUT","message":"Missing destination"}});
        };
        match write_verified(&self.pending, &self.project, destination, &self.root) {
            Ok(data) => json!({"status":"ok","data":data}),
            Err(message) => {
                json!({"status":"failed","error":{"code":"EXPORT_FAILED","message":message}})
            }
        }
    }
}

pub(super) fn save(
    pending: &PreparedPhysicalExport,
    active_project: &Path,
    destination: &str,
    root: &Path,
) -> Result<Value, String> {
    let project_id =
        Uuid::parse_str(&pending.project_id).map_err(|_| "Prepared project identity is invalid")?;
    let revision = u64::try_from(pending.project_revision)
        .map_err(|_| "Prepared project revision is invalid")?;
    let canonical_project =
        fs::canonicalize(active_project).map_err(|_| "Active project is unavailable")?;
    let prepared_path =
        fs::canonicalize(&pending.project).map_err(|_| "Prepared project is unavailable")?;
    if canonical_project != prepared_path {
        return Err("Active project changed; prepare an export for this project".into());
    }
    let arguments = json!({
        "destination":destination.trim(),
        "source_operation":pending.operation,
        "source_arguments_sha256":hex::encode(Sha256::digest(
            serde_json::to_vec(&pending.arguments).map_err(|_| "Invalid export arguments")?
        )),
        "artifact_sha256":pending.sha256,
        "project_path_sha256":hex::encode(Sha256::digest(canonical_project.to_string_lossy().as_bytes())),
        "extension":pending.extension,
        "byte_length":pending.length,
    });
    fs::create_dir_all(root).map_err(|error| error.to_string())?;
    let audit = Arc::new(
        AuditStore::open(root.join("operation-audit.sqlite")).map_err(|error| error.to_string())?,
    );
    let mut router = CommandRouter::new(Arc::new(Authority::new()), audit);
    router.register(
        "host-export",
        Arc::new(PhysicalExportHandler {
            pending: pending.clone(),
            project: canonical_project,
            root: root.to_path_buf(),
            approved_arguments: arguments.clone(),
        }),
        [Capability::new("export.file_save", Effect::SensitiveExport,
            json!({"description":"Approved, exact-project and exact-destination non-overwriting physical artifact export"}))],
    ).map_err(|error| error.to_string())?;
    let mut command = Command::new(project_id, "export.file_save", arguments);
    command.actor = "desktop-user".into();
    command.expected_revision = Some(revision);
    // This is invoked only by the explicit Save button, never at preparation.
    let now = now_seconds()?;
    let grant = router
        .issue_approval(&command, 30, now)
        .map_err(|error| error.to_string())?;
    let outcome = router
        .dispatch(&command, Some(&grant), now)
        .map_err(|error| error.to_string())?;
    if outcome["status"] != "ok" {
        return Err(outcome
            .pointer("/error/message")
            .and_then(Value::as_str)
            .unwrap_or("Physical export denied")
            .to_owned());
    }
    Ok(outcome["data"].clone())
}

pub(super) fn save_for_screen(
    pending: &PreparedPhysicalExport,
    active_project: &Path,
    destination: &str,
    root: &Path,
    operation: &str,
) -> Result<Value, String> {
    if pending.operation != operation {
        return Err(
            "The prepared artifact belongs to a different workspace; prepare it here first".into(),
        );
    }
    save(pending, active_project, destination, root)
}

fn write_verified(
    pending: &PreparedPhysicalExport,
    active_project: &Path,
    destination: &str,
    root: &Path,
) -> Result<Value, String> {
    if fs::canonicalize(active_project).map_err(|_| "Active project unavailable")?
        != fs::canonicalize(&pending.project).map_err(|_| "Prepared project unavailable")?
    {
        return Err("Active project changed; prepare an export for this project".into());
    }
    let before = ProjectStore::open(active_project)
        .map_err(|error| error.to_string())?
        .info()
        .map_err(|error| error.to_string())?;
    if before.id != pending.project_id || before.revision != pending.project_revision {
        return Err("Project revision changed after preparation; prepare again".into());
    }
    let target = Path::new(destination.trim());
    if !target.is_absolute() || target.file_name().is_none() {
        return Err("Enter an absolute output file path".into());
    }
    let extension = target.extension().and_then(|part| part.to_str());
    if extension.map(|part| part.eq_ignore_ascii_case(&pending.extension)) != Some(true) {
        return Err(format!(
            "Choose an output filename ending in .{}",
            pending.extension
        ));
    }
    let parent = target.parent().ok_or("Output folder is missing")?;
    if !parent.is_dir() {
        return Err("Output folder must already exist".into());
    }
    // Re-read the authoritative persisted content at the same project revision.
    // The prepared bytes themselves are never written without this revalidation.
    let receipt = evidence_read_at(
        active_project,
        &pending.operation,
        pending.arguments.clone(),
        root,
    )?;
    let (bytes, sha256) = checked_bytes(&receipt)?;
    let after = ProjectStore::open(active_project)
        .map_err(|error| error.to_string())?
        .info()
        .map_err(|error| error.to_string())?;
    if after.id != pending.project_id || after.revision != pending.project_revision {
        return Err("Project changed while revalidating artifact; prepare again".into());
    }
    if sha256 != pending.sha256 || bytes.len() != pending.length {
        return Err("Artifact changed since preparation; prepare again".into());
    }
    let mut output = OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .open(target)
        .map_err(|error| {
            format!("Cannot create output (existing files are never replaced): {error}")
        })?;
    let written = (|| -> Result<(), String> {
        output
            .write_all(&bytes)
            .map_err(|error| error.to_string())?;
        output.sync_all().map_err(|error| error.to_string())?;
        // Verify through our original handle. Re-opening target by pathname
        // would let a concurrent pathname replacement forge verification.
        output.rewind().map_err(|error| error.to_string())?;
        let mut persisted = Vec::with_capacity(bytes.len());
        output
            .read_to_end(&mut persisted)
            .map_err(|error| error.to_string())?;
        if persisted.len() != bytes.len() || hex::encode(Sha256::digest(&persisted)) != sha256 {
            return Err("Saved artifact checksum verification failed".into());
        }
        Ok(())
    })();
    if let Err(error) = written {
        // Do not unlink by pathname: another process could replace it between
        // creation and cleanup. Preserve for manual inspection instead.
        return Err(format!(
            "Export was not verified; inspect/remove the incomplete destination manually: {error}"
        ));
    }
    Ok(json!({
        "written_to_disk":true,
        "submission_performed":false,
        "destination":target.display().to_string(),
        "sha256":sha256,
        "byte_length":bytes.len(),
        "project_revision":pending.project_revision,
        "no_overwrite":true,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{evidence_execute_pending, evidence_preview_at, load_project_with_audit};
    use uuid::Uuid;

    #[test]
    fn explicit_file_delivery_verifies_all_manuscript_formats_and_draft_zip() {
        let root = std::env::temp_dir().join(format!("rw-explicit-export-{}", Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap();
        let project = root.join("study");
        load_project_with_audit(
            project.to_str().unwrap(),
            "Physical exports",
            true,
            &root.join("create-audit.sqlite"),
        )
        .unwrap();
        let host = root.join("host");
        let (pending, _) = evidence_preview_at(
            &project,
            "writing.section_save",
            "writing",
            json!({"manuscript_id":"paper","section":"Results","body":"Study result.","citations":[]}),
            &host,
        )
        .unwrap();
        evidence_execute_pending(&pending, &project, &host).unwrap();

        for (format, extension) in [
            ("markdown", "md"),
            ("html", "html"),
            ("docx", "docx"),
            ("pdf", "pdf"),
        ] {
            let (prepared, _generated) = prepare(
                &project,
                "writing.manuscript_export",
                json!({"manuscript_id":"paper","format":format}),
                &host,
            )
            .unwrap();
            let destination = root.join(format!("paper.{extension}"));
            assert!(!destination.exists(), "prepare must never save to disk");
            assert!(save_for_screen(
                &prepared,
                &project,
                destination.to_str().unwrap(),
                &host,
                "writing.submission_export"
            )
            .is_err());
            assert!(!destination.exists());
            let saved = save(&prepared, &project, destination.to_str().unwrap(), &host).unwrap();
            assert_eq!(saved["written_to_disk"], true);
            assert_eq!(saved["submission_performed"], false);
            assert_eq!(saved["sha256"], prepared.sha256);
            assert_eq!(
                fs::metadata(&destination).unwrap().len(),
                prepared.length as u64
            );
            assert!(save(&prepared, &project, destination.to_str().unwrap(), &host).is_err());
            assert_eq!(
                hex::encode(Sha256::digest(fs::read(&destination).unwrap())),
                prepared.sha256
            );
        }
        let (packet, _) = prepare(
            &project,
            "writing.submission_export",
            json!({"manuscript_id":"paper","journal":"Review Journal","allow_incomplete":true}),
            &host,
        )
        .unwrap();
        let zip = root.join("paper.rw-submission.zip");
        save(&packet, &project, zip.to_str().unwrap(), &host).unwrap();
        assert!(fs::read(&zip).unwrap().starts_with(b"PK\x03\x04"));
        assert!(save(&packet, &project, "relative.zip", &host).is_err());
        assert!(save(
            &packet,
            &project,
            root.join("wrong.pdf").to_str().unwrap(),
            &host
        )
        .is_err());
        {
            let audit = AuditStore::open(host.join("operation-audit.sqlite")).unwrap();
            let records = audit.events().unwrap();
            assert!(
                records
                    .iter()
                    .filter(|event| event.operation == "export.file_save"
                        && event.effect == "sensitive-export"
                        && event.status == "ok")
                    .count()
                    >= 5
            );
            assert!(
                !serde_json::to_string(&records)
                    .unwrap()
                    .contains("Study result."),
                "the export audit must record hashes, never confidential manuscript content"
            );
        }

        let (stale, _) = prepare(
            &project,
            "writing.manuscript_export",
            json!({"manuscript_id":"paper","format":"markdown"}),
            &host,
        )
        .unwrap();
        let (next, _) = evidence_preview_at(
            &project,
            "writing.section_save",
            "writing",
            json!({"manuscript_id":"paper","section":"Results","body":"Changed result","citations":[]}),
            &host,
        )
        .unwrap();
        evidence_execute_pending(&next, &project, &host).unwrap();
        let unsaved = root.join("stale.md");
        assert!(save(&stale, &project, unsaved.to_str().unwrap(), &host).is_err());
        assert!(!unsaved.exists());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn tampered_receipt_fails_before_writing() {
        let receipt = json!({"data":{"base64":"dGVzdA==","byte_length":4,
            "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}});
        assert!(checked_bytes(&receipt).is_err());
        let receipt = json!({"data":{"base64":"dGVzdA==","byte_length":5,
            "sha256":hex::encode(Sha256::digest(b"test"))}});
        assert!(checked_bytes(&receipt).is_err());
    }
}
