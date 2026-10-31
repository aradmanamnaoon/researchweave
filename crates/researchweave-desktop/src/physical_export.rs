//! Explicit, non-overwriting desktop file delivery for read-only, revision-bound
//! manuscript and draft submission artifacts. This never submits data to a journal.
use super::{analysis_read_at, evidence_read_at, now_seconds, ProjectStore};
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
        "protocol.export" => Ok("md"),
        "analysis.report.render" => Ok("md"),
        _ => Err("Only verified protocol, analysis report, manuscript and draft submission artifacts can be saved".into()),
    }
}

fn render_artifact(
    project: &Path,
    operation: &str,
    arguments: Value,
    root: &Path,
) -> Result<Value, String> {
    let mut result = if operation == "analysis.report.render" {
        analysis_read_at(project, operation, arguments, root)?
    } else {
        evidence_read_at(project, operation, arguments, root)?
    };
    if matches!(operation, "protocol.export" | "analysis.report.render") {
        // The existing read-only protocol endpoint returns verified persisted
        // Markdown text rather than the binary receipt used by publishing.
        // Analysis reports similarly compose verified immutable result IDs.
        // Adapt only at the trusted desktop boundary; do not change either API.
        if operation == "analysis.report.render" {
            let data = result
                .get("data")
                .ok_or("Analysis report receipt unavailable")?;
            let report_hash = data["report_sha256"]
                .as_str()
                .ok_or("Analysis report has no provenance digest")?;
            if data["format"] != "markdown"
                || data["scientific_interpretation_generated"] != false
                || !data["manifest"].is_object()
                || report_hash.len() != 64
                || !report_hash.bytes().all(|byte| byte.is_ascii_hexdigit())
            {
                return Err("Analysis report is missing verified provenance".into());
            }
        }
        let body = result
            .pointer("/data/text")
            .and_then(Value::as_str)
            .ok_or("Verified export did not return Markdown")?
            .as_bytes();
        if body.is_empty() || body.len() > MAX_EXPORT_BYTES {
            return Err("Verified Markdown is empty or exceeds export limit".into());
        }
        let length = body.len();
        let digest = hex::encode(Sha256::digest(body));
        let encoded = STANDARD.encode(body);
        let object = result
            .get_mut("data")
            .and_then(Value::as_object_mut)
            .ok_or("Verified Markdown receipt is malformed")?;
        object.insert("base64".into(), Value::String(encoded));
        object.insert("sha256".into(), Value::String(digest));
        object.insert("byte_length".into(), json!(length));
        object.insert("written_to_disk".into(), Value::Bool(false));
        object.insert("submission_performed".into(), Value::Bool(false));
    }
    Ok(result)
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
    let result = render_artifact(project, operation, arguments.clone(), root)?;
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
    let receipt = render_artifact(
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
    use crate::{
        analysis_execute_command_pending, analysis_execute_pending, analysis_preview_command_at,
        analysis_preview_import_at, evidence_execute_pending, evidence_preview_at,
        load_project_with_audit,
    };
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

    #[test]
    fn analysis_report_markdown_is_verified_on_prepare_and_one_use_physical_save() {
        let root = std::env::temp_dir().join(format!("rw-physical-report-{}", Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap();
        let project = root.join("study");
        load_project_with_audit(
            project.to_str().unwrap(),
            "Report export",
            true,
            &root.join("project-create-audit.sqlite"),
        )
        .unwrap();
        let source = root.join("measurements.csv");
        fs::write(&source, b"score,group\n1,A\n3,A\n5,B\n").unwrap();
        let host = root.join("host");
        let (import, preview) =
            analysis_preview_import_at(&project, source.to_str().unwrap(), &host).unwrap();
        assert_eq!(preview["data"]["preview"], true);
        let imported = analysis_execute_pending(&import, &project, &host).unwrap();
        let arguments = json!({
            "operation":"statistics.describe",
            "arguments":{
                "dataset_id":imported["data"]["dataset_id"],
                "revision":imported["data"]["revision"],
                "column":"score"
            }
        });
        let (result_pending, analysis_preview) =
            analysis_preview_command_at(&project, "analysis.result.save", arguments, &host)
                .unwrap();
        assert_eq!(analysis_preview["data"]["preview"], true);
        let result_record =
            analysis_execute_command_pending(&result_pending, &project, &host).unwrap();
        let result_id = result_record["data"]["result_id"].as_str().unwrap();

        let report_args = json!({
            "title":"Verified descriptive report",
            "result_ids":[result_id]
        });
        let (prepared, report) = prepare(
            &project,
            "analysis.report.render",
            report_args.clone(),
            &host,
        )
        .unwrap();
        assert_eq!(report["data"]["scientific_interpretation_generated"], false);
        assert_eq!(report["data"]["written_to_disk"], false);
        assert_eq!(report["data"]["manifest"]["result_ids"][0], result_id);
        assert!(report["data"]["text"]
            .as_str()
            .unwrap()
            .contains("## 1. `statistics.describe`"));
        assert_eq!(prepared.extension, "md");

        let destination = root.join("verified-report.md");
        assert!(!destination.exists(), "preparation must not write a file");
        assert!(save_for_screen(
            &prepared,
            &project,
            destination.to_str().unwrap(),
            &host,
            "writing.manuscript_export"
        )
        .is_err());
        assert!(!destination.exists());
        assert!(save(
            &prepared,
            &project,
            root.join("wrong.pdf").to_str().unwrap(),
            &host
        )
        .is_err());
        assert!(!root.join("wrong.pdf").exists());

        let receipt = save_for_screen(
            &prepared,
            &project,
            destination.to_str().unwrap(),
            &host,
            "analysis.report.render",
        )
        .unwrap();
        assert_eq!(receipt["written_to_disk"], true);
        assert_eq!(receipt["submission_performed"], false);
        assert_eq!(receipt["no_overwrite"], true);
        let body = fs::read_to_string(&destination).unwrap();
        assert!(body.contains("Verified descriptive report"));
        assert!(body.contains("statistics.describe"));
        assert!(body.contains("Dataset revision:"));
        assert_eq!(
            hex::encode(Sha256::digest(body.as_bytes())),
            prepared.sha256
        );
        assert!(save(&prepared, &project, destination.to_str().unwrap(), &host).is_err());
        assert_eq!(fs::read_to_string(&destination).unwrap(), body);

        let (stale, _) = prepare(&project, "analysis.report.render", report_args, &host).unwrap();
        let (next, _) = evidence_preview_at(
            &project,
            "protocol.create",
            "protocol",
            json!({"title":"Revised protocol", "author":"Investigator",
                "body":{"design":"observational","objective":"Observe score"}}),
            &host,
        )
        .unwrap();
        evidence_execute_pending(&next, &project, &host).unwrap();
        let stale_destination = root.join("stale.md");
        assert!(save(&stale, &project, stale_destination.to_str().unwrap(), &host).is_err());
        assert!(
            !stale_destination.exists(),
            "stale report must not create a file"
        );

        let audit = AuditStore::open(host.join("operation-audit.sqlite")).unwrap();
        let records = audit.events().unwrap();
        assert!(records.iter().any(|record| {
            record.operation == "export.file_save"
                && record.effect == "sensitive-export"
                && record.status == "ok"
        }));
        drop(audit);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn approved_protocol_markdown_file_is_versioned_audited_and_never_overwritten() {
        let root = std::env::temp_dir().join(format!("rw-protocol-export-{}", Uuid::new_v4()));
        fs::create_dir_all(&root).unwrap();
        let project = root.join("protocol-project");
        load_project_with_audit(
            project.to_str().unwrap(),
            "Protocol export",
            true,
            &root.join("create-audit.sqlite"),
        )
        .unwrap();
        let host = root.join("host");
        let (create, _) = evidence_preview_at(
            &project,
            "protocol.create",
            "protocol",
            json!({"title":"Clinical methods","author":"Researcher",
                "body":{"design":"observational","objective":"Study outcomes"}}),
            &host,
        )
        .unwrap();
        let (created, _) = evidence_execute_pending(&create, &project, &host).unwrap();
        let id = created["data"]["protocol_id"].as_str().unwrap();
        let (prepared, generated) = prepare(
            &project,
            "protocol.export",
            json!({"protocol_id":id}),
            &host,
        )
        .unwrap();
        assert!(generated["data"]["text"]
            .as_str()
            .unwrap()
            .contains("# Clinical methods"));
        assert_eq!(generated["data"]["written_to_disk"], false);
        let file = root.join("clinical-methods.md");
        assert!(!file.exists());
        let saved = save_for_screen(
            &prepared,
            &project,
            file.to_str().unwrap(),
            &host,
            "protocol.export",
        )
        .unwrap();
        assert_eq!(saved["sha256"], prepared.sha256);
        assert_eq!(saved["submission_performed"], false);
        let body = fs::read_to_string(&file).unwrap();
        assert!(body.contains("# Clinical methods"));
        assert!(body.contains("### Version 1"));
        assert_eq!(
            hex::encode(Sha256::digest(body.as_bytes())),
            prepared.sha256
        );
        assert!(save(&prepared, &project, file.to_str().unwrap(), &host).is_err());
        assert_eq!(fs::read_to_string(&file).unwrap(), body);

        let (amend, _) = evidence_preview_at(
            &project,
            "protocol.amend",
            "protocol",
            json!({"protocol_id":id,"author":"Researcher",
                "rationale":"Refine outcomes",
                "body":{"design":"observational","objective":"Refined outcomes"}}),
            &host,
        )
        .unwrap();
        evidence_execute_pending(&amend, &project, &host).unwrap();
        let stale_target = root.join("stale-protocol.md");
        assert!(save(&prepared, &project, stale_target.to_str().unwrap(), &host).is_err());
        assert!(!stale_target.exists());
        let (updated, _) = prepare(
            &project,
            "protocol.export",
            json!({"protocol_id":id}),
            &host,
        )
        .unwrap();
        assert_ne!(prepared.sha256, updated.sha256);
        save(&updated, &project, stale_target.to_str().unwrap(), &host).unwrap();
        assert!(fs::read_to_string(&stale_target)
            .unwrap()
            .contains("### Version 2"));
        {
            let audit = AuditStore::open(host.join("operation-audit.sqlite")).unwrap();
            assert!(audit.events().unwrap().iter().any(|record| {
                record.operation == "export.file_save" && record.effect == "sensitive-export"
            }));
        }
        fs::remove_dir_all(root).unwrap();
    }
}
