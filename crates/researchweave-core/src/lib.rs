//! Host-owned command contracts, one-use approvals, and observable outcomes.
//! The authority and audit journal must remain within the trusted desktop host.

use hmac::{Hmac, Mac};
use rand::{rngs::OsRng, RngCore};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;
use uuid::Uuid;

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Effect {
    Read,
    LocalWrite,
    CodeExecution,
    ExternalNetwork,
    SensitiveExport,
    Irreversible,
}

impl Effect {
    pub fn requires_approval(self) -> bool {
        self != Self::Read
    }

    pub fn from_manifest(value: &str) -> Result<Self, AuthorizationError> {
        match value {
            "read" => Ok(Self::Read),
            "local-write" | "conditional" => Ok(Self::LocalWrite),
            "code-execution" => Ok(Self::CodeExecution),
            "external-network" => Ok(Self::ExternalNetwork),
            "sensitive-export" | "sensitive-egress" => Ok(Self::SensitiveExport),
            "irreversible" => Ok(Self::Irreversible),
            _ => Err(AuthorizationError::InvalidRequest),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Read => "read",
            Self::LocalWrite => "local-write",
            Self::CodeExecution => "code-execution",
            Self::ExternalNetwork => "external-network",
            Self::SensitiveExport => "sensitive-export",
            Self::Irreversible => "irreversible",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Command {
    pub protocol_version: u8,
    pub request_id: Uuid,
    pub operation: String,
    pub project_id: Uuid,
    pub arguments: Value,
    pub preview: bool,
    pub expected_revision: Option<u64>,
    pub actor: String,
}

impl Command {
    pub fn new(project_id: Uuid, operation: impl Into<String>, arguments: Value) -> Self {
        Self {
            protocol_version: 1,
            request_id: Uuid::new_v4(),
            operation: operation.into(),
            project_id,
            arguments,
            preview: false,
            expected_revision: None,
            actor: "local-user".to_owned(),
        }
    }

    pub fn validate(&self) -> Result<(), AuthorizationError> {
        let valid_op = self.operation.len() >= 3
            && self.operation.len() <= 160
            && self.operation.starts_with(|c: char| c.is_ascii_lowercase())
            && self
                .operation
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"_.-".contains(&c));
        if self.protocol_version != 1
            || !valid_op
            || self.actor.is_empty()
            || self.actor.len() > 120
            || !self.arguments.is_object()
        {
            return Err(AuthorizationError::InvalidRequest);
        }
        Ok(())
    }

    /// Matches Python's approval_payload() field names and canonical JSON bytes.
    pub fn approval_digest(&self) -> Result<[u8; 32], AuthorizationError> {
        self.validate()?;
        let payload = json!({
            "protocol_version": self.protocol_version,
            "request_id": self.request_id.to_string(),
            "operation": self.operation,
            "project_id": self.project_id.to_string(),
            "arguments": self.arguments,
            "expected_revision": self.expected_revision,
            "actor": self.actor
        });
        let canonical =
            serde_json::to_vec(&payload).map_err(|_| AuthorizationError::InvalidRequest)?;
        Ok(Sha256::digest(canonical).into())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Approval {
    pub request_digest: String,
    pub nonce: String,
    pub issued_at: f64,
    pub expires_at: f64,
    pub signature: String,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum AuthorizationError {
    #[error("invalid command request")]
    InvalidRequest,
    #[error("host approval required")]
    ApprovalRequired,
    #[error("approval does not match command or project")]
    ScopeMismatch,
    #[error("approval outside its valid time window")]
    Expired,
    #[error("approval has already been consumed")]
    Replay,
    #[error("invalid approval signature")]
    InvalidSignature,
    #[error("internal approval state unavailable")]
    StateUnavailable,
}

/// Uses the Python HostAuthority signature format: digest|nonce|expires_at:.6f.
pub struct Authority {
    key: [u8; 32],
    used: Mutex<HashSet<String>>,
    max_ttl_seconds: u64,
}

impl Authority {
    pub fn new() -> Self {
        let mut key = [0u8; 32];
        OsRng.fill_bytes(&mut key);
        Self {
            key,
            used: Mutex::new(HashSet::new()),
            max_ttl_seconds: 300,
        }
    }

    fn signature(&self, digest: &str, nonce: &str, expires: f64) -> String {
        let mut mac = HmacSha256::new_from_slice(&self.key).expect("fixed-length HMAC key");
        mac.update(format!("{digest}|{nonce}|{expires:.6}").as_bytes());
        hex::encode(mac.finalize().into_bytes())
    }

    pub fn issue(
        &self,
        request: &Command,
        ttl_seconds: u64,
        now: f64,
    ) -> Result<Approval, AuthorizationError> {
        if request.preview
            || ttl_seconds == 0
            || ttl_seconds > self.max_ttl_seconds
            || !now.is_finite()
        {
            return Err(AuthorizationError::InvalidRequest);
        }
        let digest = hex::encode(request.approval_digest()?);
        let mut nonce = [0u8; 16];
        OsRng.fill_bytes(&mut nonce);
        let nonce = hex::encode(nonce);
        let expires_at = now + ttl_seconds as f64;
        let signature = self.signature(&digest, &nonce, expires_at);
        Ok(Approval {
            request_digest: digest,
            nonce,
            issued_at: now,
            expires_at,
            signature,
        })
    }

    /// Atomic one-use verification; failed signatures do not consume grants.
    pub fn consume(
        &self,
        request: &Command,
        approval: Option<&Approval>,
        now: f64,
    ) -> Result<(), AuthorizationError> {
        let approval = approval.ok_or(AuthorizationError::ApprovalRequired)?;
        let digest = hex::encode(request.approval_digest()?);
        if digest != approval.request_digest {
            return Err(AuthorizationError::ScopeMismatch);
        }
        if !now.is_finite()
            || !approval.issued_at.is_finite()
            || !approval.expires_at.is_finite()
            || now < approval.issued_at
            || now > approval.expires_at
            || approval.expires_at - approval.issued_at > self.max_ttl_seconds as f64
        {
            return Err(AuthorizationError::Expired);
        }
        let signature =
            hex::decode(&approval.signature).map_err(|_| AuthorizationError::InvalidSignature)?;
        let mut mac = HmacSha256::new_from_slice(&self.key).expect("fixed-length HMAC key");
        mac.update(
            format!(
                "{}|{}|{:.6}",
                approval.request_digest, approval.nonce, approval.expires_at
            )
            .as_bytes(),
        );
        mac.verify_slice(&signature)
            .map_err(|_| AuthorizationError::InvalidSignature)?;
        let mut used = self
            .used
            .lock()
            .map_err(|_| AuthorizationError::StateUnavailable)?;
        if !used.insert(approval.nonce.clone()) {
            return Err(AuthorizationError::Replay);
        }
        Ok(())
    }
}

impl Default for Authority {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OutcomeStatus {
    Ok,
    Failed,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEvent {
    pub request_id: Uuid,
    pub project_id: Uuid,
    pub operation: String,
    pub actor: String,
    pub effect: Effect,
    pub status: OutcomeStatus,
    pub error_code: Option<String>,
    pub preview: bool,
}

/// Adapter writes an outcome after dispatch, including denied operations.
pub fn audit_event(
    command: &Command,
    effect: Effect,
    status: OutcomeStatus,
    error_code: Option<String>,
) -> AuditEvent {
    AuditEvent {
        request_id: command.request_id,
        project_id: command.project_id,
        operation: command.operation.clone(),
        actor: command.actor.clone(),
        effect,
        status,
        error_code,
        preview: command.preview,
    }
}

pub fn authorize_effect(
    authority: &Authority,
    command: &Command,
    effect: Effect,
    approval: Option<&Approval>,
    now: f64,
) -> Result<(), AuthorizationError> {
    command.validate()?;
    if !command.preview && effect.requires_approval() {
        authority.consume(command, approval, now)?;
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Capability {
    pub operation: String,
    pub effect: Effect,
    #[serde(default)]
    pub manifest: Value,
}

impl Capability {
    pub fn new(operation: impl Into<String>, effect: Effect, manifest: Value) -> Self {
        Self {
            operation: operation.into(),
            effect,
            manifest,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DispatchContext {
    pub request_id: Uuid,
    pub project_id: Uuid,
    pub actor: String,
    pub expected_revision: Option<u64>,
}

pub trait OperationHandler: Send + Sync {
    fn preview(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value;
    fn execute(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value;
}

struct RegisteredOperation {
    domain: String,
    capability: Capability,
    handler: Arc<dyn OperationHandler>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuditRecord {
    pub sequence: i64,
    pub recorded_at: String,
    pub request_id: String,
    pub project_id: String,
    pub actor: String,
    pub operation: String,
    pub effect: String,
    pub preview: bool,
    pub status: String,
    pub input_sha256: String,
    pub output_sha256: String,
    pub error_code: Option<String>,
}

#[derive(Debug, Error)]
pub enum AuditError {
    #[error("SQLite audit failure: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("audit state unavailable")]
    StateUnavailable,
    #[error("audit result is not serializable")]
    Serialization,
}

pub struct AuditStore {
    connection: Mutex<rusqlite::Connection>,
}

impl AuditStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, AuditError> {
        let path = path.as_ref();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|_| AuditError::StateUnavailable)?;
        }
        let connection = rusqlite::Connection::open(path)?;
        connection.pragma_update(None, "foreign_keys", true)?;
        connection.pragma_update(None, "journal_mode", "WAL")?;
        Self::initialize(connection)
    }

    pub fn memory() -> Result<Self, AuditError> {
        Self::initialize(rusqlite::Connection::open_in_memory()?)
    }

    fn initialize(connection: rusqlite::Connection) -> Result<Self, AuditError> {
        connection.execute_batch(
            "CREATE TABLE IF NOT EXISTS operation_audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                request_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                operation TEXT NOT NULL,
                effect TEXT NOT NULL,
                preview INTEGER NOT NULL,
                status TEXT NOT NULL,
                input_sha256 TEXT NOT NULL,
                output_sha256 TEXT NOT NULL,
                error_code TEXT
            );",
        )?;
        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    pub fn append(
        &self,
        command: &Command,
        effect: Effect,
        result: &Value,
    ) -> Result<i64, AuditError> {
        let status = result
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or("failed");
        let error_code = result
            .get("error")
            .and_then(Value::as_object)
            .and_then(|error| error.get("code"))
            .and_then(Value::as_str);
        let recorded_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| AuditError::StateUnavailable)?
            .as_secs_f64()
            .to_string();
        let input_sha256 = hex::encode(
            command
                .approval_digest()
                .map_err(|_| AuditError::Serialization)?,
        );
        let output_sha256 = canonical_sha256(result)?;
        let connection = self
            .connection
            .lock()
            .map_err(|_| AuditError::StateUnavailable)?;
        connection.execute(
            "INSERT INTO operation_audit (
                recorded_at,request_id,project_id,actor,operation,effect,preview,status,
                input_sha256,output_sha256,error_code
             ) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)",
            rusqlite::params![
                recorded_at,
                command.request_id.to_string(),
                command.project_id.to_string(),
                command.actor,
                command.operation,
                effect.as_str(),
                command.preview,
                status,
                input_sha256,
                output_sha256,
                error_code,
            ],
        )?;
        Ok(connection.last_insert_rowid())
    }

    pub fn events(&self) -> Result<Vec<AuditRecord>, AuditError> {
        let connection = self
            .connection
            .lock()
            .map_err(|_| AuditError::StateUnavailable)?;
        let mut statement = connection.prepare(
            "SELECT sequence,recorded_at,request_id,project_id,actor,operation,effect,
                    preview,status,input_sha256,output_sha256,error_code
             FROM operation_audit ORDER BY sequence",
        )?;
        let rows = statement.query_map([], |row| {
            Ok(AuditRecord {
                sequence: row.get(0)?,
                recorded_at: row.get(1)?,
                request_id: row.get(2)?,
                project_id: row.get(3)?,
                actor: row.get(4)?,
                operation: row.get(5)?,
                effect: row.get(6)?,
                preview: row.get(7)?,
                status: row.get(8)?,
                input_sha256: row.get(9)?,
                output_sha256: row.get(10)?,
                error_code: row.get(11)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>()
            .map_err(AuditError::from)
    }
}

pub fn canonical_sha256(value: &Value) -> Result<String, AuditError> {
    fn sorted(value: &Value) -> Value {
        match value {
            Value::Array(items) => Value::Array(items.iter().map(sorted).collect()),
            Value::Object(map) => {
                let mut keys: Vec<_> = map.keys().collect();
                keys.sort_unstable();
                let mut output = serde_json::Map::new();
                for key in keys {
                    output.insert(key.clone(), sorted(&map[key]));
                }
                Value::Object(output)
            }
            _ => value.clone(),
        }
    }
    let bytes = serde_json::to_vec(&sorted(value)).map_err(|_| AuditError::Serialization)?;
    Ok(hex::encode(Sha256::digest(bytes)))
}

#[derive(Debug, Error)]
pub enum RouterError {
    #[error("duplicate operation {0}")]
    DuplicateOperation(String),
    #[error("invalid operation registration")]
    InvalidRegistration,
    #[error(transparent)]
    Audit(#[from] AuditError),
}

pub struct CommandRouter {
    authority: Arc<Authority>,
    audit: Arc<AuditStore>,
    operations: HashMap<String, RegisteredOperation>,
}

impl CommandRouter {
    pub fn new(authority: Arc<Authority>, audit: Arc<AuditStore>) -> Self {
        Self {
            authority,
            audit,
            operations: HashMap::new(),
        }
    }

    pub fn register(
        &mut self,
        domain: impl Into<String>,
        handler: Arc<dyn OperationHandler>,
        capabilities: impl IntoIterator<Item = Capability>,
    ) -> Result<(), RouterError> {
        let domain = domain.into();
        if domain.trim().is_empty() {
            return Err(RouterError::InvalidRegistration);
        }
        let capabilities: Vec<_> = capabilities.into_iter().collect();
        let mut seen = HashSet::new();
        for capability in &capabilities {
            let probe = Command::new(Uuid::nil(), &capability.operation, json!({}));
            if probe.validate().is_err() || !seen.insert(capability.operation.clone()) {
                return Err(RouterError::InvalidRegistration);
            }
            if self.operations.contains_key(&capability.operation) {
                return Err(RouterError::DuplicateOperation(
                    capability.operation.clone(),
                ));
            }
        }
        for capability in capabilities {
            self.operations.insert(
                capability.operation.clone(),
                RegisteredOperation {
                    domain: domain.clone(),
                    capability,
                    handler: Arc::clone(&handler),
                },
            );
        }
        Ok(())
    }

    pub fn capabilities(&self) -> Vec<Value> {
        let mut entries: Vec<_> = self
            .operations
            .values()
            .map(|registered| {
                let mut manifest = registered.capability.manifest.clone();
                if !manifest.is_object() {
                    manifest = json!({});
                }
                let object = manifest.as_object_mut().expect("object assigned above");
                object.insert(
                    "operation".into(),
                    Value::String(registered.capability.operation.clone()),
                );
                object.insert("domain".into(), Value::String(registered.domain.clone()));
                object.insert(
                    "effect".into(),
                    Value::String(registered.capability.effect.as_str().into()),
                );
                manifest
            })
            .collect();
        entries.sort_by(|left, right| {
            left.get("operation")
                .and_then(Value::as_str)
                .cmp(&right.get("operation").and_then(Value::as_str))
        });
        entries
    }

    pub fn effect_for(&self, operation: &str) -> Option<Effect> {
        self.operations
            .get(operation)
            .map(|registered| registered.capability.effect)
    }

    pub fn issue_approval(
        &self,
        command: &Command,
        ttl_seconds: u64,
        now: f64,
    ) -> Result<Approval, AuthorizationError> {
        let effect = self
            .effect_for(&command.operation)
            .ok_or(AuthorizationError::InvalidRequest)?;
        if !effect.requires_approval() {
            return Err(AuthorizationError::InvalidRequest);
        }
        self.authority.issue(command, ttl_seconds, now)
    }

    pub fn dispatch(
        &self,
        command: &Command,
        approval: Option<&Approval>,
        now: f64,
    ) -> Result<Value, RouterError> {
        if command.validate().is_err() {
            return Ok(failure(
                command,
                "INVALID_INPUT",
                "Invalid operation request",
            ));
        }
        let Some(registered) = self.operations.get(&command.operation) else {
            return Ok(failure(command, "NOT_FOUND", "Unknown operation"));
        };
        let effect = registered.capability.effect;
        if let Err(error) = authorize_effect(&self.authority, command, effect, approval, now) {
            let result = failure(command, "NEEDS_APPROVAL", &error.to_string());
            self.audit.append(command, effect, &result)?;
            return Ok(result);
        }
        let context = DispatchContext {
            request_id: command.request_id,
            project_id: command.project_id,
            actor: command.actor.clone(),
            expected_revision: command.expected_revision,
        };
        let mut result = if command.preview {
            registered
                .handler
                .preview(&command.operation, &command.arguments, &context)
        } else {
            registered
                .handler
                .execute(&command.operation, &command.arguments, &context)
        };
        if !result.is_object() {
            result = json!({"status":"failed","error":{"code":"INTERNAL_ERROR","message":"Handler returned a non-object result"}});
        }
        let object = result.as_object_mut().expect("object assigned above");
        object
            .entry("request_id")
            .or_insert_with(|| Value::String(command.request_id.to_string()));
        object
            .entry("status")
            .or_insert_with(|| Value::String("ok".into()));
        self.audit.append(command, effect, &result)?;
        Ok(result)
    }
}

fn failure(command: &Command, code: &str, message: &str) -> Value {
    json!({
        "request_id": command.request_id.to_string(),
        "status": "failed",
        "data": {},
        "artifacts": [],
        "warnings": [],
        "error": {"code": code, "message": message, "recovery": "Review the request."},
        "provenance": [],
        "impact": {"local_writes": [], "network_hosts": [], "irreversible": false}
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    struct RecordingHandler {
        previews: AtomicUsize,
        executes: AtomicUsize,
    }

    impl RecordingHandler {
        fn new() -> Self {
            Self {
                previews: AtomicUsize::new(0),
                executes: AtomicUsize::new(0),
            }
        }
    }

    impl OperationHandler for RecordingHandler {
        fn preview(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
            self.previews.fetch_add(1, Ordering::SeqCst);
            json!({
                "data": {"mode":"preview","operation":operation,"arguments":arguments,"project_id":context.project_id.to_string()}
            })
        }

        fn execute(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
            self.executes.fetch_add(1, Ordering::SeqCst);
            json!({
                "data": {"mode":"execute","operation":operation,"arguments":arguments,"project_id":context.project_id.to_string()}
            })
        }
    }
    #[test]
    fn approval_replay_and_project_scope_are_rejected() {
        let authority = Authority::new();
        let project = Uuid::new_v4();
        let command = Command::new(project, "analysis.export", json!({"name":"one"}));
        let grant = authority.issue(&command, 30, 1000.0).unwrap();
        let mut other = command.clone();
        other.project_id = Uuid::new_v4();
        assert_eq!(
            authority.consume(&other, Some(&grant), 1001.0),
            Err(AuthorizationError::ScopeMismatch)
        );
        assert_eq!(authority.consume(&command, Some(&grant), 1001.0), Ok(()));
        assert_eq!(
            authority.consume(&command, Some(&grant), 1001.0),
            Err(AuthorizationError::Replay)
        );
    }
    #[test]
    fn expires_and_rejects_tampering() {
        let authority = Authority::new();
        let command = Command::new(Uuid::new_v4(), "ai.request", json!({}));
        let mut approval = authority.issue(&command, 10, 10.0).unwrap();
        assert_eq!(
            authority.consume(&command, Some(&approval), 21.0),
            Err(AuthorizationError::Expired)
        );
        // Always change the HMAC. Replacing its prefix with a fixed string
        // can accidentally preserve a genuine randomly generated signature
        // (a 1-in-256 chance for the old "ff" replacement).
        let original_signature = approval.signature.clone();
        let replacement = if approval.signature.starts_with('0') {
            "1"
        } else {
            "0"
        };
        approval.signature.replace_range(0..1, replacement);
        assert_ne!(approval.signature, original_signature);
        assert_eq!(
            authority.consume(&command, Some(&approval), 12.0),
            Err(AuthorizationError::InvalidSignature)
        );
    }
    #[test]
    fn effects_and_audit_are_explicit() {
        let command = Command::new(Uuid::new_v4(), "evidence.read", json!({}));
        authorize_effect(&Authority::new(), &command, Effect::Read, None, 1.0).unwrap();
        let event = audit_event(&command, Effect::Read, OutcomeStatus::Ok, None);
        assert_eq!(event.project_id, command.project_id);
        assert!(Effect::SensitiveExport.requires_approval());
        assert_eq!(
            Effect::from_manifest("conditional").unwrap(),
            Effect::LocalWrite
        );
        assert_eq!(
            Effect::from_manifest("sensitive-egress").unwrap(),
            Effect::SensitiveExport
        );
    }

    #[test]
    fn router_enforces_effects_previews_and_duplicate_registration() {
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let handler = Arc::new(RecordingHandler::new());
        let mut router = CommandRouter::new(authority, Arc::clone(&audit));
        router
            .register(
                "analysis",
                handler.clone(),
                [
                    Capability::new("analysis.read", Effect::Read, json!({"title":"Read"})),
                    Capability::new(
                        "analysis.write",
                        Effect::LocalWrite,
                        json!({"title":"Write"}),
                    ),
                ],
            )
            .unwrap();
        assert!(matches!(
            router.register(
                "duplicate",
                handler.clone(),
                [Capability::new("analysis.read", Effect::Read, json!({}))]
            ),
            Err(RouterError::DuplicateOperation(_))
        ));

        let read = Command::new(Uuid::new_v4(), "analysis.read", json!({"row": 1}));
        let result = router.dispatch(&read, None, 10.0).unwrap();
        assert_eq!(result["status"], "ok");
        assert_eq!(handler.executes.load(Ordering::SeqCst), 1);

        let mut preview = Command::new(Uuid::new_v4(), "analysis.write", json!({"row": 2}));
        preview.preview = true;
        let result = router.dispatch(&preview, None, 11.0).unwrap();
        assert_eq!(result["status"], "ok");
        assert_eq!(handler.previews.load(Ordering::SeqCst), 1);
        assert_eq!(audit.events().unwrap().len(), 2);
    }

    #[test]
    fn router_binds_approval_to_arguments_project_and_one_use() {
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::memory().unwrap());
        let handler = Arc::new(RecordingHandler::new());
        let mut router = CommandRouter::new(Arc::clone(&authority), Arc::clone(&audit));
        router
            .register(
                "evidence",
                handler.clone(),
                [Capability::new(
                    "evidence.save",
                    Effect::LocalWrite,
                    json!({}),
                )],
            )
            .unwrap();
        let command = Command::new(
            Uuid::new_v4(),
            "evidence.save",
            json!({"content":"top-secret"}),
        );
        let approval = router.issue_approval(&command, 30, 100.0).unwrap();

        let mut changed = command.clone();
        changed.arguments = json!({"content":"changed"});
        let denied = router.dispatch(&changed, Some(&approval), 101.0).unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");
        assert_eq!(handler.executes.load(Ordering::SeqCst), 0);

        let mut other_project = command.clone();
        other_project.project_id = Uuid::new_v4();
        let denied = router
            .dispatch(&other_project, Some(&approval), 101.0)
            .unwrap();
        assert_eq!(denied["error"]["code"], "NEEDS_APPROVAL");

        assert_eq!(
            router.dispatch(&command, Some(&approval), 101.0).unwrap()["status"],
            "ok"
        );
        assert_eq!(handler.executes.load(Ordering::SeqCst), 1);
        let replay = router.dispatch(&command, Some(&approval), 102.0).unwrap();
        assert_eq!(replay["error"]["code"], "NEEDS_APPROVAL");
        assert_eq!(handler.executes.load(Ordering::SeqCst), 1);
        let serialized = serde_json::to_string(&audit.events().unwrap()).unwrap();
        assert!(!serialized.contains("top-secret"));
        assert!(!serialized.contains("changed"));
    }

    #[test]
    fn audit_store_persists_denials_without_argument_payloads() {
        let path = std::env::temp_dir().join(format!(
            "researchweave-audit-{}.sqlite",
            Uuid::new_v4().simple()
        ));
        let authority = Arc::new(Authority::new());
        let audit = Arc::new(AuditStore::open(&path).unwrap());
        let mut router = CommandRouter::new(authority, Arc::clone(&audit));
        router
            .register(
                "sync",
                Arc::new(RecordingHandler::new()),
                [Capability::new(
                    "sync.push",
                    Effect::ExternalNetwork,
                    json!({}),
                )],
            )
            .unwrap();
        let command = Command::new(
            Uuid::new_v4(),
            "sync.push",
            json!({"credential":"never-store-me"}),
        );
        let result = router.dispatch(&command, None, 1.0).unwrap();
        assert_eq!(result["error"]["code"], "NEEDS_APPROVAL");
        drop(router);
        drop(audit);

        let reopened = AuditStore::open(&path).unwrap();
        let events = reopened.events().unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].error_code.as_deref(), Some("NEEDS_APPROVAL"));
        assert_eq!(events[0].effect, "external-network");
        assert_eq!(events[0].input_sha256.len(), 64);
        assert_eq!(events[0].output_sha256.len(), 64);
        assert!(!serde_json::to_string(&events)
            .unwrap()
            .contains("never-store-me"));
        drop(reopened);
        let _ = std::fs::remove_file(&path);
    }
}
