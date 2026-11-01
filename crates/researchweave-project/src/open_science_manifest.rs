//! F34: offline, redacted, integrity-verified research-object inventory.
//!
//! This is not an OSF upload, RO-Crate conformance certification, or a grant
//! of rights to distribute source material. Every rights assertion remains
//! caller-declared and unverified; the deposit gate is always closed.
use crate::{sha256, ProjectStore};
use researchweave_core::DispatchContext;
use rusqlite::params;
use serde_json::{json, Map, Value};
use std::collections::HashSet;
use std::path::Path;
use uuid::Uuid;

const FORMAT: &str = "researchweave-redacted-research-object-inventory-v1";
const MAX_SOURCES: usize = 4096;
const MAX_RIGHTS: usize = 4096;

fn validate_rights(arguments: &Value) -> Result<Map<String, Value>, String> {
    let allowed = ["project_id", "rights_declarations"];
    let object = arguments
        .as_object()
        .ok_or("research-object arguments must be an object")?;
    if object.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err("unexpected research-object manifest arguments".into());
    }
    let rights = match object.get("rights_declarations") {
        None => return Ok(Map::new()),
        Some(value) => value
            .as_object()
            .ok_or("rights declarations must be a map")?,
    };
    if rights.len() > MAX_RIGHTS {
        return Err("rights declaration limit exceeded".into());
    }
    for (id, declaration) in rights {
        let parsed = Uuid::parse_str(id).map_err(|_| "invalid source rights UUID")?;
        if parsed.to_string() != *id {
            return Err("source rights UUID must be canonical".into());
        }
        let fields = declaration
            .as_object()
            .ok_or("rights entry must be an object")?;
        if fields
            .keys()
            .any(|key| key != "spdx_license" && key != "redistribution_declared")
        {
            return Err("unsupported rights declaration field".into());
        }
        let license = fields
            .get("spdx_license")
            .and_then(Value::as_str)
            .ok_or("explicit source SPDX license required")?;
        if license.is_empty()
            || license.len() > 64
            || !license
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'+' | b'.'))
        {
            return Err("source license must be a bounded SPDX-style identifier".into());
        }
        if !fields
            .get("redistribution_declared")
            .is_some_and(Value::is_boolean)
        {
            return Err("source redistribution declaration must be boolean".into());
        }
    }
    Ok(rights.clone())
}

