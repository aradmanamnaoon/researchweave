//! Immutable, encrypted project snapshots and compare-and-swap revision tips.
//! Backends must provide atomic CAS and immutable put-if-absent semantics.
use researchweave_crypto::{decrypt_backup, encrypt_backup, CryptoError};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::Mutex;
use thiserror::Error;
use uuid::Uuid;

pub const MAX_SYNC_OBJECT_BYTES: usize = 256 * 1024 * 1024 + 32 * 1024;

#[derive(Debug, Error)]
pub enum SyncError {
    #[error("invalid project, device, revision, or object path")]
    InvalidInput,
    #[error("immutable object collision or corrupted object")]
    Integrity,
    #[error("object does not exist")]
    NotFound,
    #[error("remote tip changed")]
    Conflict,
    #[error("restore destination exists")]
    DestinationExists,
    #[error("operation cancelled")]
    Cancelled,
    #[error("backend state unavailable")]
    Backend,
    #[error("cryptographic operation failed: {0}")]
    Crypto(#[from] CryptoError),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
}

impl PartialEq for SyncError {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Crypto(left), Self::Crypto(right)) => left == right,
            (Self::Io(left), Self::Io(right)) => left.kind() == right.kind(),
            _ => std::mem::discriminant(self) == std::mem::discriminant(other),
        }
    }
}
impl Eq for SyncError {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Revision {
    pub revision: String,
    pub predecessor: Option<String>,
    pub encrypted_sha256: String,
    pub plaintext_sha256: String,
    pub size: usize,
    pub device_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Tip {
    pub revision: Option<String>,
    pub version: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Conflict {
    pub expected_revision: Option<String>,
    pub actual_revision: Option<String>,
    pub preserved: Revision,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PushResult {
    Advanced(Revision),
    Conflict(Conflict),
}

pub trait RevisionBackend: Send + Sync {
    fn tip(&self, project_id: &str) -> Result<Tip, SyncError>;
    fn put_immutable(&self, project_id: &str, key: &str, data: &[u8]) -> Result<(), SyncError>;
    fn get_immutable(&self, project_id: &str, key: &str) -> Result<Vec<u8>, SyncError>;
    fn compare_and_swap_tip(
        &self,
        project_id: &str,
        expected: &Tip,
        new_revision: &str,
    ) -> Result<(), SyncError>;
}

#[derive(Default)]
struct MemoryState {
    objects: HashMap<(String, String), Vec<u8>>,
    tips: HashMap<String, Tip>,
}

/// Deterministic in-memory reference backend. CAS operates under one lock.
#[derive(Default)]
pub struct MemoryBackend {
    state: Mutex<MemoryState>,
}

impl MemoryBackend {
    pub fn new() -> Self {
        Self::default()
    }
}

impl RevisionBackend for MemoryBackend {
    fn tip(&self, project_id: &str) -> Result<Tip, SyncError> {
        let state = self.state.lock().map_err(|_| SyncError::Backend)?;
        Ok(state.tips.get(project_id).cloned().unwrap_or(Tip {
            revision: None,
            version: 0,
        }))
    }
    fn put_immutable(&self, project_id: &str, key: &str, data: &[u8]) -> Result<(), SyncError> {
        let mut state = self.state.lock().map_err(|_| SyncError::Backend)?;
        let entry = state
            .objects
            .entry((project_id.to_owned(), key.to_owned()))
            .or_insert_with(|| data.to_vec());
        if entry != data {
            return Err(SyncError::Integrity);
        }
        Ok(())
    }
    fn get_immutable(&self, project_id: &str, key: &str) -> Result<Vec<u8>, SyncError> {
        let state = self.state.lock().map_err(|_| SyncError::Backend)?;
        state
            .objects
            .get(&(project_id.to_owned(), key.to_owned()))
            .cloned()
            .ok_or(SyncError::NotFound)
    }
    fn compare_and_swap_tip(
        &self,
        project_id: &str,
        expected: &Tip,
        new_revision: &str,
    ) -> Result<(), SyncError> {
        let mut state = self.state.lock().map_err(|_| SyncError::Backend)?;
        let current = state.tips.get(project_id).cloned().unwrap_or(Tip {
            revision: None,
            version: 0,
        });
        if current != *expected {
            return Err(SyncError::Conflict);
        }
        state.tips.insert(
            project_id.to_owned(),
            Tip {
                revision: Some(new_revision.to_owned()),
                version: current.version + 1,
            },
        );
        Ok(())
    }
}

pub struct SyncService<B: RevisionBackend> {
    backend: B,
    project_id: String,
    device_id: String,
}

fn safe_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._-".contains(c))
}
fn sha(data: &[u8]) -> String {
    hex::encode(Sha256::digest(data))
}
fn blob_key(hash: &str) -> String {
    format!("blobs/{hash}.rwenc")
}
fn manifest_key(revision: &str) -> String {
    format!("manifests/{revision}.json")
}

impl<B: RevisionBackend> SyncService<B> {
    pub fn new(
        backend: B,
        project_id: impl Into<String>,
        device_id: impl Into<String>,
    ) -> Result<Self, SyncError> {
        let project_id = project_id.into();
        let device_id = device_id.into();
        if !safe_id(&project_id) || !safe_id(&device_id) {
            return Err(SyncError::InvalidInput);
        }
        Ok(Self {
            backend,
            project_id,
            device_id,
        })
    }
    pub fn backend(&self) -> &B {
        &self.backend
    }
    pub fn tip(&self) -> Result<Tip, SyncError> {
        self.backend.tip(&self.project_id)
    }

    pub fn push(
        &self,
        data: &[u8],
        password: &str,
        expected_revision: Option<&str>,
    ) -> Result<PushResult, SyncError> {
        self.push_checked(data, password, expected_revision, &|| false)
    }
    pub fn push_checked(
        &self,
        data: &[u8],
        password: &str,
        expected_revision: Option<&str>,
        cancelled: &dyn Fn() -> bool,
    ) -> Result<PushResult, SyncError> {
        if let Some(id) = expected_revision {
            if !safe_id(id) {
                return Err(SyncError::InvalidInput);
            }
        }
        if cancelled() {
            return Err(SyncError::Cancelled);
        }
        let (encrypted, receipt) = encrypt_backup(&self.project_id, data, password)?;
        self.push_sealed_checked(
            &encrypted,
            &receipt.plaintext_sha256,
            expected_revision,
            cancelled,
        )
    }

    /// Store an object that was already encrypted and authenticated by a
    /// project-level envelope. This keeps the revision/CAS protocol independent
    /// from a particular encryption container while preserving content hashes.
    pub fn push_sealed(
        &self,
        encrypted: &[u8],
        plaintext_sha256: &str,
        expected_revision: Option<&str>,
    ) -> Result<PushResult, SyncError> {
        self.push_sealed_checked(encrypted, plaintext_sha256, expected_revision, &|| false)
    }

    pub fn push_sealed_checked(
        &self,
        encrypted: &[u8],
        plaintext_sha256: &str,
        expected_revision: Option<&str>,
        cancelled: &dyn Fn() -> bool,
    ) -> Result<PushResult, SyncError> {
        if encrypted.is_empty()
            || encrypted.len() > MAX_SYNC_OBJECT_BYTES
            || plaintext_sha256.len() != 64
            || !plaintext_sha256
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit())
        {
            return Err(SyncError::InvalidInput);
        }
        if let Some(id) = expected_revision {
            if !safe_id(id) {
                return Err(SyncError::InvalidInput);
            }
        }
        if cancelled() {
            return Err(SyncError::Cancelled);
        }
        let prior = self.tip()?;
        if cancelled() {
            return Err(SyncError::Cancelled);
        }
        let manifest = Revision {
            revision: Uuid::new_v4().simple().to_string(),
            predecessor: expected_revision.map(str::to_owned),
            encrypted_sha256: sha(encrypted),
            plaintext_sha256: plaintext_sha256.to_ascii_lowercase(),
            size: encrypted.len(),
            device_id: self.device_id.clone(),
        };
        self.backend.put_immutable(
            &self.project_id,
            &blob_key(&manifest.encrypted_sha256),
            encrypted,
        )?;
        self.backend.put_immutable(
            &self.project_id,
            &manifest_key(&manifest.revision),
            &serde_json::to_vec(&manifest).map_err(|_| SyncError::Integrity)?,
        )?;
        if cancelled() {
            return Err(SyncError::Cancelled);
        } // the immutable orphan is safe to recover
        if prior.revision.as_deref() != expected_revision {
            return Ok(PushResult::Conflict(Conflict {
                expected_revision: expected_revision.map(str::to_owned),
                actual_revision: prior.revision,
                preserved: manifest,
            }));
        }
        match self
            .backend
            .compare_and_swap_tip(&self.project_id, &prior, &manifest.revision)
        {
            Ok(()) => Ok(PushResult::Advanced(manifest)),
            Err(SyncError::Conflict) => Ok(PushResult::Conflict(Conflict {
                expected_revision: expected_revision.map(str::to_owned),
                actual_revision: self.tip()?.revision,
                preserved: manifest,
            })),
            Err(error) => Err(error),
        }
    }

    pub fn manifest(&self, revision: &str) -> Result<Revision, SyncError> {
        if !safe_id(revision) {
            return Err(SyncError::InvalidInput);
        }
        let raw = self
            .backend
            .get_immutable(&self.project_id, &manifest_key(revision))?;
        let result: Revision = serde_json::from_slice(&raw).map_err(|_| SyncError::Integrity)?;
        if result.revision != revision
            || !safe_id(&result.device_id)
            || result.predecessor.as_deref().is_some_and(|p| !safe_id(p))
            || result.encrypted_sha256.len() != 64
            || !result
                .encrypted_sha256
                .bytes()
                .all(|c| c.is_ascii_hexdigit())
            || result.plaintext_sha256.len() != 64
            || !result
                .plaintext_sha256
                .bytes()
                .all(|c| c.is_ascii_hexdigit())
            || result.size == 0
            || result.size > MAX_SYNC_OBJECT_BYTES
        {
            return Err(SyncError::Integrity);
        }
        Ok(result)
    }
    pub fn pull_encrypted(&self, revision: &str) -> Result<(Revision, Vec<u8>), SyncError> {
        let info = self.manifest(revision)?;
        let encrypted = self
            .backend
            .get_immutable(&self.project_id, &blob_key(&info.encrypted_sha256))?;
        if info.size != encrypted.len() || sha(&encrypted) != info.encrypted_sha256 {
            return Err(SyncError::Integrity);
        }
        Ok((info, encrypted))
    }
    pub fn pull(&self, revision: &str, password: &str) -> Result<Vec<u8>, SyncError> {
        let (info, encrypted) = self.pull_encrypted(revision)?;
        let plain = decrypt_backup(&self.project_id, &encrypted, password)?;
        if sha(&plain) != info.plaintext_sha256 {
            return Err(SyncError::Integrity);
        }
        Ok(plain)
    }
    pub fn history(&self, limit: usize) -> Result<Vec<Revision>, SyncError> {
        let mut revisions = Vec::new();
        let mut current = self.tip()?.revision;
        let mut visited = std::collections::HashSet::new();
        while let Some(id) = current {
            if !visited.insert(id.clone()) {
                return Err(SyncError::Integrity);
            }
            let revision = self.manifest(&id)?;
            current = revision.predecessor.clone();
            revisions.push(revision);
            if revisions.len() >= limit {
                break;
            }
        }
        Ok(revisions)
    }
    /// Create-only restore; does not replace or mutate the active project.
    pub fn restore_as_copy(
        &self,
        revision: &str,
        password: &str,
        destination: &Path,
    ) -> Result<String, SyncError> {
        let contents = self.pull(revision, password)?;
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(destination)
            .map_err(|e| {
                if e.kind() == std::io::ErrorKind::AlreadyExists {
                    SyncError::DestinationExists
                } else {
                    SyncError::Io(e)
                }
            })?;
        if let Err(error) = (|| -> std::io::Result<()> {
            output.write_all(&contents)?;
            output.sync_all()
        })() {
            drop(output);
            let _ = fs::remove_file(destination);
            return Err(SyncError::Io(error));
        }
        Ok(sha(&contents))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    const PASSWORD: &str = "strong test password";

    fn sync(
        backend: Arc<MemoryBackend>,
        project: &str,
        device: &str,
    ) -> SyncService<Arc<MemoryBackend>> {
        SyncService::new(backend, project, device).unwrap()
    }
    impl<T: RevisionBackend + ?Sized> RevisionBackend for Arc<T> {
        fn tip(&self, p: &str) -> Result<Tip, SyncError> {
            (**self).tip(p)
        }
        fn put_immutable(&self, p: &str, k: &str, d: &[u8]) -> Result<(), SyncError> {
            (**self).put_immutable(p, k, d)
        }
        fn get_immutable(&self, p: &str, k: &str) -> Result<Vec<u8>, SyncError> {
            (**self).get_immutable(p, k)
        }
        fn compare_and_swap_tip(&self, p: &str, expected: &Tip, r: &str) -> Result<(), SyncError> {
            (**self).compare_and_swap_tip(p, expected, r)
        }
    }
    fn advanced(result: PushResult) -> Revision {
        match result {
            PushResult::Advanced(item) => item,
            PushResult::Conflict(_) => panic!("unexpected conflict"),
        }
    }
    #[test]
    fn first_push_pull_fast_forward_and_history() {
        let backend = Arc::new(MemoryBackend::new());
        let first = sync(backend.clone(), "project", "a");
        let second = sync(backend, "project", "b");
        let a = advanced(first.push(b"one", PASSWORD, None).unwrap());
        assert_eq!(second.pull(&a.revision, PASSWORD).unwrap(), b"one");
        let b = advanced(second.push(b"two", PASSWORD, Some(&a.revision)).unwrap());
        assert_eq!(first.history(10).unwrap(), vec![b.clone(), a.clone()]);
        assert_eq!(first.tip().unwrap().revision, Some(b.revision));
    }
    #[test]
    fn divergent_edit_preserves_both_and_stale_predecessor() {
        let backend = Arc::new(MemoryBackend::new());
        let a = sync(backend.clone(), "p", "a");
        let b = sync(backend, "p", "b");
        let base = advanced(a.push(b"base", PASSWORD, None).unwrap());
        let current = advanced(a.push(b"current", PASSWORD, Some(&base.revision)).unwrap());
        let conflict = match b.push(b"branch", PASSWORD, Some(&base.revision)).unwrap() {
            PushResult::Conflict(c) => c,
            _ => panic!("stale predecessor accepted"),
        };
        assert_eq!(conflict.actual_revision, Some(current.revision.clone()));
        assert_eq!(
            b.pull(&conflict.preserved.revision, PASSWORD).unwrap(),
            b"branch"
        );
        assert_eq!(a.pull(&current.revision, PASSWORD).unwrap(), b"current");
        assert_eq!(a.tip().unwrap().revision, Some(current.revision));
    }
    #[test]
    fn concurrent_compare_and_swap_rejects_stale_version() {
        let backend = MemoryBackend::new();
        let prior = backend.tip("p").unwrap();
        backend.compare_and_swap_tip("p", &prior, "first").unwrap();
        assert_eq!(
            backend.compare_and_swap_tip("p", &prior, "second"),
            Err(SyncError::Conflict)
        );
    }
    #[test]
    fn immutable_duplicates_and_corruption_are_rejected() {
        let backend = Arc::new(MemoryBackend::new());
        let s = sync(backend.clone(), "p", "a");
        let rev = advanced(s.push(b"data", PASSWORD, None).unwrap());
        let key = blob_key(&rev.encrypted_sha256);
        let original = backend.get_immutable("p", &key).unwrap();
        backend.put_immutable("p", &key, &original).unwrap();
        assert_eq!(
            backend.put_immutable("p", &key, b"different"),
            Err(SyncError::Integrity)
        );
        // Inject corruption as an untrusted storage provider could.
        backend
            .state
            .lock()
            .unwrap()
            .objects
            .insert(("p".into(), key), b"corrupt".to_vec());
        assert!(matches!(
            s.pull(&rev.revision, PASSWORD),
            Err(SyncError::Integrity)
        ));
    }
    #[test]
    fn wrong_password_and_project_cannot_decrypt() {
        let backend = Arc::new(MemoryBackend::new());
        let a = sync(backend.clone(), "p", "a");
        let rev = advanced(a.push(b"data", PASSWORD, None).unwrap());
        assert!(matches!(
            a.pull(&rev.revision, "incorrect password"),
            Err(SyncError::Crypto(CryptoError::AuthenticationFailed))
        ));
        let other = sync(backend.clone(), "other", "b");
        assert!(matches!(
            other.pull(&rev.revision, PASSWORD),
            Err(SyncError::NotFound)
        ));
        // Even when ciphertext is exposed in a different namespace, AEAD project binding rejects it.
        let key = blob_key(&rev.encrypted_sha256);
        let data = backend.get_immutable("p", &key).unwrap();
        backend.put_immutable("other", &key, &data).unwrap();
        backend
            .put_immutable(
                "other",
                &manifest_key(&rev.revision),
                &backend
                    .get_immutable("p", &manifest_key(&rev.revision))
                    .unwrap(),
            )
            .unwrap();
        assert!(matches!(
            other.pull(&rev.revision, PASSWORD),
            Err(SyncError::Crypto(CryptoError::AuthenticationFailed))
        ));
    }
    #[test]
    fn restore_copy_and_cancel_without_tip_change() {
        let backend = Arc::new(MemoryBackend::new());
        let s = sync(backend, "project", "a");
        assert_eq!(
            s.push_checked(b"hello", PASSWORD, None, &|| true),
            Err(SyncError::Cancelled)
        );
        assert_eq!(s.tip().unwrap().revision, None);
        let revision = advanced(s.push(b"hello", PASSWORD, None).unwrap());
        let path = std::env::temp_dir().join(format!("researchweave-sync-test-{}", Uuid::new_v4()));
        assert_eq!(
            s.restore_as_copy(&revision.revision, PASSWORD, &path)
                .unwrap(),
            sha(b"hello")
        );
        assert_eq!(fs::read(&path).unwrap(), b"hello");
        assert!(matches!(
            s.restore_as_copy(&revision.revision, PASSWORD, &path),
            Err(SyncError::DestinationExists)
        ));
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn presealed_objects_support_project_sized_envelopes_and_conflicts() {
        let backend = Arc::new(MemoryBackend::new());
        let first = sync(backend.clone(), "project", "a");
        let second = sync(backend, "project", "b");
        // One byte above the legacy RWENC1 plaintext ceiling proves the
        // revision protocol no longer imposes that legacy encryption limit.
        let sealed = vec![0x5a; 16_000_001];
        let plaintext_hash = sha(b"verified-project-archive");
        let base = advanced(first.push_sealed(&sealed, &plaintext_hash, None).unwrap());
        let (manifest, pulled) = second.pull_encrypted(&base.revision).unwrap();
        assert_eq!(manifest, base);
        assert_eq!(pulled, sealed);

        let branch = vec![0x33; 16_000_001];
        let current = advanced(
            first
                .push_sealed(&branch, &sha(b"current"), Some(&base.revision))
                .unwrap(),
        );
        let conflict = match second
            .push_sealed(&sealed, &plaintext_hash, Some(&base.revision))
            .unwrap()
        {
            PushResult::Conflict(conflict) => conflict,
            PushResult::Advanced(_) => panic!("stale sealed push unexpectedly advanced"),
        };
        assert_eq!(conflict.actual_revision, Some(current.revision));
        assert_eq!(
            second
                .pull_encrypted(&conflict.preserved.revision)
                .unwrap()
                .1,
            sealed
        );
    }
}
