//! Production S3-compatible transport and OS-backed credential references.
//!
//! The sync layer owns revision/conflict/encryption semantics. This crate only
//! provides a concrete object backend plus credential storage and a live
//! conditional-write capability probe. No plaintext project content is stored
//! here; callers pass the already encrypted blobs produced by researchweave-sync.

use aws_config::BehaviorVersion;
use aws_credential_types::Credentials;
use aws_sdk_s3::error::ProvideErrorMetadata;
use aws_sdk_s3::{
    config::{Builder as S3ConfigBuilder, Region},
    primitives::ByteStream,
    Client,
};
use parking_lot::Mutex;
use researchweave_core::{Capability, DispatchContext, Effect, OperationHandler};
use researchweave_crypto::{decrypt_project_archive_bytes, encrypt_project_archive_bytes};
use researchweave_project::verify_archive;
use researchweave_sync::{
    PushResult, RevisionBackend, SyncError, SyncService, Tip, MAX_SYNC_OBJECT_BYTES,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fmt, fs,
    io::Write,
    path::{Component, Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};
use thiserror::Error;
use tokio::runtime::Runtime;
use url::Url;
use uuid::Uuid;
use zeroize::Zeroizing;

const KEYRING_SERVICE: &str = "org.researchweave.s3";
const SYNC_KEYRING_SERVICE: &str = "org.researchweave.sync-encryption";
const DEFAULT_REGION: &str = "us-east-1";
const MAX_OBJECT_BYTES: usize = MAX_SYNC_OBJECT_BYTES;

#[derive(Debug, Error)]
pub enum CloudError {
    #[error("invalid cloud configuration")]
    InvalidConfiguration,
    #[error("credential is missing")]
    MissingCredential,
    #[error("operating-system credential store is unavailable")]
    CredentialStore,
    #[error("S3-compatible service is unavailable")]
    ProviderUnavailable,
    #[error("S3 provider does not enforce the conditional writes required for safe sync")]
    ConditionalWritesUnsupported,
    #[error("S3 request failed ({0:?}): {advice}", advice = .0.advice())]
    Provider(FailureClass),
    #[error("invalid sync request")]
    InvalidSyncInput,
    #[error("remote sync integrity verification failed")]
    SyncIntegrity,
    #[error("project encryption authentication failed")]
    SyncAuthentication,
    #[error("remote sync conflict; the local encrypted revision was preserved")]
    SyncConflict,
    #[error("sync operation was cancelled")]
    SyncCancelled,
    #[error("restore destination already exists")]
    DestinationExists,
    #[error("project archive is unavailable or invalid")]
    ArchiveInvalid,
    #[error("cloud profile storage is unavailable")]
    ProfileStore,
}

impl CloudError {
    fn code(&self) -> &'static str {
        match self {
            Self::InvalidConfiguration | Self::InvalidSyncInput => "INVALID_INPUT",
            Self::MissingCredential => "MISSING_CREDENTIAL",
            Self::CredentialStore => "CREDENTIAL_STORE",
            Self::ProviderUnavailable | Self::Provider(_) => "PROVIDER_UNAVAILABLE",
            Self::ConditionalWritesUnsupported => "CONDITIONAL_WRITES_UNSUPPORTED",
            Self::SyncIntegrity | Self::ArchiveInvalid => "INTEGRITY_FAILURE",
            Self::SyncAuthentication => "AUTHENTICATION_FAILED",
            Self::SyncConflict => "CONFLICT",
            Self::SyncCancelled => "CANCELLED",
            Self::DestinationExists => "CONFLICT",
            Self::ProfileStore => "LOCAL_STORAGE",
        }
    }
}

/// Public, redacted outcome class. Never retain provider response bodies or headers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureClass {
    Authentication,
    Permission,
    Missing,
    Conflict,
    Precondition,
    RateLimited,
    Temporary,
    Timeout,
    Tls,
    Transport,
    ClockSkew,
    Signature,
    Unknown,
}

// Only known metadata and status codes enter this surface. Provider response
// bodies, error messages and endpoint details must never reach the caller.
macro_rules! safe_sdk_error {
    ($error:expr) => {{
        let error = &$error;
        let status = error.raw_response().map(|r| r.status().as_u16());
        let code = error.as_service_error().and_then(|e| e.code());
        CloudError::Provider(classify_failure(status, code, None))
    }};
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RetryDecision {
    Never,
    BoundedBackoff,
}

impl FailureClass {
    pub fn retry(self) -> RetryDecision {
        match self {
            Self::RateLimited | Self::Temporary | Self::Timeout | Self::Transport => {
                RetryDecision::BoundedBackoff
            }
            _ => RetryDecision::Never,
        }
    }
    pub fn advice(self) -> &'static str {
        match self {
            Self::Authentication | Self::Signature => {
                "Check the stored access key, secret, session token and signing settings."
            }
            Self::Permission => "Check bucket permissions for the requested operation.",
            Self::Missing => "Check the bucket and object location.",
            Self::Conflict | Self::Precondition => {
                "Refresh the remote revision; do not overwrite concurrent changes."
            }
            Self::RateLimited => "Retry with bounded exponential backoff.",
            Self::Temporary => {
                "Provider is temporarily unavailable; retry within the configured limit."
            }
            Self::Timeout | Self::Transport => "Check connection and configured request timeout.",
            Self::Tls => "Check the server certificate and trusted TLS chain.",
            Self::ClockSkew => "Synchronize the system clock and retry.",
            Self::Unknown => {
                "Inspect provider health and endpoint settings without exposing credentials."
            }
        }
    }
}

pub fn classify_failure(
    status: Option<u16>,
    code: Option<&str>,
    transport: Option<&str>,
) -> FailureClass {
    // Provider codes win over HTTP status for signature and clock diagnostics.
    match code.unwrap_or("").to_ascii_lowercase().as_str() {
        "requesttimetooskewed" | "requestexpired" | "requestinthefuture" => {
            return FailureClass::ClockSkew
        }
        "signaturedoesnotmatch" | "invalidsignatureexception" | "authorizationheadermalformed" => {
            return FailureClass::Signature
        }
        "expiredtoken" | "invalidtoken" | "invalidaccesskeyid" => {
            return FailureClass::Authentication
        }
        _ => {}
    }
    match status {
        Some(401) => FailureClass::Authentication,
        Some(403) => FailureClass::Permission,
        Some(404) => FailureClass::Missing,
        Some(409) => FailureClass::Conflict,
        Some(412) => FailureClass::Precondition,
        Some(429) => FailureClass::RateLimited,
        Some(500..=599) => FailureClass::Temporary,
        _ => match transport.unwrap_or("").to_ascii_lowercase().as_str() {
            "timeout" | "timedout" => FailureClass::Timeout,
            "tls" | "certificate" | "ssl" => FailureClass::Tls,
            "transport" | "connection" | "dns" => FailureClass::Transport,
            _ => FailureClass::Unknown,
        },
    }
}

pub fn retry_delay(attempt: u32, failure: FailureClass) -> Option<Duration> {
    if attempt >= 3 || failure.retry() == RetryDecision::Never {
        return None;
    }
    Some(Duration::from_millis(
        200_u64.saturating_mul(1 << attempt.saturating_sub(1).min(2)),
    ))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ProviderKind {
    Liara,
    GenericS3,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct S3Profile {
    pub profile_id: String,
    pub provider: ProviderKind,
    pub endpoint: String,
    pub bucket: String,
    pub region: String,
    pub prefix: String,
    pub force_path_style: bool,
}

impl S3Profile {
    /// Liara documents per-bucket endpoints, path-style access, and us-east-1.
    /// The endpoint stays user supplied because Liara exposes it in bucket settings.
    pub fn liara(
        profile_id: impl Into<String>,
        endpoint: impl Into<String>,
        bucket: impl Into<String>,
    ) -> Self {
        Self {
            profile_id: profile_id.into(),
            provider: ProviderKind::Liara,
            endpoint: endpoint.into(),
            bucket: bucket.into(),
            region: DEFAULT_REGION.to_owned(),
            prefix: "researchweave".to_owned(),
            force_path_style: true,
        }
    }

    pub fn validate(&self) -> Result<(), CloudError> {
        if !safe_token(&self.profile_id, 96)
            || !safe_bucket(&self.bucket)
            || !safe_prefix(&self.prefix)
            || self.region.is_empty()
            || self.region.len() > 96
        {
            return Err(CloudError::InvalidConfiguration);
        }
        let endpoint = Url::parse(&self.endpoint).map_err(|_| CloudError::InvalidConfiguration)?;
        let host = endpoint
            .host_str()
            .ok_or(CloudError::InvalidConfiguration)?;
        let local_http =
            endpoint.scheme() == "http" && matches!(host, "localhost" | "127.0.0.1" | "::1");
        if endpoint.scheme() != "https" && !local_http {
            return Err(CloudError::InvalidConfiguration);
        }
        if endpoint.username() != ""
            || endpoint.password().is_some()
            || endpoint.query().is_some()
            || endpoint.fragment().is_some()
        {
            return Err(CloudError::InvalidConfiguration);
        }
        if self.provider == ProviderKind::Liara
            && (!self.force_path_style || self.region != DEFAULT_REGION)
        {
            return Err(CloudError::InvalidConfiguration);
        }
        Ok(())
    }
}

fn safe_token(value: &str, max: usize) -> bool {
    !value.is_empty()
        && value.len() <= max
        && value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._-".contains(c))
}

fn safe_bucket(value: &str) -> bool {
    value.len() >= 3
        && value.len() <= 63
        && value
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || ".-".contains(c))
        && value
            .chars()
            .next()
            .is_some_and(|c| c.is_ascii_alphanumeric())
        && value
            .chars()
            .last()
            .is_some_and(|c| c.is_ascii_alphanumeric())
}

fn safe_prefix(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 160
        && !value.starts_with('/')
        && !value.ends_with('/')
        && value
            .split('/')
            .all(|part| safe_token(part, 96) && part != "." && part != "..")
}

#[derive(Clone, PartialEq, Eq)]
pub struct CredentialBundle {
    pub access_key: String,
    pub secret_key: String,
    pub session_token: Option<String>,
}

impl fmt::Debug for CredentialBundle {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("CredentialBundle { credentials: [REDACTED] }")
    }
}

