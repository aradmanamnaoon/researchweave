//! Durable trusted-host lifecycle for model-proposed application commands.
//!
//! Model adapters never execute tools. A trusted host first persists an exact
//! command, lets a human approve or deny its canonical fingerprint, and only
//! then asks this bridge to dispatch that same command through CommandRouter.
//! The router performs its own independent approval check and privacy-safe audit.

use researchweave_core::{canonical_sha256, Command, CommandRouter};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};

const MAX_ACTIONS_PER_PROJECT: usize = 5_000;
const MAX_ARGUMENT_BYTES: usize = 64 * 1024;
const MAX_REASON_BYTES: usize = 1_000;
const MAX_STORE_BYTES: usize = 32 * 1024 * 1024;
const SAFE_DOMAINS: &[&str] = &["analysis", "evidence", "library", "ai"];

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum AgentActionError {
    #[error("invalid agent action")]
    Invalid,
    #[error("agent action is not allowed")]
    PermissionDenied,
    #[error("agent action was not found")]
    NotFound,
    #[error("agent action state conflict")]
    Conflict,
    #[error("agent action capacity exceeded")]
    Limit,
    #[error("agent action storage failed")]
    Storage,
    #[error("agent action router failed")]
    Router,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentActionRecord {
    pub id: String,
    pub project_id: String,
    pub operation: String,
    pub domain: String,
    pub effect: String,
    pub fingerprint: String,
    pub approval_fingerprint: Option<String>,
    pub state: String,
    pub command: Command,
    pub denial_reason: Option<String>,
    pub result_status: Option<String>,
    pub result_error_code: Option<String>,
    pub result_sha256: Option<String>,
}

#[derive(Default, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    projects: BTreeMap<String, BTreeMap<String, AgentActionRecord>>,
}

pub struct AgentActionStore {
    file: PathBuf,
    state: Mutex<Snapshot>,
}

