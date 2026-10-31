//! Local protocol baseline freeze stored as an append-only, project-revisioned
//! event. A local timestamp and event digest are NOT external preregistration.
//! The existing protocol version table remains append-only and compatible with
//! schema-v5 projects and encrypted project archives.

use super::{digest, mutate, required_text, DispatchContext, ProjectStore};
use rusqlite::{params, Connection};
use serde_json::{json, Value};

#[derive(Debug)]
struct FreezeRecord {
    version: i64,
    sha256: String,
    actor: String,
    timestamp: String,
    event_hash: String,
    sequence: i64,
}

fn snapshot(
    conn: &Connection,
    protocol_id: &str,
    requested_version: Option<i64>,
) -> Result<(i64, String), String> {
    let (version, title, body_raw, author, recorded_at): (i64, String, String, String, String) =
        conn.query_row(
            "SELECT version,title,body_json,author,recorded_at FROM protocols
             WHERE id=?1 AND (?2 IS NULL OR version=?2)
             ORDER BY version DESC LIMIT 1",
            params![protocol_id, requested_version],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            },
        )
        .map_err(|_| "protocol version unavailable")?;
    if version <= 0 {
        return Err("invalid protocol version".into());
    }
    let body: Value = serde_json::from_str(&body_raw).map_err(|_| "protocol body is corrupt")?;
    if !body.is_object() {
        return Err("protocol body must be a structured object".into());
    }
    let canonical = json!({
        "protocol_id":protocol_id,
        "version":version,
        "title":title,
        "body":body,
        "author":author,
        "recorded_at":recorded_at
    });
    let bytes =
        serde_json::to_vec(&canonical).map_err(|_| "protocol snapshot cannot be encoded")?;
    Ok((version, digest(&bytes)))
}

fn frozen_event(conn: &Connection, protocol_id: &str) -> Result<Option<FreezeRecord>, String> {
    let mut statement = conn
        .prepare(
            "SELECT payload_json,actor,timestamp,event_hash,sequence
         FROM events WHERE operation='protocol.freeze' ORDER BY sequence",
        )
        .map_err(|_| "protocol freeze journal is unavailable")?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, i64>(4)?,
            ))
        })
        .map_err(|_| "protocol freeze journal cannot be read")?;
    let mut found = None;
    for row in rows {
        let (raw, actor, timestamp, event_hash, sequence) =
            row.map_err(|_| "protocol freeze journal is corrupt")?;
        if raw.len() > 8_192 {
            return Err("protocol freeze event is oversized".into());
        }
        let event: Value =
            serde_json::from_str(&raw).map_err(|_| "protocol freeze event is invalid JSON")?;
        if event["protocol_id"].as_str() != Some(protocol_id) {
            continue;
        }
        if found.is_some() {
            return Err("conflicting local protocol freezes were recorded".into());
        }
        let version = event["version"]
            .as_i64()
            .filter(|version| *version > 0)
            .ok_or("local protocol freeze event has invalid version")?;
        let sha256 = event["snapshot_sha256"]
            .as_str()
            .filter(|hash| hash.len() == 64 && hash.bytes().all(|byte| byte.is_ascii_hexdigit()))
            .ok_or("local protocol freeze event has invalid digest")?;
        if event_hash.len() != 64 || !event_hash.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err("local protocol freeze event has invalid chain hash".into());
        }
        found = Some(FreezeRecord {
            version,
            sha256: sha256.to_owned(),
            actor,
            timestamp,
            event_hash,
            sequence,
        });
    }
    Ok(found)
}