pub trait SecretStore: Send + Sync {
    fn put(&self, profile_id: &str, credentials: &CredentialBundle) -> Result<(), CloudError>;
    fn get(&self, profile_id: &str) -> Result<CredentialBundle, CloudError>;
    fn delete(&self, profile_id: &str) -> Result<(), CloudError>;
}

#[derive(Debug, Default)]
pub struct OsKeyringStore;

impl OsKeyringStore {
    fn entry(profile_id: &str) -> Result<keyring::Entry, CloudError> {
        if !safe_token(profile_id, 96) {
            return Err(CloudError::InvalidConfiguration);
        }
        keyring::Entry::new(KEYRING_SERVICE, profile_id).map_err(|_| CloudError::CredentialStore)
    }
}

impl SecretStore for OsKeyringStore {
    fn put(&self, profile_id: &str, credentials: &CredentialBundle) -> Result<(), CloudError> {
        if credentials.access_key.is_empty()
            || credentials.secret_key.is_empty()
            || credentials.access_key.len() > 1024
            || credentials.secret_key.len() > 4096
            || credentials
                .session_token
                .as_ref()
                .is_some_and(|token| token.is_empty() || token.len() > 8192)
        {
            return Err(CloudError::InvalidConfiguration);
        }
        let payload = serde_json::to_string(&(
            credentials.access_key.as_str(),
            credentials.secret_key.as_str(),
            credentials.session_token.as_deref(),
        ))
        .map_err(|_| CloudError::CredentialStore)?;
        Self::entry(profile_id)?
            .set_password(&payload)
            .map_err(|_| CloudError::CredentialStore)
    }

    fn get(&self, profile_id: &str) -> Result<CredentialBundle, CloudError> {
        let raw = Self::entry(profile_id)?
            .get_password()
            .map_err(|error| match error {
                keyring::Error::NoEntry => CloudError::MissingCredential,
                _ => CloudError::CredentialStore,
            })?;
        let (access_key, secret_key, session_token): (String, String, Option<String>) =
            serde_json::from_str(&raw).map_err(|_| CloudError::CredentialStore)?;
        Ok(CredentialBundle {
            access_key,
            secret_key,
            session_token,
        })
    }

    fn delete(&self, profile_id: &str) -> Result<(), CloudError> {
        match Self::entry(profile_id)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(_) => Err(CloudError::CredentialStore),
        }
    }
}

#[derive(Default)]
pub struct MemorySecretStore(Mutex<HashMap<String, CredentialBundle>>);

impl SecretStore for MemorySecretStore {
    fn put(&self, profile_id: &str, credentials: &CredentialBundle) -> Result<(), CloudError> {
        if !safe_token(profile_id, 96) {
            return Err(CloudError::InvalidConfiguration);
        }
        self.0
            .lock()
            .insert(profile_id.to_owned(), credentials.clone());
        Ok(())
    }

    fn get(&self, profile_id: &str) -> Result<CredentialBundle, CloudError> {
        self.0
            .lock()
            .get(profile_id)
            .cloned()
            .ok_or(CloudError::MissingCredential)
    }

    fn delete(&self, profile_id: &str) -> Result<(), CloudError> {
        self.0.lock().remove(profile_id);
        Ok(())
    }
}

pub trait SyncSecretStore: Send + Sync {
    fn put(&self, project_id: Uuid, passphrase: &str) -> Result<(), CloudError>;
    fn get(&self, project_id: Uuid) -> Result<Zeroizing<String>, CloudError>;
    fn delete(&self, project_id: Uuid) -> Result<(), CloudError>;
}

#[derive(Debug, Default)]
pub struct OsSyncSecretStore;

impl OsSyncSecretStore {
    fn entry(project_id: Uuid) -> Result<keyring::Entry, CloudError> {
        keyring::Entry::new(SYNC_KEYRING_SERVICE, &project_id.to_string())
            .map_err(|_| CloudError::CredentialStore)
    }
}

fn validate_sync_passphrase(passphrase: &str) -> Result<(), CloudError> {
    if passphrase.chars().count() < 12 || passphrase.len() > 2048 {
        return Err(CloudError::InvalidSyncInput);
    }
    Ok(())
}

impl SyncSecretStore for OsSyncSecretStore {
    fn put(&self, project_id: Uuid, passphrase: &str) -> Result<(), CloudError> {
        validate_sync_passphrase(passphrase)?;
        Self::entry(project_id)?
            .set_password(passphrase)
            .map_err(|_| CloudError::CredentialStore)
    }

    fn get(&self, project_id: Uuid) -> Result<Zeroizing<String>, CloudError> {
        let passphrase = Self::entry(project_id)?
            .get_password()
            .map_err(|error| match error {
                keyring::Error::NoEntry => CloudError::MissingCredential,
                _ => CloudError::CredentialStore,
            })?;
        validate_sync_passphrase(&passphrase)?;
        Ok(Zeroizing::new(passphrase))
    }

    fn delete(&self, project_id: Uuid) -> Result<(), CloudError> {
        match Self::entry(project_id)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(_) => Err(CloudError::CredentialStore),
        }
    }
}

#[derive(Default)]
pub struct MemorySyncSecretStore(Mutex<HashMap<Uuid, String>>);

impl SyncSecretStore for MemorySyncSecretStore {
    fn put(&self, project_id: Uuid, passphrase: &str) -> Result<(), CloudError> {
        validate_sync_passphrase(passphrase)?;
        self.0.lock().insert(project_id, passphrase.to_owned());
        Ok(())
    }

    fn get(&self, project_id: Uuid) -> Result<Zeroizing<String>, CloudError> {
        self.0
            .lock()
            .get(&project_id)
            .cloned()
            .map(Zeroizing::new)
            .ok_or(CloudError::MissingCredential)
    }

    fn delete(&self, project_id: Uuid) -> Result<(), CloudError> {
        self.0.lock().remove(&project_id);
        Ok(())
    }
}

/// Host-dispatchable cloud controls. The host registers these capabilities and
/// enforces approvals; this handler never grants its own authority.
pub struct CloudOperationHandler {
    profiles: Mutex<HashMap<String, S3Profile>>,
    profile_path: Option<PathBuf>,
    secrets: Arc<dyn SecretStore>,
    sync_secrets: Arc<dyn SyncSecretStore>,
    verified: Mutex<VerifiedBackends<S3Backend>>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProfileFile {
    version: u8,
    profiles: Vec<S3Profile>,
}

fn load_profiles(path: &Path) -> Result<HashMap<String, S3Profile>, CloudError> {
    if !path.exists() {
        return Ok(HashMap::new());
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| CloudError::ProfileStore)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > 1024 * 1024 {
        return Err(CloudError::ProfileStore);
    }
    let file: ProfileFile =
        serde_json::from_slice(&fs::read(path).map_err(|_| CloudError::ProfileStore)?)
            .map_err(|_| CloudError::ProfileStore)?;
    if file.version != 1 || file.profiles.len() > 64 {
        return Err(CloudError::ProfileStore);
    }
    let mut profiles = HashMap::new();
    for profile in file.profiles {
        profile.validate()?;
        if profiles
            .insert(profile.profile_id.clone(), profile)
            .is_some()
        {
            return Err(CloudError::ProfileStore);
        }
    }
    Ok(profiles)
}

fn persist_profiles(path: &Path, profiles: &HashMap<String, S3Profile>) -> Result<(), CloudError> {
    let parent = path.parent().ok_or(CloudError::ProfileStore)?;
    fs::create_dir_all(parent).map_err(|_| CloudError::ProfileStore)?;
    let parent_metadata = fs::symlink_metadata(parent).map_err(|_| CloudError::ProfileStore)?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(CloudError::ProfileStore);
    }
    let mut values: Vec<_> = profiles.values().cloned().collect();
    values.sort_by(|left, right| left.profile_id.cmp(&right.profile_id));
    let bytes = serde_json::to_vec_pretty(&ProfileFile {
        version: 1,
        profiles: values,
    })
    .map_err(|_| CloudError::ProfileStore)?;
    if bytes.len() > 1024 * 1024 {
        return Err(CloudError::ProfileStore);
    }
    let mut staged =
        tempfile::NamedTempFile::new_in(parent).map_err(|_| CloudError::ProfileStore)?;
    staged
        .write_all(&bytes)
        .and_then(|_| staged.write_all(b"\n"))
        .and_then(|_| staged.as_file().sync_all())
        .map_err(|_| CloudError::ProfileStore)?;
    staged.persist(path).map_err(|_| CloudError::ProfileStore)?;
    Ok(())
}