fn command_fingerprint(command: &Command) -> Result<String, AgentActionError> {
    let digest = command
        .approval_digest()
        .map_err(|_| AgentActionError::Invalid)?;
    Ok(digest.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn operation_manifest(router: &CommandRouter, operation: &str) -> Option<(String, String)> {
    router.capabilities().into_iter().find_map(|item| {
        if item.get("operation").and_then(Value::as_str) != Some(operation) {
            return None;
        }
        Some((
            item.get("domain")?.as_str()?.to_owned(),
            item.get("effect")?.as_str()?.to_owned(),
        ))
    })
}

fn validate_agent_command(
    router: &CommandRouter,
    command: &Command,
) -> Result<(String, String, String), AgentActionError> {
    command.validate().map_err(|_| AgentActionError::Invalid)?;
    if command.preview
        || command.actor != "researchweave-ai-agent"
        || command.operation.starts_with("assistant.agent.")
        || serde_json::to_vec(&command.arguments)
            .map_err(|_| AgentActionError::Invalid)?
            .len()
            > MAX_ARGUMENT_BYTES
    {
        return Err(AgentActionError::Invalid);
    }
    let (domain, effect) =
        operation_manifest(router, &command.operation).ok_or(AgentActionError::PermissionDenied)?;
    if !SAFE_DOMAINS.contains(&domain.as_str()) {
        return Err(AgentActionError::PermissionDenied);
    }
    let fingerprint = command_fingerprint(command)?;
    Ok((domain, effect, fingerprint))
}

impl AgentActionStore {
    pub fn open(file: &Path) -> Result<Self, AgentActionError> {
        if !file.parent().is_some_and(Path::is_dir) || file.is_symlink() {
            return Err(AgentActionError::Invalid);
        }
        let state = if file.exists() {
            let bytes = fs::read(file).map_err(|_| AgentActionError::Storage)?;
            if bytes.len() > MAX_STORE_BYTES {
                return Err(AgentActionError::Limit);
            }
            serde_json::from_slice(&bytes).map_err(|_| AgentActionError::Storage)?
        } else {
            Snapshot::default()
        };
        Ok(Self {
            file: file.to_path_buf(),
            state: Mutex::new(state),
        })
    }

    fn persist(&self, snapshot: &Snapshot) -> Result<(), AgentActionError> {
        let bytes = serde_json::to_vec(snapshot).map_err(|_| AgentActionError::Storage)?;
        if bytes.len() > MAX_STORE_BYTES {
            return Err(AgentActionError::Limit);
        }
        let temp = self.file.with_extension("pending");
        if temp.is_symlink() {
            return Err(AgentActionError::Storage);
        }
        let mut handle = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|_| AgentActionError::Storage)?;
        let result = (|| {
            handle
                .write_all(&bytes)
                .map_err(|_| AgentActionError::Storage)?;
            handle.sync_all().map_err(|_| AgentActionError::Storage)?;
            drop(handle);
            replace_file(&temp, &self.file)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp);
        }
        result
    }

    fn update<R>(
        &self,
        mutate: impl FnOnce(&mut Snapshot) -> Result<R, AgentActionError>,
    ) -> Result<R, AgentActionError> {
        let mut guard = self.state.lock().map_err(|_| AgentActionError::Storage)?;
        let mut next = guard.clone();
        let result = mutate(&mut next)?;
        self.persist(&next)?;
        *guard = next;
        Ok(result)
    }

    pub fn propose(
        &self,
        router: &CommandRouter,
        command: Command,
    ) -> Result<AgentActionRecord, AgentActionError> {
        let (domain, effect, fingerprint) = validate_agent_command(router, &command)?;
        let project_id = command.project_id.to_string();
        let id = command.request_id.to_string();
        self.update(|snapshot| {
            let actions = snapshot.projects.entry(project_id.clone()).or_default();
            if actions.contains_key(&id) {
                return Err(AgentActionError::Conflict);
            }
            if actions.len() >= MAX_ACTIONS_PER_PROJECT {
                return Err(AgentActionError::Limit);
            }
            let record = AgentActionRecord {
                id: id.clone(),
                project_id: project_id.clone(),
                operation: command.operation.clone(),
                domain,
                effect,
                fingerprint,
                approval_fingerprint: None,
                state: "proposed".into(),
                command,
                denial_reason: None,
                result_status: None,
                result_error_code: None,
                result_sha256: None,
            };
            actions.insert(id, record.clone());
            Ok(record)
        })
    }

    pub fn approve(
        &self,
        project_id: &str,
        action_id: &str,
        expected_fingerprint: &str,
    ) -> Result<AgentActionRecord, AgentActionError> {
        self.update(|snapshot| {
            let record = snapshot
                .projects
                .get_mut(project_id)
                .and_then(|actions| actions.get_mut(action_id))
                .ok_or(AgentActionError::NotFound)?;
            if record.state != "proposed" {
                return Err(AgentActionError::Conflict);
            }
            let current = command_fingerprint(&record.command)?;
            if current != record.fingerprint || current != expected_fingerprint {
                return Err(AgentActionError::PermissionDenied);
            }
            record.state = "approved".into();
            record.approval_fingerprint = Some(current);
            Ok(record.clone())
        })
    }

    pub fn deny(
        &self,
        project_id: &str,
        action_id: &str,
        expected_fingerprint: &str,
        reason: &str,
    ) -> Result<AgentActionRecord, AgentActionError> {
        if reason.trim().is_empty() || reason.len() > MAX_REASON_BYTES {
            return Err(AgentActionError::Invalid);
        }
        self.update(|snapshot| {
            let record = snapshot
                .projects
                .get_mut(project_id)
                .and_then(|actions| actions.get_mut(action_id))
                .ok_or(AgentActionError::NotFound)?;
            if record.state != "proposed" {
                return Err(AgentActionError::Conflict);
            }
            let current = command_fingerprint(&record.command)?;
            if current != record.fingerprint || current != expected_fingerprint {
                return Err(AgentActionError::PermissionDenied);
            }
            record.state = "denied".into();
            record.denial_reason = Some(reason.trim().to_owned());
            Ok(record.clone())
        })
    }

    pub fn execute(
        &self,
        project_id: &str,
        action_id: &str,
        router: &CommandRouter,
        now: f64,
    ) -> Result<Value, AgentActionError> {
        let command = self.update(|snapshot| {
            let record = snapshot
                .projects
                .get_mut(project_id)
                .and_then(|actions| actions.get_mut(action_id))
                .ok_or(AgentActionError::NotFound)?;
            if record.state != "approved"
                || record.approval_fingerprint.as_deref() != Some(record.fingerprint.as_str())
                || command_fingerprint(&record.command)? != record.fingerprint
            {
                return Err(AgentActionError::Conflict);
            }
            let (domain, effect, fingerprint) = validate_agent_command(router, &record.command)?;
            if domain != record.domain
                || effect != record.effect
                || fingerprint != record.fingerprint
            {
                return Err(AgentActionError::PermissionDenied);
            }
            record.state = "running".into();
            Ok(record.command.clone())
        })?;

        let effect = router
            .effect_for(&command.operation)
            .ok_or(AgentActionError::PermissionDenied)?;
        let approval = if effect.requires_approval() {
            Some(
                router
                    .issue_approval(&command, 30, now)
                    .map_err(|_| AgentActionError::Router)?,
            )
        } else {
            None
        };
        let result = router
            .dispatch(&command, approval.as_ref(), now)
            .map_err(|_| AgentActionError::Router)?;
        let status = result
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or("failed")
            .to_owned();
        let error_code = result
            .get("error")
            .and_then(Value::as_object)
            .and_then(|error| error.get("code"))
            .and_then(Value::as_str)
            .map(str::to_owned);
        let result_sha256 = canonical_sha256(&result).map_err(|_| AgentActionError::Storage)?;
        self.update(|snapshot| {
            let record = snapshot
                .projects
                .get_mut(project_id)
                .and_then(|actions| actions.get_mut(action_id))
                .ok_or(AgentActionError::NotFound)?;
            if record.state != "running" {
                return Err(AgentActionError::Conflict);
            }
            record.state = if status == "ok" {
                "completed".into()
            } else {
                "failed".into()
            };
            record.result_status = Some(status);
            record.result_error_code = error_code;
            record.result_sha256 = Some(result_sha256);
            Ok(())
        })?;
        Ok(result)
    }

    /// A process may stop after persisting running state and before recording the
    /// router outcome. Never retry that action automatically because its side
    /// effect may already have happened; require explicit human review.
    pub fn recover_interrupted(
        &self,
        project_id: &str,
    ) -> Result<Vec<AgentActionRecord>, AgentActionError> {
        self.update(|snapshot| {
            let actions = snapshot.projects.entry(project_id.to_owned()).or_default();
            let mut recovered = Vec::new();
            for record in actions.values_mut() {
                if record.state == "running" {
                    record.state = "interrupted_review".into();
                    record.result_status = Some("unknown".into());
                    record.result_error_code = Some("INTERRUPTED".into());
                    recovered.push(record.clone());
                }
            }
            Ok(recovered)
        })
    }

    pub fn timeline(&self, project_id: &str) -> Result<Vec<AgentActionRecord>, AgentActionError> {
        let guard = self.state.lock().map_err(|_| AgentActionError::Storage)?;
        Ok(guard
            .projects
            .get(project_id)
            .map(|actions| actions.values().cloned().collect())
            .unwrap_or_default())
    }
}

#[cfg(windows)]
fn replace_file(source: &Path, dest: &Path) -> Result<(), AgentActionError> {
    if !dest.exists() {
        return fs::rename(source, dest).map_err(|_| AgentActionError::Storage);
    }
    use std::os::windows::ffi::OsStrExt;
    unsafe extern "system" {
        fn ReplaceFileW(
            replaced: *const u16,
            replacement: *const u16,
            backup: *const u16,
            flags: u32,
            exclude: *const u8,
            reserved: *const u8,
        ) -> i32;
    }
    let target = dest
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    let source = source
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    if unsafe {
        ReplaceFileW(
            target.as_ptr(),
            source.as_ptr(),
            std::ptr::null(),
            0,
            std::ptr::null(),
            std::ptr::null(),
        )
    } == 0
    {
        return Err(AgentActionError::Storage);
    }
    Ok(())
}

#[cfg(not(windows))]
fn replace_file(source: &Path, dest: &Path) -> Result<(), AgentActionError> {
    fs::rename(source, dest).map_err(|_| AgentActionError::Storage)
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_core::{
        AuditStore, Authority, Capability, DispatchContext, Effect, OperationHandler,
    };
    use serde_json::json;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use std::time::{SystemTime, UNIX_EPOCH};

    struct RecordingHandler {
        executions: AtomicUsize,
    }

    impl OperationHandler for RecordingHandler {
        fn preview(&self, operation: &str, _: &Value, _: &DispatchContext) -> Value {
            json!({"status":"ok","data":{"operation":operation,"preview":true}})
        }

        fn execute(&self, operation: &str, _: &Value, _: &DispatchContext) -> Value {
            self.executions.fetch_add(1, Ordering::SeqCst);
            json!({"status":"ok","data":{"operation":operation}})
        }
    }

    fn build_router(audit: Arc<AuditStore>, handler: Arc<RecordingHandler>) -> CommandRouter {
        let mut router = CommandRouter::new(Arc::new(Authority::new()), audit);
        router
            .register(
                "evidence",
                handler,
                [
                    Capability::new("evidence.agent_fixture", Effect::LocalWrite, json!({})),
                    Capability::new("evidence.agent_read", Effect::Read, json!({})),
                ],
            )
            .unwrap();
        router
            .register(
                "project",
                Arc::new(RecordingHandler {
                    executions: AtomicUsize::new(0),
                }),
                [Capability::new(
                    "project.delete_fixture",
                    Effect::Irreversible,
                    json!({}),
                )],
            )
            .unwrap();
        router
    }

    fn command(project_id: &str, operation: &str, secret: &str) -> Command {
        let mut command = Command::new(
            project_id.parse().unwrap(),
            operation,
            json!({"content":secret}),
        );
        command.actor = "researchweave-ai-agent".into();
        command
    }

    fn store_path(label: &str) -> (PathBuf, PathBuf) {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let directory = std::env::temp_dir().join(format!(
            "researchweave-agent-actions-{label}-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir(&directory).unwrap();
        let file = directory.join("agent-actions.json");
        (directory, file)
    }

    #[test]
    fn durable_agent_action_requires_exact_human_decision_and_router_approval() {
        let (directory, path) = store_path("approval");
        let audit = Arc::new(AuditStore::memory().unwrap());
        let handler = Arc::new(RecordingHandler {
            executions: AtomicUsize::new(0),
        });
        let router = build_router(Arc::clone(&audit), Arc::clone(&handler));
        let store = AgentActionStore::open(&path).unwrap();
        let project = "11111111-1111-4111-8111-111111111111";

        let proposed = store
            .propose(
                &router,
                command(project, "evidence.agent_fixture", "private-research-text"),
            )
            .unwrap();
        assert_eq!(proposed.state, "proposed");
        assert!(matches!(
            store.approve(project, &proposed.id, &"0".repeat(64)),
            Err(AgentActionError::PermissionDenied)
        ));
        assert_eq!(handler.executions.load(Ordering::SeqCst), 0);

        let approved = store
            .approve(project, &proposed.id, &proposed.fingerprint)
            .unwrap();
        assert_eq!(approved.state, "approved");
        let result = store.execute(project, &proposed.id, &router, 10.0).unwrap();
        assert_eq!(result["status"], "ok");
        assert_eq!(handler.executions.load(Ordering::SeqCst), 1);
        assert!(matches!(
            store.execute(project, &proposed.id, &router, 11.0),
            Err(AgentActionError::Conflict)
        ));
        assert_eq!(handler.executions.load(Ordering::SeqCst), 1);

        let events = audit.events().unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].operation, "evidence.agent_fixture");
        assert_eq!(events[0].effect, "local-write");
        assert!(!serde_json::to_string(&events)
            .unwrap()
            .contains("private-research-text"));

        drop(store);
        let reopened = AgentActionStore::open(&path).unwrap();
        let timeline = reopened.timeline(project).unwrap();
        assert_eq!(timeline.len(), 1);
        assert_eq!(timeline[0].state, "completed");
        assert_eq!(timeline[0].result_status.as_deref(), Some("ok"));
        assert_eq!(timeline[0].result_sha256.as_ref().unwrap().len(), 64);
        drop(reopened);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn denial_unsafe_domains_and_recursive_agent_calls_fail_closed() {
        let (directory, path) = store_path("denial");
        let audit = Arc::new(AuditStore::memory().unwrap());
        let handler = Arc::new(RecordingHandler {
            executions: AtomicUsize::new(0),
        });
        let router = build_router(audit, Arc::clone(&handler));
        let store = AgentActionStore::open(&path).unwrap();
        let project = "22222222-2222-4222-8222-222222222222";

        let proposed = store
            .propose(
                &router,
                command(project, "evidence.agent_fixture", "deny-me"),
            )
            .unwrap();
        let denied = store
            .deny(
                project,
                &proposed.id,
                &proposed.fingerprint,
                "Human rejected this write.",
            )
            .unwrap();
        assert_eq!(denied.state, "denied");
        assert!(matches!(
            store.execute(project, &proposed.id, &router, 1.0),
            Err(AgentActionError::Conflict)
        ));
        assert_eq!(handler.executions.load(Ordering::SeqCst), 0);

        assert!(matches!(
            store.propose(
                &router,
                command(project, "project.delete_fixture", "never-delete")
            ),
            Err(AgentActionError::PermissionDenied)
        ));

        let recursive_handler = Arc::new(RecordingHandler {
            executions: AtomicUsize::new(0),
        });
        let recursive_audit = Arc::new(AuditStore::memory().unwrap());
        let mut recursive_router = CommandRouter::new(Arc::new(Authority::new()), recursive_audit);
        recursive_router
            .register(
                "ai",
                recursive_handler,
                [Capability::new(
                    "assistant.agent.plan",
                    Effect::Read,
                    json!({}),
                )],
            )
            .unwrap();
        assert!(matches!(
            store.propose(
                &recursive_router,
                command(
                    project,
                    "assistant.agent.plan",
                    "untrusted recursive instruction"
                )
            ),
            Err(AgentActionError::Invalid)
        ));
        drop(store);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn interrupted_execution_requires_review_and_never_auto_retries() {
        let (directory, path) = store_path("interrupted");
        let audit = Arc::new(AuditStore::memory().unwrap());
        let handler = Arc::new(RecordingHandler {
            executions: AtomicUsize::new(0),
        });
        let router = build_router(audit, Arc::clone(&handler));
        let store = AgentActionStore::open(&path).unwrap();
        let project = "44444444-4444-4444-8444-444444444444";
        let proposed = store
            .propose(
                &router,
                command(
                    project,
                    "evidence.agent_fixture",
                    "interrupted-private-data",
                ),
            )
            .unwrap();
        store
            .approve(project, &proposed.id, &proposed.fingerprint)
            .unwrap();
        store
            .update(|snapshot| {
                snapshot
                    .projects
                    .get_mut(project)
                    .unwrap()
                    .get_mut(&proposed.id)
                    .unwrap()
                    .state = "running".into();
                Ok(())
            })
            .unwrap();
        drop(store);

        let reopened = AgentActionStore::open(&path).unwrap();
        let recovered = reopened.recover_interrupted(project).unwrap();
        assert_eq!(recovered.len(), 1);
        assert_eq!(recovered[0].state, "interrupted_review");
        assert_eq!(
            recovered[0].result_error_code.as_deref(),
            Some("INTERRUPTED")
        );
        assert!(matches!(
            reopened.execute(project, &proposed.id, &router, 20.0),
            Err(AgentActionError::Conflict)
        ));
        assert_eq!(handler.executions.load(Ordering::SeqCst), 0);
        drop(reopened);
        fs::remove_dir_all(directory).unwrap();
    }
}