pub(super) fn status(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let protocol_id = required_text(args, "protocol_id")?.trim();
    if protocol_id.is_empty() || protocol_id.len() > 128 {
        return Err("invalid protocol identifier".into());
    }
    let conn = store.connection();
    let (current_version, _) = snapshot(conn, protocol_id, None)?;
    let Some(frozen) = frozen_event(conn, protocol_id)? else {
        return Ok(json!({
            "protocol_id":protocol_id,
            "frozen":false,
            "current_version":current_version,
            "local_only":true,
            "external_registration_verified":false
        }));
    };
    let (_, actual_hash) = snapshot(conn, protocol_id, Some(frozen.version))?;
    if actual_hash != frozen.sha256 {
        return Err("frozen protocol version no longer matches its recorded SHA-256".into());
    }
    if frozen.version > current_version {
        return Err("frozen protocol version is newer than the latest version".into());
    }
    Ok(json!({
        "protocol_id":protocol_id,
        "frozen":true,
        "frozen_version":frozen.version,
        "snapshot_sha256":frozen.sha256,
        "recorded_at_local_clock":frozen.timestamp,
        "actor_unverified":frozen.actor,
        "event_hash":frozen.event_hash,
        "event_sequence":frozen.sequence,
        "current_version":current_version,
        "post_freeze_amendment_versions":current_version-frozen.version,
        "local_only":true,
        "external_registration_verified":false
    }))
}

/// A read-only, deterministic Markdown representation of the authoritative
/// local baseline event. The 4-space-indented JSON prevents user-supplied
/// author/actor strings from becoming executable Markdown instructions.
/// No file is written here; physical delivery requires a separately approved
/// sensitive-export action at the desktop boundary.
pub(super) fn receipt(store: &ProjectStore, args: &Value) -> Result<Value, String> {
    let data = status(store, args)?;
    if data["frozen"] != true
        || data["local_only"] != true
        || data["external_registration_verified"] != false
    {
        return Err(
            "Freeze an existing protocol before exporting its local baseline receipt".into(),
        );
    }
    let project_id = store.info().map_err(|_| "project identity unavailable")?.id;
    let record = json!({"project_id":project_id,"local_baseline":data});
    let canonical = serde_json::to_string_pretty(&record)
        .map_err(|_| "Local baseline receipt could not be serialized")?;
    let indented = canonical
        .lines()
        .map(|line| format!("    {line}"))
        .collect::<Vec<_>>()
        .join("\n");
    let text = format!(
        "# ResearchWeave local protocol baseline receipt\n\n\
         **Local-only provenance; NOT externally verified preregistration.** \
         The computer clock, local event sequence, event digest and unverified \
         actor do not establish an independent timestamp or identity.\n\n\
         The snapshot digest binds the original persisted protocol version; \
         subsequent amendments are reported without rewriting that version.\n\n\
         ## Verified local record\n\n{indented}\n"
    );
    Ok(json!({
        "text":text,
        "project_id":project_id,
        "protocol_id":record["local_baseline"]["protocol_id"],
        "frozen":true,
        "frozen_version":record["local_baseline"]["frozen_version"],
        "snapshot_sha256":record["local_baseline"]["snapshot_sha256"],
        "event_hash":record["local_baseline"]["event_hash"],
        "event_sequence":record["local_baseline"]["event_sequence"],
        "local_only":true,
        "external_registration_verified":false,
        "written_to_disk":false
    }))
}