#[derive(Default)]
struct VerifiedBackends<B> {
    entries: HashMap<String, Arc<B>>,
    epochs: HashMap<String, u64>,
}

impl<B> VerifiedBackends<B> {
    fn revoke(&mut self, profile_id: &str) {
        self.entries.remove(profile_id);
        let epoch = self.epochs.entry(profile_id.to_owned()).or_default();
        *epoch = epoch.wrapping_add(1);
    }
    fn epoch(&self, profile_id: &str) -> u64 {
        self.epochs.get(profile_id).copied().unwrap_or(0)
    }
    fn retain_if_current(&mut self, profile_id: String, epoch: u64, backend: Arc<B>) -> bool {
        if self.epoch(&profile_id) != epoch {
            return false;
        }
        self.entries.insert(profile_id, backend);
        true
    }
    fn get(&self, profile_id: &str) -> Option<Arc<B>> {
        self.entries.get(profile_id).cloned()
    }
}

struct BorrowedBackend<'a>(&'a dyn RevisionBackend);

impl RevisionBackend for BorrowedBackend<'_> {
    fn tip(&self, project_id: &str) -> Result<Tip, SyncError> {
        self.0.tip(project_id)
    }
    fn put_immutable(&self, project_id: &str, key: &str, data: &[u8]) -> Result<(), SyncError> {
        self.0.put_immutable(project_id, key, data)
    }
    fn get_immutable(&self, project_id: &str, key: &str) -> Result<Vec<u8>, SyncError> {
        self.0.get_immutable(project_id, key)
    }
    fn compare_and_swap_tip(
        &self,
        project_id: &str,
        expected: &Tip,
        new_revision: &str,
    ) -> Result<(), SyncError> {
        self.0
            .compare_and_swap_tip(project_id, expected, new_revision)
    }
}

fn read_project_sync(
    backend: &dyn RevisionBackend,
    project_id: Uuid,
    operation: &str,
    arguments: &Value,
) -> Result<Value, SyncError> {
    let service = SyncService::new(
        BorrowedBackend(backend),
        project_id.to_string(),
        "cloud-reader",
    )?;
    match operation {
        "cloud.sync.tip" => {
            let tip = service.tip()?;
            Ok(json!({"project_id":project_id,"revision":tip.revision,"version":tip.version}))
        }
        "cloud.sync.history" => {
            let limit = arguments.get("limit").and_then(Value::as_u64).unwrap_or(20);
            if !(1..=100).contains(&limit) {
                return Err(SyncError::InvalidInput);
            }
            let history = service.history(limit as usize)?;
            Ok(json!({"project_id":project_id,"revisions":history}))
        }
        _ => Err(SyncError::InvalidInput),
    }
}

fn map_sync_error(error: SyncError) -> CloudError {
    match error {
        SyncError::InvalidInput => CloudError::InvalidSyncInput,
        SyncError::Integrity | SyncError::NotFound => CloudError::SyncIntegrity,
        SyncError::Conflict => CloudError::SyncConflict,
        SyncError::Cancelled => CloudError::SyncCancelled,
        SyncError::DestinationExists => CloudError::DestinationExists,
        SyncError::Crypto(_) => CloudError::SyncAuthentication,
        SyncError::Backend | SyncError::Io(_) => CloudError::ProviderUnavailable,
    }
}

fn archive_input_path(arguments: &Value) -> Result<PathBuf, CloudError> {
    let path = arguments
        .get("archive")
        .and_then(Value::as_str)
        .map(PathBuf::from)
        .ok_or(CloudError::InvalidSyncInput)?;
    if !path.is_absolute()
        || path.extension().and_then(|part| part.to_str()) != Some("rwproj")
        || path.file_name().is_none()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err(CloudError::InvalidSyncInput);
    }
    let metadata = fs::symlink_metadata(&path).map_err(|_| CloudError::ArchiveInvalid)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(CloudError::ArchiveInvalid);
    }
    Ok(path)
}

fn archive_destination_path(arguments: &Value) -> Result<PathBuf, CloudError> {
    let path = arguments
        .get("destination")
        .and_then(Value::as_str)
        .map(PathBuf::from)
        .ok_or(CloudError::InvalidSyncInput)?;
    if !path.is_absolute()
        || path.extension().and_then(|part| part.to_str()) != Some("rwproj")
        || path.file_name().is_none()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir))
        || path.exists()
    {
        return Err(if path.exists() {
            CloudError::DestinationExists
        } else {
            CloudError::InvalidSyncInput
        });
    }
    let parent = path.parent().ok_or(CloudError::InvalidSyncInput)?;
    let metadata = fs::symlink_metadata(parent).map_err(|_| CloudError::InvalidSyncInput)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(CloudError::InvalidSyncInput);
    }
    Ok(path)
}

fn push_project_archive(
    backend: &dyn RevisionBackend,
    project_id: Uuid,
    project_revision: i64,
    archive: &[u8],
    passphrase: &str,
    expected_revision: Option<&str>,
    device_id: &str,
) -> Result<Value, CloudError> {
    let service = SyncService::new(
        BorrowedBackend(backend),
        project_id.to_string(),
        device_id.to_owned(),
    )
    .map_err(map_sync_error)?;
    let encrypted = encrypt_project_archive_bytes(
        &project_id.to_string(),
        project_revision,
        archive,
        passphrase,
    )
    .map_err(|error| map_sync_error(SyncError::Crypto(error)))?;
    let plaintext_sha256 = hex::encode(Sha256::digest(archive));
    match service
        .push_sealed(&encrypted, &plaintext_sha256, expected_revision)
        .map_err(map_sync_error)?
    {
        PushResult::Advanced(revision) => Ok(json!({
            "project_id":project_id,
            "advanced":true,
            "conflict":false,
            "revision":revision.revision,
            "predecessor":revision.predecessor,
            "encrypted_sha256":revision.encrypted_sha256,
            "plaintext_sha256":revision.plaintext_sha256,
            "size":revision.size,
            "device_id":revision.device_id
        })),
        PushResult::Conflict(conflict) => Ok(json!({
            "project_id":project_id,
            "advanced":false,
            "conflict":true,
            "expected_revision":conflict.expected_revision,
            "actual_revision":conflict.actual_revision,
            "preserved_revision":conflict.preserved.revision,
            "plaintext_sha256":conflict.preserved.plaintext_sha256
        })),
    }
}

fn pull_project_archive(
    backend: &dyn RevisionBackend,
    project_id: Uuid,
    revision: &str,
    passphrase: &str,
) -> Result<Vec<u8>, CloudError> {
    let service = SyncService::new(
        BorrowedBackend(backend),
        project_id.to_string(),
        "cloud-reader",
    )
    .map_err(map_sync_error)?;
    let (manifest, encrypted) = service.pull_encrypted(revision).map_err(map_sync_error)?;
    if encrypted.starts_with(b"RWPENC1\n") {
        let (archive, metadata) = decrypt_project_archive_bytes(&encrypted, passphrase)
            .map_err(|error| map_sync_error(SyncError::Crypto(error)))?;
        if metadata.project_id != project_id.to_string()
            || metadata.plaintext_sha256 != manifest.plaintext_sha256
            || hex::encode(Sha256::digest(&archive)) != manifest.plaintext_sha256
        {
            return Err(CloudError::SyncIntegrity);
        }
        Ok(archive)
    } else {
        // Legacy revisions used the smaller RWENC1 envelope. Keep them
        // readable so upgrading the app does not orphan remote history.
        service.pull(revision, passphrase).map_err(map_sync_error)
    }
}

fn persist_verified_archive(
    project_id: Uuid,
    bytes: &[u8],
    destination: &Path,
) -> Result<Value, CloudError> {
    let parent = destination.parent().ok_or(CloudError::InvalidSyncInput)?;
    let mut staged =
        tempfile::NamedTempFile::new_in(parent).map_err(|_| CloudError::ArchiveInvalid)?;
    staged
        .write_all(bytes)
        .and_then(|_| staged.as_file().sync_all())
        .map_err(|_| CloudError::ArchiveInvalid)?;
    let verified = verify_archive(staged.path()).map_err(|_| CloudError::ArchiveInvalid)?;
    if verified.project_id != project_id.to_string() {
        return Err(CloudError::ArchiveInvalid);
    }
    staged.persist_noclobber(destination).map_err(|error| {
        if error.error.kind() == std::io::ErrorKind::AlreadyExists {
            CloudError::DestinationExists
        } else {
            CloudError::ArchiveInvalid
        }
    })?;
    Ok(json!({
        "project_id":verified.project_id,
        "project_revision":verified.project_revision,
        "manifest_sha256":verified.manifest_sha256,
        "files":verified.files,
        "expanded_bytes":verified.expanded_bytes,
        "destination":destination,
        "verified":true
    }))
}