pub(crate) fn preview(
    project_path: &Path,
    args: &Value,
    context: &DispatchContext,
    integrity: &Value,
) -> Result<Value, String> {
    let rights = validate_rights(args)?;
    let store =
        ProjectStore::open(project_path).map_err(|_| "validated project cannot be reopened")?;
    let info = store.info().map_err(|_| "project metadata unavailable")?;
    if info.id != context.project_id.to_string()
        || args.get("project_id").and_then(Value::as_str) != Some(info.id.as_str())
        || context
            .expected_revision
            .is_some_and(|expected| expected != info.revision as u64)
    {
        return Err("project scope or requested revision changed".into());
    }
    if integrity["ok"] != true
        || integrity["project_id"] != info.id
        || integrity["revision"] != info.revision
        || !integrity["last_event_sha256"].is_string()
    {
        return Err("verified source project receipt missing or changed".into());
    }
    let mut statement = store
        .connection()
        .prepare(
            "SELECT s.id,s.media_type,s.digest,o.size,s.deleted
         FROM sources s JOIN objects o ON o.digest=s.digest
         ORDER BY s.id LIMIT ?1",
        )
        .map_err(|_| "verified source index unavailable")?;
    let rows = statement
        .query_map(params![(MAX_SOURCES + 1) as i64], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, i64>(4)?,
            ))
        })
        .map_err(|_| "verified source records unavailable")?;
    let mut sources = Vec::<Value>::new();
    let mut known = HashSet::<String>::new();
    let mut deleted_count = 0;
    let mut total_bytes = 0u64;
    for row in rows {
        let (id, media_type, digest, size, deleted) =
            row.map_err(|_| "source inventory unreadable")?;
        if sources.len() + deleted_count >= MAX_SOURCES {
            return Err("source inventory exceeds portable preview budget".into());
        }
        let id_uuid = Uuid::parse_str(&id).map_err(|_| "invalid persisted source identity")?;
        if id_uuid.to_string() != id {
            return Err("noncanonical persisted source ID".into());
        }
        if size < 0
            || digest.len() != 64
            || !digest
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
            || deleted != 0 && deleted != 1
        {
            return Err("source object integrity metadata invalid".into());
        }
        known.insert(id.clone());
        if deleted == 1 {
            deleted_count += 1;
            continue;
        }
        let declaration = rights.get(&id);
        total_bytes = total_bytes
            .checked_add(size as u64)
            .ok_or("source inventory byte count overflow")?;
        sources.push(json!({
            "source_id":id,
            "media_type":media_type,
            "sha256":digest,
            "bytes":size,
            "license_spdx_user_declared":declaration
                .and_then(|value| value["spdx_license"].as_str()),
            "redistribution_user_declared":declaration
                .and_then(|value| value["redistribution_declared"].as_bool()),
            "rights_verified":false,
            "consent_verified":false,
            "source_title_redacted":true,
            "source_path_redacted":true,
        }));
    }
    if rights.keys().any(|id| !known.contains(id)) {
        return Err("rights declaration refers to unknown source identity".into());
    }
    let receipt = json!({
        "format":FORMAT,
        "project_id":info.id,
        "source_project_revision":info.revision,
        "source_event_chain_sha256":integrity["last_event_sha256"],
        "source_objects_integrity_checked":true,
        "project_privacy_label":info.privacy,
        "source_count":sources.len(),
        "deleted_sources_omitted":deleted_count,
        "included_total_bytes":total_bytes,
        "source_files_included":false,
        "source_titles_and_paths_redacted":true,
        "source_records":sources,
        "rights_verified":false,
        "ethics_or_patient_consent_verified":false,
        "redistribution_authorized":false,
        "external_deposit_performed":false,
        "osf_upload_performed":false,
        "ro_crate_conformance_claimed":false,
        "human_licensing_and_privacy_review_required":true,
        "warning":"This is a local cryptographic inventory only. User-declared license and redistribution flags are not independent legal or ethical proof; it is NOT safe to publish files or patient data based on this receipt."
    });
    let canonical = serde_json::to_string(&receipt)
        .map_err(|_| "research-object manifest serialization failed")?;
    if canonical.len() > 3_000_000 {
        return Err("research-object preview exceeds output budget".into());
    }
    Ok(json!({
        "preview_only":true,"writes":0,
        "manifest":receipt,
        "manifest_sha256":sha256(canonical.as_bytes()),
        "manifest_json":canonical,
        "physical_file_written":false,
        "remote_service_contacted":false
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ProjectInfo;
    use researchweave_core::OperationHandler;

    #[test]
    fn redacted_immutable_manifest_requires_scoped_integrity_and_explicit_unverified_rights() {
        fn rights_map(source: &str, license: &str) -> Value {
            let mut rights = Map::new();
            rights.insert(
                source.to_owned(),
                json!({"spdx_license":license,"redistribution_declared":true}),
            );
            Value::Object(rights)
        }
        let dir = tempfile::tempdir().unwrap();
        let id = Uuid::new_v4();
        let project = dir.path().join("Research");
        let store = ProjectStore::create(
            &project,
            &ProjectInfo {
                id: id.to_string(),
                title: "Patient research: private".into(),
                question: "Clinical subject secret".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "restricted".into(),
                revision: 0,
                created_at: "2026-11-01T00:00:00Z".into(),
            },
        )
        .unwrap();
        let bytes = b"synthetic deidentified data";
        let digest = store.put_object(bytes).unwrap();
        let source = Uuid::new_v4().to_string();
        store
            .connection()
            .execute(
                "INSERT INTO sources(id,title,media_type,digest,imported_at,origin,deleted)
             VALUES (?1,?2,?3,?4,?5,?6,0)",
                params![
                    source,
                    "Sensitive unverified source",
                    "text/plain",
                    digest,
                    "2026-11-01T00:00:00Z",
                    "private-source-path"
                ],
            )
            .unwrap();
        let handler = crate::ProjectHandler::bound(id, &project).unwrap();
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: id,
            actor: "local-preview".into(),
            expected_revision: Some(0),
        };
        let args = json!({"project_id":id.to_string(),
            "rights_declarations":rights_map(&source,"CC-BY-4.0")});
        let before = std::fs::read(project.join("data/project.sqlite")).unwrap();
        let result = handler.execute("project.open_science_manifest_preview", &args, &context);
        assert!(result.get("status").is_none(), "{result}");
        let data = &result["data"];
        assert_eq!(data["writes"], 0);
        assert_eq!(data["manifest"]["source_count"], 1);
        assert_eq!(data["manifest"]["included_total_bytes"], bytes.len());
        assert_eq!(data["manifest"]["source_records"][0]["sha256"], digest);
        assert_eq!(
            data["manifest"]["source_records"][0]["rights_verified"],
            false
        );
        assert_eq!(data["manifest"]["redistribution_authorized"], false);
        assert_eq!(data["manifest"]["external_deposit_performed"], false);
        assert_eq!(data["physical_file_written"], false);
        assert_eq!(data["remote_service_contacted"], false);
        let encoded = data["manifest_json"].as_str().unwrap();
        assert_eq!(data["manifest_sha256"], sha256(encoded.as_bytes()));
        assert!(!encoded.contains("Sensitive unverified source"));
        assert!(!encoded.contains("Clinical subject secret"));
        assert!(!encoded.contains("private-source-path"));
        let again = handler.execute("project.open_science_manifest_preview", &args, &context);
        assert_eq!(result, again);
        assert_eq!(
            std::fs::read(project.join("data/project.sqlite")).unwrap(),
            before
        );
        let invalid = [
            json!({"project_id":Uuid::new_v4().to_string()}),
            json!({"project_id":id.to_string(),
                "rights_declarations":rights_map(&Uuid::new_v4().to_string(),"CC0-1.0")}),
            json!({"project_id":id.to_string(),
                "rights_declarations":rights_map(&source,"CC BY 4.0")}),
            json!({"project_id":id.to_string(),"password":"do not accept"}),
        ];
        for args in invalid {
            assert_eq!(
                handler.execute("project.open_science_manifest_preview", &args, &context)["status"],
                "failed"
            );
        }
    }
}