pub(super) fn write(
    store: &mut ProjectStore,
    args: &Value,
    context: &DispatchContext,
) -> Result<Value, String> {
    let protocol_id = required_text(args, "protocol_id")?.trim();
    if protocol_id.is_empty() || protocol_id.len() > 128 {
        return Err("invalid protocol identifier".into());
    }
    let expected_version = args
        .get("expected_version")
        .and_then(Value::as_i64)
        .filter(|version| *version > 0)
        .ok_or("expected_version must be a recorded positive protocol version")?;
    let (latest_version, snapshot_sha256) = snapshot(store.connection(), protocol_id, None)?;
    if latest_version != expected_version {
        return Err("protocol changed since the requested freeze version; preview again".into());
    }
    if frozen_event(store.connection(), protocol_id)?.is_some() {
        return Err("this protocol already has an immutable local freeze baseline".into());
    }
    let payload = json!({
        "protocol_id":protocol_id,
        "version":latest_version,
        "snapshot_sha256":snapshot_sha256,
        "kind":"local_protocol_baseline_v1"
    });
    let (recorded_at, project_revision) = mutate(
        store,
        "protocol.freeze",
        context,
        &payload,
        |transaction, now| {
            if frozen_event(transaction, protocol_id)?.is_some() {
                return Err("this protocol already has an immutable local freeze baseline".into());
            }
            let (revision, observed_sha256) = snapshot(transaction, protocol_id, None)?;
            if revision != latest_version || observed_sha256 != snapshot_sha256 {
                return Err("protocol version or content changed during local freeze".into());
            }
            Ok(now.to_owned())
        },
    )?;
    Ok(json!({
        "protocol_id":protocol_id,
        "frozen":true,
        "frozen_version":latest_version,
        "snapshot_sha256":snapshot_sha256,
        "recorded_at_local_clock":recorded_at,
        "actor_unverified":context.actor,
        "project_revision":project_revision,
        "post_freeze_amendment_versions":0,
        "local_only":true,
        "external_registration_verified":false
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::EvidenceHandler;
    use researchweave_core::OperationHandler;
    use researchweave_project::ProjectInfo;
    use uuid::Uuid;

    #[test]
    fn freeze_preserves_protocol_version_and_exposes_later_amendments_without_relock() {
        let fixture = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let project_root = fixture.path().join(project_id.to_string());
        let store = ProjectStore::create(
            &project_root,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Prospective study".into(),
                question: "Does the intervention change outcomes?".into(),
                design: "observational".into(),
                locale: "en".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-31T00:00:00Z".into(),
            },
        )
        .unwrap();
        drop(store);
        let handler = EvidenceHandler::new(fixture.path().to_path_buf());
        let scoped_context = |revision| DispatchContext {
            request_id: Uuid::new_v4(),
            project_id,
            actor: "unverified-local-researcher".into(),
            expected_revision: Some(revision),
        };
        let create = handler.execute(
            "protocol.create",
            &json!({
                "project_id":project_id.to_string(),
                "title":"Baseline analysis protocol",
                "author":"Local researcher",
                "body":{"design":"observational","objective":"Measure a prespecified outcome"}
            }),
            &scoped_context(0),
        );
        assert_eq!(create["status"], "ok", "{create}");
        let protocol_id = create["data"]["protocol_id"].as_str().unwrap();
        let subject = json!({"project_id":project_id.to_string(),"protocol_id":protocol_id});
        let fresh = handler.execute("protocol.freeze_status", &subject, &scoped_context(1));
        assert_eq!(fresh["data"]["frozen"], false);
        assert_eq!(
            handler.execute("protocol.freeze_receipt", &subject, &scoped_context(1))["status"],
            "error",
            "unfrozen protocols cannot export a baseline receipt"
        );
        let freeze = json!({
            "project_id":project_id.to_string(),
            "protocol_id":protocol_id,
            "expected_version":1
        });
        let invalid = handler.preview(
            "protocol.freeze",
            &json!({
                "project_id":project_id.to_string(),
                "protocol_id":protocol_id,
                "expected_version":2
            }),
            &scoped_context(1),
        );
        assert_eq!(invalid["status"], "error", "{invalid}");
        let preview = handler.preview("protocol.freeze", &freeze, &scoped_context(1));
        assert_eq!(preview["status"], "ok", "{preview}");
        assert_eq!(preview["data"]["authoritative_revision"], 1);
        assert_eq!(preview["data"]["simulated_revision"], 2);
        let preview_hash = preview["data"]["simulated_result"]["snapshot_sha256"]
            .as_str()
            .unwrap()
            .to_owned();
        assert_eq!(preview_hash.len(), 64);
        let before = ProjectStore::open(&project_root).unwrap();
        assert_eq!(before.info().unwrap().revision, 1);
        let events: i64 = before
            .connection()
            .query_row("SELECT count(*) FROM events", [], |row| row.get(0))
            .unwrap();
        assert_eq!(events, 1, "preview must never change the project");
        drop(before);

        let recorded = handler.execute("protocol.freeze", &freeze, &scoped_context(1));
        assert_eq!(recorded["status"], "ok", "{recorded}");
        assert_eq!(recorded["data"]["snapshot_sha256"], preview_hash);
        assert_eq!(recorded["data"]["local_only"], true);
        assert_eq!(recorded["data"]["external_registration_verified"], false);
        assert_eq!(recorded["data"]["project_revision"], 2);
        let locked = handler.execute("protocol.freeze_status", &subject, &scoped_context(2));
        assert_eq!(locked["status"], "ok", "{locked}");
        assert_eq!(locked["data"]["frozen"], true);
        assert_eq!(locked["data"]["frozen_version"], 1);
        assert_eq!(locked["data"]["current_version"], 1);
        assert_eq!(locked["data"]["post_freeze_amendment_versions"], 0);
        assert_eq!(locked["data"]["snapshot_sha256"], preview_hash);
        assert_eq!(locked["data"]["event_hash"].as_str().unwrap().len(), 64);
        let receipt = handler.execute("protocol.freeze_receipt", &subject, &scoped_context(2));
        assert_eq!(receipt["status"], "ok", "{receipt}");
        assert_eq!(receipt["data"]["snapshot_sha256"], preview_hash);
        assert_eq!(receipt["data"]["written_to_disk"], false);
        assert_eq!(receipt["data"]["event_hash"], locked["data"]["event_hash"]);
        let markdown = receipt["data"]["text"].as_str().unwrap();
        assert!(markdown.contains("NOT externally verified preregistration"));
        assert!(markdown.contains(&preview_hash));
        assert!(markdown.contains("    \"local_baseline\""));
        assert_eq!(
            handler.preview("protocol.freeze", &freeze, &scoped_context(2))["status"],
            "error",
            "a protocol must have only one baseline freeze"
        );
        assert_eq!(
            handler.execute("protocol.freeze", &freeze, &scoped_context(2))["status"],
            "error",
            "a direct duplicate request cannot lock another baseline"
        );

        let amended = handler.execute(
            "protocol.amend",
            &json!({
                "project_id":project_id.to_string(),"protocol_id":protocol_id,
                "author":"Local researcher","rationale":"Transparent post-freeze amendment",
                "body":{
                    "design":"observational","objective":"Measure a prespecified outcome",
                    "secondary_outcome":"New, declared after baseline"
                }
            }),
            &scoped_context(2),
        );
        assert_eq!(amended["status"], "ok", "{amended}");
        let reloaded = handler.execute("protocol.freeze_status", &subject, &scoped_context(3));
        assert_eq!(reloaded["status"], "ok", "{reloaded}");
        assert_eq!(reloaded["data"]["frozen_version"], 1);
        assert_eq!(reloaded["data"]["current_version"], 2);
        assert_eq!(reloaded["data"]["post_freeze_amendment_versions"], 1);
        assert_eq!(reloaded["data"]["snapshot_sha256"], preview_hash);
        let amended_receipt =
            handler.execute("protocol.freeze_receipt", &subject, &scoped_context(3));
        assert_eq!(amended_receipt["status"], "ok", "{amended_receipt}");
        assert!(amended_receipt["data"]["text"]
            .as_str()
            .unwrap()
            .contains("\"post_freeze_amendment_versions\": 1"));
        assert_eq!(amended_receipt["data"]["snapshot_sha256"], preview_hash);
        let wrong_scope = DispatchContext {
            project_id: Uuid::new_v4(),
            ..scoped_context(3)
        };
        assert_eq!(
            handler.execute("protocol.freeze_status", &subject, &wrong_scope)["status"],
            "error",
            "local freeze receipt must never leak across project scope"
        );
        assert_eq!(
            handler.execute("protocol.freeze_receipt", &subject, &wrong_scope)["status"],
            "error",
            "local freeze export must never leak across project scope"
        );

        let tampered = ProjectStore::open(&project_root).unwrap();
        tampered
            .connection()
            .execute(
                "UPDATE protocols SET body_json=?1 WHERE id=?2 AND version=1",
                params![
                    r#"{"design":"experimental","objective":"tampered"}"#,
                    protocol_id
                ],
            )
            .unwrap();
        drop(tampered);
        let invalidated = handler.execute("protocol.freeze_status", &subject, &scoped_context(3));
        assert_eq!(invalidated["status"], "error", "{invalidated}");
        assert!(invalidated["error"]["message"]
            .as_str()
            .unwrap()
            .contains("SHA-256"));
        assert_eq!(
            handler.execute("protocol.freeze_receipt", &subject, &scoped_context(3))["status"],
            "error",
            "tampered baseline content must block an export receipt"
        );
    }
}