impl CloudOperationHandler {
    pub fn new(secrets: Arc<dyn SecretStore>) -> Self {
        Self::new_with_sync_secrets(secrets, Arc::new(OsSyncSecretStore))
    }

    pub fn new_with_sync_secrets(
        secrets: Arc<dyn SecretStore>,
        sync_secrets: Arc<dyn SyncSecretStore>,
    ) -> Self {
        Self {
            profiles: Mutex::new(HashMap::new()),
            profile_path: None,
            secrets,
            sync_secrets,
            verified: Mutex::new(VerifiedBackends {
                entries: HashMap::new(),
                epochs: HashMap::new(),
            }),
        }
    }

    pub fn with_profile_path(
        secrets: Arc<dyn SecretStore>,
        sync_secrets: Arc<dyn SyncSecretStore>,
        profile_path: PathBuf,
    ) -> Result<Self, CloudError> {
        let profiles = load_profiles(&profile_path)?;
        Ok(Self {
            profiles: Mutex::new(profiles),
            profile_path: Some(profile_path),
            secrets,
            sync_secrets,
            verified: Mutex::new(VerifiedBackends {
                entries: HashMap::new(),
                epochs: HashMap::new(),
            }),
        })
    }

    fn save_profiles(&self, profiles: &HashMap<String, S3Profile>) -> Result<(), CloudError> {
        if let Some(path) = self.profile_path.as_deref() {
            persist_profiles(path, profiles)?;
        }
        Ok(())
    }

    pub fn capabilities() -> Vec<Capability> {
        [
            ("cloud.profile.validate", Effect::Read),
            ("cloud.profile.list", Effect::Read),
            ("cloud.profile.configure", Effect::LocalWrite),
            ("cloud.profile.disconnect", Effect::LocalWrite),
            ("cloud.credentials.store", Effect::LocalWrite),
            ("cloud.credentials.delete", Effect::LocalWrite),
            ("cloud.encryption.store", Effect::LocalWrite),
            ("cloud.encryption.delete", Effect::LocalWrite),
            ("cloud.connection.verify", Effect::ExternalNetwork),
            ("cloud.conditional.probe", Effect::ExternalNetwork),
            ("cloud.sync.tip", Effect::ExternalNetwork),
            ("cloud.sync.history", Effect::ExternalNetwork),
            ("cloud.sync.push", Effect::ExternalNetwork),
            ("cloud.sync.pull", Effect::ExternalNetwork),
        ]
        .into_iter()
        .map(|(name, effect)| {
            let sensitive_arguments = match name {
                "cloud.credentials.store" => json!(["access_key", "secret_key", "session_token"]),
                "cloud.encryption.store" => json!(["passphrase"]),
                _ => json!([]),
            };
            Capability::new(
                name,
                effect,
                json!({
                    "domain":"cloud",
                    "approval_required":effect.requires_approval(),
                    "project_scoped":name.starts_with("cloud.sync.")
                        || name.starts_with("cloud.encryption."),
                    "sensitive_arguments":sensitive_arguments
                }),
            )
        })
        .collect()
    }

    fn run(
        &self,
        operation: &str,
        arguments: &Value,
        context: &DispatchContext,
        preview: bool,
    ) -> Value {
        let result: Result<Value, CloudError> = (|| match operation {
            "cloud.profile.list" => {
                let mut profiles: Vec<_> = self
                    .profiles
                    .lock()
                    .values()
                    .map(|profile| {
                        json!({
                            "profile_id":profile.profile_id,
                            "provider":profile.provider,
                            "endpoint":profile.endpoint,
                            "region":profile.region,
                            "bucket":profile.bucket,
                            "prefix":profile.prefix,
                            "path_style":profile.force_path_style,
                            "credentials_present":self.secrets.get(&profile.profile_id).is_ok()
                        })
                    })
                    .collect();
                profiles.sort_by(|left, right| {
                    left["profile_id"]
                        .as_str()
                        .cmp(&right["profile_id"].as_str())
                });
                Ok(json!({"profiles":profiles}))
            }
            "cloud.profile.validate" | "cloud.profile.configure" => {
                let profile: S3Profile = serde_json::from_value(arguments.clone())
                    .map_err(|_| CloudError::InvalidConfiguration)?;
                profile.validate()?;
                if !preview && operation == "cloud.profile.configure" {
                    self.verified.lock().revoke(&profile.profile_id);
                    let mut profiles = self.profiles.lock();
                    let mut updated = profiles.clone();
                    updated.insert(profile.profile_id.clone(), profile.clone());
                    self.save_profiles(&updated)?;
                    *profiles = updated;
                }
                Ok(
                    json!({"profile_id":profile.profile_id, "provider":profile.provider, "validated":true}),
                )
            }
            "cloud.profile.disconnect" => {
                let id = arguments
                    .get("profile_id")
                    .and_then(Value::as_str)
                    .filter(|id| safe_token(id, 96))
                    .ok_or(CloudError::InvalidConfiguration)?;
                if !preview {
                    self.verified.lock().revoke(id);
                    let mut profiles = self.profiles.lock();
                    let mut updated = profiles.clone();
                    updated.remove(id);
                    self.save_profiles(&updated)?;
                    *profiles = updated;
                }
                Ok(json!({
                    "profile_id":id,
                    "disconnected":!preview,
                    "credentials_deleted":false
                }))
            }
            "cloud.credentials.store" | "cloud.credentials.delete" => {
                let id = arguments
                    .get("profile_id")
                    .and_then(Value::as_str)
                    .filter(|id| safe_token(id, 96))
                    .ok_or(CloudError::InvalidConfiguration)?;
                if operation == "cloud.credentials.store" {
                    let access = arguments
                        .get("access_key")
                        .and_then(Value::as_str)
                        .ok_or(CloudError::InvalidConfiguration)?;
                    let secret = arguments
                        .get("secret_key")
                        .and_then(Value::as_str)
                        .ok_or(CloudError::InvalidConfiguration)?;
                    let token = arguments
                        .get("session_token")
                        .and_then(Value::as_str)
                        .map(str::to_owned);
                    let bundle = CredentialBundle {
                        access_key: access.to_owned(),
                        secret_key: secret.to_owned(),
                        session_token: token,
                    };
                    if !preview {
                        self.verified.lock().revoke(id);
                        self.secrets.put(id, &bundle)?;
                    }
                } else if !preview {
                    self.verified.lock().revoke(id);
                    self.secrets.delete(id)?;
                }
                Ok(
                    json!({"profile_id":id, "credential_action": if operation == "cloud.credentials.store" {"store"} else {"delete"}}),
                )
            }
            "cloud.encryption.store" | "cloud.encryption.delete" => {
                if operation == "cloud.encryption.store" {
                    let passphrase = arguments
                        .get("passphrase")
                        .and_then(Value::as_str)
                        .ok_or(CloudError::InvalidSyncInput)?;
                    validate_sync_passphrase(passphrase)?;
                    if !preview {
                        self.sync_secrets.put(context.project_id, passphrase)?;
                    }
                } else if !preview {
                    self.sync_secrets.delete(context.project_id)?;
                }
                Ok(json!({
                    "project_id":context.project_id,
                    "encryption_action":if operation == "cloud.encryption.store" {"store"} else {"delete"},
                    "secret_persisted":!preview && operation == "cloud.encryption.store"
                }))
            }
            "cloud.connection.verify" | "cloud.conditional.probe" => {
                let id = arguments
                    .get("profile_id")
                    .and_then(Value::as_str)
                    .ok_or(CloudError::InvalidConfiguration)?;
                if preview {
                    if !self.profiles.lock().contains_key(id) {
                        return Err(CloudError::InvalidConfiguration);
                    }
                    return Ok(
                        json!({"profile_id":id,"network_request":true,"probe_writes_temporary_object":operation == "cloud.conditional.probe"}),
                    );
                }
                let (profile, probe_epoch) = if operation == "cloud.conditional.probe" {
                    let mut verified = self.verified.lock();
                    let profile = self
                        .profiles
                        .lock()
                        .get(id)
                        .cloned()
                        .ok_or(CloudError::InvalidConfiguration)?;
                    verified.revoke(id);
                    (profile, Some(verified.epoch(id)))
                } else {
                    (
                        self.profiles
                            .lock()
                            .get(id)
                            .cloned()
                            .ok_or(CloudError::InvalidConfiguration)?,
                        None,
                    )
                };
                let backend = Arc::new(S3Backend::connect(profile, self.secrets.as_ref())?);
                if operation == "cloud.connection.verify" {
                    backend.test_connection()?;
                } else {
                    backend.verify_conditional_writes()?;
                    if !self.verified.lock().retain_if_current(
                        id.to_owned(),
                        probe_epoch.expect("probe epoch"),
                        Arc::clone(&backend),
                    ) {
                        return Err(CloudError::ConditionalWritesUnsupported);
                    }
                }
                Ok(
                    json!({"profile_id":id,"connected":true,"conditional_writes_verified":backend.conditional_writes_verified()}),
                )
            }
            "cloud.sync.tip" | "cloud.sync.history" => {
                let id = arguments
                    .get("profile_id")
                    .and_then(Value::as_str)
                    .filter(|id| safe_token(id, 96))
                    .ok_or(CloudError::InvalidConfiguration)?;
                if preview {
                    return Ok(
                        json!({"profile_id":id,"project_id":context.project_id,"network_request":true,"read_only":true}),
                    );
                }
                let backend = self
                    .verified
                    .lock()
                    .get(id)
                    .ok_or(CloudError::ConditionalWritesUnsupported)?;
                if !backend.conditional_writes_verified() {
                    return Err(CloudError::ConditionalWritesUnsupported);
                }
                read_project_sync(backend.as_ref(), context.project_id, operation, arguments)
                    .map_err(|_| CloudError::ProviderUnavailable)
            }
            "cloud.sync.push" => {
                let id = arguments
                    .get("profile_id")
                    .and_then(Value::as_str)
                    .filter(|id| safe_token(id, 96))
                    .ok_or(CloudError::InvalidConfiguration)?;
                let device_id = arguments
                    .get("device_id")
                    .and_then(Value::as_str)
                    .filter(|device| safe_token(device, 128))
                    .ok_or(CloudError::InvalidSyncInput)?;
                let expected_revision = arguments.get("expected_revision").and_then(Value::as_str);
                if expected_revision.is_some_and(|revision| !safe_token(revision, 128)) {
                    return Err(CloudError::InvalidSyncInput);
                }
                let archive = archive_input_path(arguments)?;
                let verified_archive =
                    verify_archive(&archive).map_err(|_| CloudError::ArchiveInvalid)?;
                if verified_archive.project_id != context.project_id.to_string() {
                    return Err(CloudError::ArchiveInvalid);
                }
                if preview {
                    return Ok(json!({
                        "profile_id":id,
                        "project_id":context.project_id,
                        "archive_manifest_sha256":verified_archive.manifest_sha256,
                        "project_revision":verified_archive.project_revision,
                        "expected_revision":expected_revision,
                        "device_id":device_id,
                        "network_request":true,
                        "plaintext_uploaded":false
                    }));
                }
                let backend = self
                    .verified
                    .lock()
                    .get(id)
                    .ok_or(CloudError::ConditionalWritesUnsupported)?;
                if !backend.conditional_writes_verified() {
                    return Err(CloudError::ConditionalWritesUnsupported);
                }
                let passphrase = self.sync_secrets.get(context.project_id)?;
                let bytes = fs::read(&archive).map_err(|_| CloudError::ArchiveInvalid)?;
                push_project_archive(
                    backend.as_ref(),
                    context.project_id,
                    verified_archive.project_revision,
                    &bytes,
                    &passphrase,
                    expected_revision,
                    device_id,
                )
            }
            "cloud.sync.pull" => {
                let id = arguments
                    .get("profile_id")
                    .and_then(Value::as_str)
                    .filter(|id| safe_token(id, 96))
                    .ok_or(CloudError::InvalidConfiguration)?;
                let revision = arguments
                    .get("revision")
                    .and_then(Value::as_str)
                    .filter(|revision| safe_token(revision, 128))
                    .ok_or(CloudError::InvalidSyncInput)?;
                let destination = archive_destination_path(arguments)?;
                if preview {
                    return Ok(json!({
                        "profile_id":id,
                        "project_id":context.project_id,
                        "revision":revision,
                        "destination":destination,
                        "network_request":true,
                        "create_new":true
                    }));
                }
                let backend = self
                    .verified
                    .lock()
                    .get(id)
                    .ok_or(CloudError::ConditionalWritesUnsupported)?;
                if !backend.conditional_writes_verified() {
                    return Err(CloudError::ConditionalWritesUnsupported);
                }
                let passphrase = self.sync_secrets.get(context.project_id)?;
                let bytes = pull_project_archive(
                    backend.as_ref(),
                    context.project_id,
                    revision,
                    &passphrase,
                )?;
                let mut receipt =
                    persist_verified_archive(context.project_id, &bytes, &destination)?;
                if let Some(object) = receipt.as_object_mut() {
                    object.insert("revision".into(), Value::String(revision.to_owned()));
                }
                Ok(receipt)
            }
            _ => Err(CloudError::InvalidConfiguration),
        })();
        match result {
            Ok(value) => json!({"ok":true,"status":"ok","preview":preview,"result":value}),
            Err(error) => json!({
                "ok":false,
                "status":"failed",
                "preview":preview,
                "result":{},
                "error":{"code":error.code(),"message":error.to_string()}
            }),
        }
    }
}

impl OperationHandler for CloudOperationHandler {
    fn preview(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        self.run(operation, arguments, context, true)
    }

    fn execute(&self, operation: &str, arguments: &Value, context: &DispatchContext) -> Value {
        self.run(operation, arguments, context, false)
    }
}

#[derive(Clone)]
struct ObservedTip {
    tip: Tip,
    etag: Option<String>,
}

pub struct S3Backend {
    runtime: Arc<Runtime>,
    client: Client,
    profile: S3Profile,
    observed_tips: Mutex<HashMap<String, ObservedTip>>,
    conditional_writes_verified: AtomicBool,
    probe_lock: Mutex<()>,
}

impl S3Backend {
    pub fn connect(profile: S3Profile, secrets: &dyn SecretStore) -> Result<Self, CloudError> {
        profile.validate()?;
        let credentials = secrets.get(&profile.profile_id)?;
        if credentials.access_key.is_empty() || credentials.secret_key.is_empty() {
            return Err(CloudError::MissingCredential);
        }
        let runtime = Arc::new(Runtime::new().map_err(|_| CloudError::ProviderUnavailable)?);
        let region = Region::new(profile.region.clone());
        let creds = Credentials::new(
            credentials.access_key,
            credentials.secret_key,
            credentials.session_token,
            None,
            "researchweave-os-keyring",
        );
        let shared = runtime.block_on(
            aws_config::defaults(BehaviorVersion::latest())
                .region(region.clone())
                .credentials_provider(creds)
                .load(),
        );
        let config = S3ConfigBuilder::from(&shared)
            .region(region)
            .endpoint_url(profile.endpoint.clone())
            .force_path_style(profile.force_path_style)
            .retry_config(aws_sdk_s3::config::retry::RetryConfig::standard().with_max_attempts(3))
            .timeout_config(
                aws_sdk_s3::config::timeout::TimeoutConfig::builder()
                    .operation_timeout(Duration::from_secs(25))
                    .build(),
            )
            .build();
        Ok(Self {
            runtime,
            client: Client::from_conf(config),
            profile,
            observed_tips: Mutex::new(HashMap::new()),
            conditional_writes_verified: AtomicBool::new(false),
            probe_lock: Mutex::new(()),
        })
    }

    fn object_key(&self, project_id: &str, key: &str) -> Result<String, SyncError> {
        if !safe_token(project_id, 128)
            || key.is_empty()
            || key.len() > 512
            || key.starts_with('/')
            || key
                .split('/')
                .any(|part| part.is_empty() || part == "." || part == "..")
        {
            return Err(SyncError::InvalidInput);
        }
        Ok(format!(
            "{}/projects/{project_id}/{key}",
            self.profile.prefix
        ))
    }

    fn tip_key(&self, project_id: &str) -> Result<String, SyncError> {
        self.object_key(project_id, "tip.json")
    }

    /// Check bucket connectivity without surfacing raw provider errors or secrets.
    pub fn test_connection(&self) -> Result<(), CloudError> {
        self.runtime.block_on(async {
            self.client
                .head_bucket()
                .bucket(&self.profile.bucket)
                .send()
                .await
                .map(|_| ())
                .map_err(|error| safe_sdk_error!(error))
        })
    }

    /// List revision identifiers within the configured profile and project namespace.
    /// Pagination beyond the caller's explicit bound is intentionally not automatic.
    pub fn list_revision_ids(
        &self,
        project_id: &str,
        limit: i32,
    ) -> Result<Vec<String>, SyncError> {
        if !(1..=1000).contains(&limit) || !safe_token(project_id, 128) {
            return Err(SyncError::InvalidInput);
        }
        let prefix = format!("{}/projects/{project_id}/manifests/", self.profile.prefix);
        let objects = self
            .runtime
            .block_on(
                self.client
                    .list_objects_v2()
                    .bucket(&self.profile.bucket)
                    .prefix(&prefix)
                    .max_keys(limit)
                    .send(),
            )
            .map_err(|_| SyncError::Backend)?;
        Ok(objects
            .contents()
            .iter()
            .filter_map(|entry| entry.key())
            .filter_map(|key| key.strip_prefix(&prefix))
            .filter_map(|name| name.strip_suffix(".json"))
            .filter(|id| safe_token(id, 128))
            .map(str::to_owned)
            .collect())
    }

    /// Explicitly remove an orphaned immutable object. Refuses tip and foreign keys.
    /// Caller must establish that no revision references the object before deletion.
    pub fn delete_orphan_object(&self, project_id: &str, key: &str) -> Result<(), SyncError> {
        if !self.conditional_writes_verified() {
            return Err(SyncError::Backend);
        }
        if !(key.starts_with("blobs/") || key.starts_with("manifests/")) {
            return Err(SyncError::InvalidInput);
        }
        let scoped = self.object_key(project_id, key)?;
        self.runtime
            .block_on(
                self.client
                    .delete_object()
                    .bucket(&self.profile.bucket)
                    .key(scoped)
                    .send(),
            )
            .map_err(|_| SyncError::Backend)?;
        Ok(())
    }

    /// Cancellation is checked before and after the request; in-flight transport
    /// cancellation requires a future async backend API.
    pub fn get_immutable_checked(
        &self,
        project_id: &str,
        key: &str,
        cancelled: &dyn Fn() -> bool,
    ) -> Result<Vec<u8>, SyncError> {
        if cancelled() {
            return Err(SyncError::Cancelled);
        }
        let data = self.get_immutable(project_id, key)?;
        if cancelled() {
            return Err(SyncError::Cancelled);
        }
        Ok(data)
    }

    async fn read_tip_remote(&self, project_id: &str) -> Result<ObservedTip, SyncError> {
        let key = self.tip_key(project_id)?;
        let response = match self
            .client
            .get_object()
            .bucket(&self.profile.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(response) => response,
            Err(error) => {
                if error
                    .raw_response()
                    .is_some_and(|response| response.status().as_u16() == 404)
                {
                    return Ok(ObservedTip {
                        tip: Tip {
                            revision: None,
                            version: 0,
                        },
                        etag: None,
                    });
                }
                return Err(SyncError::Backend);
            }
        };
        let etag = response.e_tag().map(str::to_owned);
        let bytes = response
            .body
            .collect()
            .await
            .map_err(|_| SyncError::Backend)?
            .into_bytes();
        let tip: TipWire = serde_json::from_slice(&bytes).map_err(|_| SyncError::Integrity)?;
        if tip.version == 0 || tip.revision.is_empty() || !safe_token(&tip.revision, 128) {
            return Err(SyncError::Integrity);
        }
        Ok(ObservedTip {
            tip: Tip {
                revision: Some(tip.revision),
                version: tip.version,
            },
            etag,
        })
    }

    /// Verifies bucket access and the S3 conditional writes that make tip CAS safe.
    /// This writes only a random probe object and deletes it best-effort afterward.
    pub fn verify_conditional_writes(&self) -> Result<(), CloudError> {
        // Serialize concurrent probes so an older success cannot re-grant a
        // capability after a newer failed probe.
        let _probe_guard = self.probe_lock.lock();
        // A failed re-probe must revoke a previously established capability.
        self.conditional_writes_verified
            .store(false, Ordering::Release);
        let key = format!(
            "{}/_probe/{}.json",
            self.profile.prefix,
            Uuid::new_v4().simple()
        );
        let result = self.runtime.block_on(async {
            let first = self
                .client
                .put_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .if_none_match("*")
                .body(ByteStream::from_static(b"one"))
                .send()
                .await
                .map_err(|error| safe_sdk_error!(error))?;
            let first_etag = first
                .e_tag()
                .ok_or(CloudError::ProviderUnavailable)?
                .to_owned();
            let duplicate_create = self
                .client
                .put_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .if_none_match("*")
                .body(ByteStream::from_static(b"overwrite"))
                .send()
                .await;
            if !duplicate_create.as_ref().err().is_some_and(|error| {
                error
                    .raw_response()
                    .is_some_and(|response| response.status().as_u16() == 412)
            }) {
                let _ = self
                    .client
                    .delete_object()
                    .bucket(&self.profile.bucket)
                    .key(&key)
                    .send()
                    .await;
                return Err(CloudError::ConditionalWritesUnsupported);
            }
            let second = self
                .client
                .put_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .if_match(first_etag.clone())
                .body(ByteStream::from_static(b"two"))
                .send()
                .await
                .map_err(|error| safe_sdk_error!(error))?;
            let second_etag = second
                .e_tag()
                .ok_or(CloudError::ProviderUnavailable)?
                .to_owned();
            let stale_write = self
                .client
                .put_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .if_match(first_etag)
                .body(ByteStream::from_static(b"unsafe"))
                .send()
                .await;
            let _ = self
                .client
                .delete_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .send()
                .await;
            let stale_rejected = stale_write.as_ref().err().is_some_and(|error| {
                error
                    .raw_response()
                    .is_some_and(|response| response.status().as_u16() == 412)
            });
            if !stale_rejected || second_etag.is_empty() {
                return Err(CloudError::ConditionalWritesUnsupported);
            }
            Ok(())
        });
        if result.is_ok() {
            self.conditional_writes_verified
                .store(true, Ordering::Release);
        }
        result
    }

    /// Safe-sync mutations remain disabled until the live provider probe proves
    /// both create-if-absent and ETag-guarded replacement semantics.
    pub fn conditional_writes_verified(&self) -> bool {
        self.conditional_writes_verified.load(Ordering::Acquire)
    }
}

#[derive(Serialize, Deserialize)]
struct TipWire {
    revision: String,
    version: u64,
}

impl RevisionBackend for S3Backend {
    fn tip(&self, project_id: &str) -> Result<Tip, SyncError> {
        let observed = self.runtime.block_on(self.read_tip_remote(project_id))?;
        let tip = observed.tip.clone();
        self.observed_tips
            .lock()
            .insert(project_id.to_owned(), observed);
        Ok(tip)
    }

    fn put_immutable(&self, project_id: &str, key: &str, data: &[u8]) -> Result<(), SyncError> {
        if !self.conditional_writes_verified() {
            return Err(SyncError::Backend);
        }
        if data.len() > MAX_OBJECT_BYTES {
            return Err(SyncError::InvalidInput);
        }
        let key = self.object_key(project_id, key)?;
        let first = self.runtime.block_on(
            self.client
                .put_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .if_none_match("*")
                .body(ByteStream::from(data.to_vec()))
                .send(),
        );
        if first.is_ok() {
            return Ok(());
        }
        let existing = self.runtime.block_on(async {
            let response = self
                .client
                .get_object()
                .bucket(&self.profile.bucket)
                .key(&key)
                .send()
                .await
                .map_err(|_| SyncError::Backend)?;
            response
                .body
                .collect()
                .await
                .map(|bytes| bytes.into_bytes().to_vec())
                .map_err(|_| SyncError::Backend)
        })?;
        if existing == data {
            Ok(())
        } else {
            Err(SyncError::Integrity)
        }
    }

    fn get_immutable(&self, project_id: &str, key: &str) -> Result<Vec<u8>, SyncError> {
        let key = self.object_key(project_id, key)?;
        self.runtime.block_on(async {
            let response = self
                .client
                .get_object()
                .bucket(&self.profile.bucket)
                .key(key)
                .send()
                .await
                .map_err(|error| {
                    if error
                        .raw_response()
                        .is_some_and(|response| response.status().as_u16() == 404)
                    {
                        SyncError::NotFound
                    } else {
                        SyncError::Backend
                    }
                })?;
            response
                .body
                .collect()
                .await
                .map(|bytes| bytes.into_bytes().to_vec())
                .map_err(|_| SyncError::Backend)
        })
    }

    fn compare_and_swap_tip(
        &self,
        project_id: &str,
        expected: &Tip,
        new_revision: &str,
    ) -> Result<(), SyncError> {
        if !self.conditional_writes_verified() {
            return Err(SyncError::Backend);
        }
        if !safe_token(new_revision, 128) {
            return Err(SyncError::InvalidInput);
        }
        let observed = self
            .observed_tips
            .lock()
            .get(project_id)
            .cloned()
            .ok_or(SyncError::Conflict)?;
        if observed.tip != *expected {
            return Err(SyncError::Conflict);
        }
        let key = self.tip_key(project_id)?;
        let body = serde_json::to_vec(&TipWire {
            revision: new_revision.to_owned(),
            version: expected.version + 1,
        })
        .map_err(|_| SyncError::Backend)?;
        let result = self.runtime.block_on(async {
            let request = self
                .client
                .put_object()
                .bucket(&self.profile.bucket)
                .key(key)
                .body(ByteStream::from(body));
            match observed.etag {
                Some(etag) => request.if_match(etag).send().await,
                None => request.if_none_match("*").send().await,
            }
        });
        if result.is_ok() {
            self.observed_tips.lock().remove(project_id);
            return Ok(());
        }
        let current = self.runtime.block_on(self.read_tip_remote(project_id));
        match current {
            Ok(current) if current.tip != *expected => Err(SyncError::Conflict),
            _ => Err(SyncError::Backend),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use researchweave_project::{archive_project, ProjectInfo, ProjectStore};

    #[test]
    fn retained_backend_identity_and_revocation_epochs() {
        let mut cache = VerifiedBackends::<String>::default();
        let first = Arc::new("verified backend".to_owned());
        let epoch = cache.epoch("profile");
        assert!(cache.retain_if_current("profile".into(), epoch, Arc::clone(&first)));
        assert!(Arc::ptr_eq(&cache.get("profile").unwrap(), &first));
        cache.revoke("profile");
        assert!(cache.get("profile").is_none());
        assert!(!cache.retain_if_current("profile".into(), epoch, first));
        assert!(cache.get("profile").is_none());
    }

    #[test]
    fn sync_reads_use_context_project_only_and_validate_limit() {
        let backend = researchweave_sync::MemoryBackend::new();
        let project = Uuid::new_v4();
        let other = Uuid::new_v4();
        backend
            .compare_and_swap_tip(
                &other.to_string(),
                &Tip {
                    revision: None,
                    version: 0,
                },
                "other-revision",
            )
            .unwrap();
        let tip = read_project_sync(
            &backend,
            project,
            "cloud.sync.tip",
            &json!({"project_id":other}),
        )
        .unwrap();
        assert_eq!(tip["project_id"], project.to_string());
        assert_eq!(tip["revision"], Value::Null);
        assert_eq!(tip["version"], 0);
        let history = read_project_sync(
            &backend,
            project,
            "cloud.sync.history",
            &json!({"limit":10}),
        )
        .unwrap();
        assert_eq!(history["revisions"], json!([]));
        assert_eq!(
            read_project_sync(
                &backend,
                project,
                "cloud.sync.history",
                &json!({"limit":101})
            )
            .unwrap_err(),
            SyncError::InvalidInput
        );
    }

    #[test]
    fn cloud_handler_preview_has_no_side_effects_and_redacts_secrets() {
        let store = Arc::new(MemorySecretStore::default());
        let handler = CloudOperationHandler::new(store.clone());
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let profile = serde_json::to_value(S3Profile::liara(
            "profile",
            "https://storage.c2.liara.site",
            "bucket-name",
        ))
        .unwrap();
        assert_eq!(
            handler.preview("cloud.profile.configure", &profile, &context)["ok"],
            true
        );
        assert!(handler.profiles.lock().is_empty());
        assert_eq!(
            handler.execute("cloud.profile.configure", &profile, &context)["ok"],
            true
        );
        let args =
            json!({"profile_id":"profile","access_key":"key-SECRET","secret_key":"very-SECRET"});
        let preview = handler.preview("cloud.credentials.store", &args, &context);
        assert!(!preview.to_string().contains("SECRET"));
        assert!(store.get("profile").is_err());
        let applied = handler.execute("cloud.credentials.store", &args, &context);
        assert!(!applied.to_string().contains("SECRET"));
        assert!(store.get("profile").is_ok());
        assert_eq!(
            handler.preview(
                "cloud.conditional.probe",
                &json!({"profile_id":"profile"}),
                &context
            )["result"]["probe_writes_temporary_object"],
            true
        );
        handler.execute(
            "cloud.credentials.delete",
            &json!({"profile_id":"profile"}),
            &context,
        );
        assert!(store.get("profile").is_err());
        assert_eq!(
            CloudOperationHandler::capabilities()
                .iter()
                .find(|c| c.operation == "cloud.conditional.probe")
                .unwrap()
                .effect,
            Effect::ExternalNetwork
        );
    }

    #[test]
    fn cloud_profiles_persist_across_restart_without_credentials() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("cloud").join("profiles.json");
        let credentials = Arc::new(MemorySecretStore::default());
        let encryption = Arc::new(MemorySyncSecretStore::default());
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let handler = CloudOperationHandler::with_profile_path(
            credentials.clone(),
            encryption.clone(),
            path.clone(),
        )
        .unwrap();
        let mut profile =
            S3Profile::liara("persisted", "https://storage.c2.liara.site", "bucket-one");
        let configured = handler.execute(
            "cloud.profile.configure",
            &serde_json::to_value(&profile).unwrap(),
            &context,
        );
        assert_eq!(configured["status"], "ok");
        credentials
            .put(
                "persisted",
                &CredentialBundle {
                    access_key: "access-SECRET".into(),
                    secret_key: "secret-SECRET".into(),
                    session_token: None,
                },
            )
            .unwrap();
        let on_disk = fs::read_to_string(&path).unwrap();
        assert!(on_disk.contains("bucket-one"));
        assert!(!on_disk.contains("SECRET"));

        profile.bucket = "bucket-two".into();
        assert_eq!(
            handler.execute(
                "cloud.profile.configure",
                &serde_json::to_value(&profile).unwrap(),
                &context,
            )["status"],
            "ok"
        );
        drop(handler);

        let restarted =
            CloudOperationHandler::with_profile_path(credentials.clone(), encryption, path.clone())
                .unwrap();
        let listed = restarted.execute("cloud.profile.list", &json!({}), &context);
        assert_eq!(listed["status"], "ok");
        assert_eq!(listed["result"]["profiles"][0]["profile_id"], "persisted");
        assert_eq!(listed["result"]["profiles"][0]["bucket"], "bucket-two");
        assert_eq!(listed["result"]["profiles"][0]["credentials_present"], true);

        let preview = restarted.preview(
            "cloud.profile.disconnect",
            &json!({"profile_id":"persisted"}),
            &context,
        );
        assert_eq!(preview["result"]["disconnected"], false);
        assert_eq!(
            restarted.execute("cloud.profile.list", &json!({}), &context)["result"]["profiles"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        let disconnected = restarted.execute(
            "cloud.profile.disconnect",
            &json!({"profile_id":"persisted"}),
            &context,
        );
        assert_eq!(disconnected["result"]["credentials_deleted"], false);
        assert!(credentials.get("persisted").is_ok());
        drop(restarted);

        let after_restart = CloudOperationHandler::with_profile_path(
            credentials,
            Arc::new(MemorySyncSecretStore::default()),
            path,
        )
        .unwrap();
        assert!(after_restart.profiles.lock().is_empty());
    }

    #[test]
    fn failure_classes_and_bounded_retry_are_deterministic_and_redacted() {
        for (status, kind) in [
            (401, FailureClass::Authentication),
            (403, FailureClass::Permission),
            (404, FailureClass::Missing),
            (409, FailureClass::Conflict),
            (412, FailureClass::Precondition),
            (429, FailureClass::RateLimited),
            (500, FailureClass::Temporary),
            (503, FailureClass::Temporary),
        ] {
            assert_eq!(classify_failure(Some(status), None, None), kind);
            assert!(!kind.advice().contains("secret-value"));
        }
        assert_eq!(
            classify_failure(Some(403), Some("SignatureDoesNotMatch"), None),
            FailureClass::Signature
        );
        assert_eq!(
            classify_failure(Some(403), Some("RequestTimeTooSkewed"), None),
            FailureClass::ClockSkew
        );
        assert_eq!(classify_failure(None, None, Some("tls")), FailureClass::Tls);
        assert_eq!(
            classify_failure(None, None, Some("timeout")),
            FailureClass::Timeout
        );
        assert_eq!(
            classify_failure(None, None, Some("connection")),
            FailureClass::Transport
        );
        assert_eq!(
            retry_delay(1, FailureClass::RateLimited),
            Some(Duration::from_millis(200))
        );
        assert_eq!(
            retry_delay(2, FailureClass::Temporary),
            Some(Duration::from_millis(400))
        );
        assert_eq!(retry_delay(3, FailureClass::Temporary), None);
        assert_eq!(retry_delay(1, FailureClass::Precondition), None);
        assert_eq!(retry_delay(1, FailureClass::Signature), None);
    }

    #[test]
    fn failed_probe_revokes_previously_verified_capability() {
        let profile = S3Profile::liara("p", "http://127.0.0.1:1", "bucket-name");
        let runtime = Arc::new(Runtime::new().unwrap());
        let config = S3ConfigBuilder::new()
            .behavior_version(BehaviorVersion::latest())
            .region(Region::new(DEFAULT_REGION))
            .endpoint_url(profile.endpoint.clone())
            .force_path_style(true)
            .timeout_config(
                aws_sdk_s3::config::timeout::TimeoutConfig::builder()
                    .operation_timeout(Duration::from_millis(350))
                    .build(),
            )
            .retry_config(aws_sdk_s3::config::retry::RetryConfig::standard().with_max_attempts(1))
            .build();
        let backend = S3Backend {
            runtime,
            client: Client::from_conf(config),
            profile,
            observed_tips: Mutex::new(HashMap::new()),
            conditional_writes_verified: AtomicBool::new(true),
            probe_lock: Mutex::new(()),
        };
        assert!(backend.verify_conditional_writes().is_err());
        assert!(!backend.conditional_writes_verified.load(Ordering::Acquire));
        assert_eq!(
            backend.put_immutable("p", "blobs/test", b"encrypted"),
            Err(SyncError::Backend)
        );
    }

    #[test]
    fn liara_profile_is_secure_and_path_style() {
        let profile = S3Profile::liara("liara-main", "https://storage.c2.liara.site", "my-bucket");
        assert_eq!(profile.provider, ProviderKind::Liara);
        assert_eq!(profile.region, DEFAULT_REGION);
        assert!(profile.force_path_style);
        profile.validate().unwrap();
    }

    #[test]
    fn rejects_insecure_remote_and_endpoint_credentials() {
        let mut profile = S3Profile::liara("p", "http://storage.example.com", "bucket-name");
        assert!(profile.validate().is_err());
        profile.endpoint = "https://user:pass@storage.example.com".into();
        assert!(profile.validate().is_err());
        profile.endpoint = "http://127.0.0.1:9000".into();
        profile.provider = ProviderKind::GenericS3;
        assert!(profile.validate().is_ok());
    }

    #[test]
    fn memory_secret_store_roundtrip_and_delete() {
        let store = MemorySecretStore::default();
        let credentials = CredentialBundle {
            access_key: "access".into(),
            secret_key: "secret".into(),
            session_token: Some("session".into()),
        };
        assert!(!format!("{credentials:?}").contains("session"));
        store.put("profile", &credentials).unwrap();
        assert_eq!(store.get("profile").unwrap(), credentials);
        store.delete("profile").unwrap();
        assert!(matches!(
            store.get("profile"),
            Err(CloudError::MissingCredential)
        ));
    }

    #[test]
    #[ignore = "writes synthetic entries to the host OS credential manager"]
    fn os_keyring_roundtrip_restart_and_delete() {
        let profile_id = format!("researchweave-test-{}", Uuid::new_v4());
        let project_id = Uuid::new_v4();
        let credentials = CredentialBundle {
            access_key: "synthetic-access-key".into(),
            secret_key: "synthetic-secret-key".into(),
            session_token: Some("synthetic-session-token".into()),
        };
        let passphrase = "synthetic sync passphrase 2026";

        let exercise = (|| -> Result<(), String> {
            let credential_writer = OsKeyringStore;
            credential_writer
                .put(&profile_id, &credentials)
                .map_err(|error| format!("credential put failed: {error}"))?;

            // Construct fresh store values to prove retrieval is not in-memory state.
            let credential_reader = OsKeyringStore;
            let loaded = credential_reader
                .get(&profile_id)
                .map_err(|error| format!("credential get failed: {error}"))?;
            if loaded != credentials {
                return Err("credential roundtrip mismatch".into());
            }

            let sync_writer = OsSyncSecretStore;
            sync_writer
                .put(project_id, passphrase)
                .map_err(|error| format!("sync secret put failed: {error}"))?;
            let sync_reader = OsSyncSecretStore;
            let loaded_passphrase = sync_reader
                .get(project_id)
                .map_err(|error| format!("sync secret get failed: {error}"))?;
            if loaded_passphrase.as_str() != passphrase {
                return Err("sync secret roundtrip mismatch".into());
            }
            Ok(())
        })();

        // Always attempt cleanup before surfacing a failure so the ignored host test does not
        // leave synthetic credentials behind.
        let credential_cleanup = OsKeyringStore.delete(&profile_id);
        let sync_cleanup = OsSyncSecretStore.delete(project_id);
        assert!(
            credential_cleanup.is_ok(),
            "failed to remove synthetic credential entry"
        );
        assert!(
            sync_cleanup.is_ok(),
            "failed to remove synthetic sync-secret entry"
        );
        exercise.expect("host OS keyring roundtrip failed");

        assert!(matches!(
            OsKeyringStore.get(&profile_id),
            Err(CloudError::MissingCredential)
        ));
        assert!(matches!(
            OsSyncSecretStore.get(project_id),
            Err(CloudError::MissingCredential)
        ));
    }

    #[test]
    fn sync_passphrase_store_is_project_scoped_redacted_and_deletable() {
        let store = MemorySyncSecretStore::default();
        let first = Uuid::new_v4();
        let second = Uuid::new_v4();
        store.put(first, "correct horse battery staple").unwrap();
        assert_eq!(&*store.get(first).unwrap(), "correct horse battery staple");
        assert!(matches!(
            store.get(second),
            Err(CloudError::MissingCredential)
        ));
        store.delete(first).unwrap();
        assert!(matches!(
            store.get(first),
            Err(CloudError::MissingCredential)
        ));
        assert!(matches!(
            store.put(first, "too short"),
            Err(CloudError::InvalidSyncInput)
        ));
    }

    #[test]
    fn encrypted_sync_helpers_roundtrip_verified_project_archive_and_preserve_conflict() {
        let source = tempfile::tempdir().unwrap();
        let project_id = Uuid::new_v4();
        let project_root = source.path().join("project");
        let store = ProjectStore::create(
            &project_root,
            &ProjectInfo {
                id: project_id.to_string(),
                title: "Cloud پژوهش".into(),
                question: "Does encrypted sync preserve this archive?".into(),
                design: "observational".into(),
                locale: "fa".into(),
                privacy: "private".into(),
                revision: 0,
                created_at: "2026-10-25T00:00:00Z".into(),
            },
        )
        .unwrap();
        let archive_path = source.path().join("source.rwproj");
        archive_project(&store, &archive_path).unwrap();
        let archive = fs::read(&archive_path).unwrap();

        let backend = researchweave_sync::MemoryBackend::new();
        let pushed = push_project_archive(
            &backend,
            project_id,
            0,
            &archive,
            "correct horse battery staple",
            None,
            "device-a",
        )
        .unwrap();
        assert_eq!(pushed["advanced"], true);
        assert_eq!(pushed["conflict"], false);
        let encrypted_object = backend
            .get_immutable(
                &project_id.to_string(),
                &format!(
                    "blobs/{}.rwenc",
                    pushed["encrypted_sha256"].as_str().unwrap()
                ),
            )
            .unwrap();
        assert!(encrypted_object.starts_with(b"RWPENC1\n"));
        let revision = pushed["revision"].as_str().unwrap().to_owned();
        let pulled = pull_project_archive(
            &backend,
            project_id,
            &revision,
            "correct horse battery staple",
        )
        .unwrap();
        assert_eq!(pulled, archive);

        let destination = source.path().join("pulled.rwproj");
        let receipt = persist_verified_archive(project_id, &pulled, &destination).unwrap();
        assert_eq!(receipt["verified"], true);
        assert_eq!(
            verify_archive(&destination).unwrap().project_id,
            project_id.to_string()
        );
        assert!(matches!(
            persist_verified_archive(project_id, &pulled, &destination),
            Err(CloudError::DestinationExists)
        ));

        let conflict = push_project_archive(
            &backend,
            project_id,
            0,
            &archive,
            "correct horse battery staple",
            None,
            "device-b",
        )
        .unwrap();
        assert_eq!(conflict["advanced"], false);
        assert_eq!(conflict["conflict"], true);
        assert_eq!(conflict["actual_revision"], revision);
        assert!(conflict["preserved_revision"].as_str().is_some());
    }

    #[test]
    fn encryption_secret_commands_never_echo_passphrase() {
        let credentials = Arc::new(MemorySecretStore::default());
        let encryption = Arc::new(MemorySyncSecretStore::default());
        let handler = CloudOperationHandler::new_with_sync_secrets(credentials, encryption.clone());
        let context = DispatchContext {
            request_id: Uuid::new_v4(),
            project_id: Uuid::new_v4(),
            actor: "test".into(),
            expected_revision: None,
        };
        let secret = "correct horse battery staple";
        let preview = handler.preview(
            "cloud.encryption.store",
            &json!({"passphrase":secret}),
            &context,
        );
        assert!(!preview.to_string().contains(secret));
        assert!(matches!(
            encryption.get(context.project_id),
            Err(CloudError::MissingCredential)
        ));
        let stored = handler.execute(
            "cloud.encryption.store",
            &json!({"passphrase":secret}),
            &context,
        );
        assert_eq!(stored["status"], "ok");
        assert!(!stored.to_string().contains(secret));
        assert_eq!(&*encryption.get(context.project_id).unwrap(), secret);
        let deleted = handler.execute("cloud.encryption.delete", &json!({}), &context);
        assert_eq!(deleted["status"], "ok");
        assert!(matches!(
            encryption.get(context.project_id),
            Err(CloudError::MissingCredential)
        ));
        let capabilities = CloudOperationHandler::capabilities();
        assert!(capabilities.iter().any(|capability| {
            capability.operation == "cloud.sync.push"
                && capability.effect == Effect::ExternalNetwork
        }));
        assert!(capabilities.iter().any(|capability| {
            capability.operation == "cloud.sync.pull"
                && capability.effect == Effect::ExternalNetwork
        }));
    }

    #[test]
    fn object_identifiers_reject_traversal() {
        let profile = S3Profile::liara("p", "https://storage.c2.liara.site", "bucket-name");
        let runtime = Arc::new(Runtime::new().unwrap());
        let config = S3ConfigBuilder::new()
            .behavior_version(BehaviorVersion::latest())
            .region(Region::new(DEFAULT_REGION))
            .endpoint_url(profile.endpoint.clone())
            .force_path_style(true)
            .build();
        let backend = S3Backend {
            runtime,
            client: Client::from_conf(config),
            profile,
            observed_tips: Mutex::new(HashMap::new()),
            conditional_writes_verified: AtomicBool::new(false),
            probe_lock: Mutex::new(()),
        };
        assert!(backend.object_key("project", "blobs/hash.rwenc").is_ok());
        assert_eq!(
            backend.object_key("project", "../secret"),
            Err(SyncError::InvalidInput)
        );
        assert_eq!(
            backend.put_immutable("project", "blobs/hash.rwenc", b"ciphertext"),
            Err(SyncError::Backend)
        );
    }
}
