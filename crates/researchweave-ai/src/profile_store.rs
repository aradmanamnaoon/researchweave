//! Durable non-secret AI provider metadata. Credentials never enter this store.
use crate::{AiError, Capabilities, ProviderKind, ProviderProfile};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
};

const MAX_BYTES: u64 = 65536;
const MAX_PROFILES: usize = 64;

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProfileMetadata {
    pub id: String,
    pub kind: ProviderKind,
    pub model: String,
    pub endpoint: String,
    pub local: bool,
    pub capabilities: Capabilities,
}

impl ProfileMetadata {
    pub fn validate(&self) -> Result<(), AiError> {
        ProviderProfile {
            id: self.id.clone(),
            kind: self.kind.clone(),
            model: self.model.clone(),
            endpoint: self.endpoint.clone(),
            local: self.local,
            credential_reference: None,
            capabilities: self.capabilities.clone(),
        }
        .validate()
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct FileSchema {
    version: u32,
    profiles: Vec<ProfileMetadata>,
}

pub struct ProfileStore {
    path: PathBuf,
    entries: Mutex<BTreeMap<String, ProfileMetadata>>,
}

impl ProfileStore {
    pub fn open(path: &Path) -> Result<Self, AiError> {
        if path.is_symlink() {
            return Err(AiError::Invalid);
        }
        let entries = if path.exists() {
            if fs::metadata(path).map_err(|_| AiError::Invalid)?.len() > MAX_BYTES {
                return Err(AiError::Invalid);
            }
            let bytes = fs::read(path).map_err(|_| AiError::Invalid)?;
            let schema: FileSchema =
                serde_json::from_slice(&bytes).map_err(|_| AiError::Invalid)?;
            if schema.version != 1 || schema.profiles.len() > MAX_PROFILES {
                return Err(AiError::Invalid);
            }
            let mut map = BTreeMap::new();
            for profile in schema.profiles {
                profile.validate()?;
                if map.insert(profile.id.clone(), profile).is_some() {
                    return Err(AiError::Invalid);
                }
            }
            map
        } else {
            BTreeMap::new()
        };
        Ok(Self {
            path: path.to_path_buf(),
            entries: Mutex::new(entries),
        })
    }

    pub fn list(&self) -> Result<Vec<ProfileMetadata>, AiError> {
        Ok(self
            .entries
            .lock()
            .map_err(|_| AiError::Invalid)?
            .values()
            .cloned()
            .collect())
    }

    pub fn change(
        &self,
        profile: Option<ProfileMetadata>,
        id: &str,
        update: bool,
    ) -> Result<(), AiError> {
        let mut guard = self.entries.lock().map_err(|_| AiError::Invalid)?;
        let mut next = guard.clone();
        match profile {
            Some(profile) => {
                profile.validate()?;
                if profile.id != id
                    || (next.contains_key(id) != update)
                    || (next.len() >= MAX_PROFILES && !update)
                {
                    return Err(AiError::Invalid);
                }
                next.insert(id.into(), profile);
            }
            None => {
                if next.remove(id).is_none() {
                    return Err(AiError::Invalid);
                }
            }
        }
        let encoded = serde_json::to_vec(&FileSchema {
            version: 1,
            profiles: next.values().cloned().collect(),
        })
        .map_err(|_| AiError::Invalid)?;
        if encoded.len() as u64 > MAX_BYTES {
            return Err(AiError::Invalid);
        }
        if self.path.is_symlink() {
            return Err(AiError::Invalid);
        }
        let parent = self.path.parent().ok_or(AiError::Invalid)?;
        fs::create_dir_all(parent).map_err(|_| AiError::Invalid)?;
        let tmp = self
            .path
            .with_extension(format!("tmp-{}", std::process::id()));
        fs::write(&tmp, encoded).map_err(|_| AiError::Invalid)?;
        if replace_file(&tmp, &self.path).is_err() {
            let _ = fs::remove_file(&tmp);
            return Err(AiError::Invalid);
        }
        *guard = next;
        Ok(())
    }
}

#[cfg(windows)]
fn replace_file(source: &Path, dest: &Path) -> Result<(), AiError> {
    if !dest.exists() {
        return fs::rename(source, dest).map_err(|_| AiError::Invalid);
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
    let replacement = source
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    if unsafe {
        ReplaceFileW(
            target.as_ptr(),
            replacement.as_ptr(),
            std::ptr::null(),
            0,
            std::ptr::null(),
            std::ptr::null(),
        )
    } == 0
    {
        return Err(AiError::Invalid);
    }
    Ok(())
}

#[cfg(not(windows))]
fn replace_file(source: &Path, dest: &Path) -> Result<(), AiError> {
    fs::rename(source, dest).map_err(|_| AiError::Invalid)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn restart_update_rejects_secrets_unknown_and_duplicates() {
        let dir = std::env::temp_dir().join(format!("rw-ai-profiles-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("profiles.json");
        let _ = fs::remove_file(&path);
        let store = ProfileStore::open(&path).unwrap();
        let input = serde_json::json!({"id":"one","kind":"open_ai_compatible",
            "model":"model-a","endpoint":"https://example.org/v1","local":false,
            "capabilities":{"streaming":false,"tools":true,"structured_output":false}});
        let profile: ProfileMetadata = serde_json::from_value(input.clone()).unwrap();
        store.change(Some(profile.clone()), "one", false).unwrap();
        assert!(store.change(Some(profile.clone()), "one", false).is_err());
        assert!(store
            .change(Some(profile.clone()), "missing", true)
            .is_err());
        assert!(serde_json::from_value::<ProfileMetadata>(serde_json::json!({
            "id":"x","kind":"open_ai_compatible","model":"model",
            "endpoint":"https://example.org","local":false,
            "credential_reference":"secret-token","capabilities":{"streaming":false,"tools":false,"structured_output":false}
        })).is_err());
        assert!(!fs::read_to_string(&path)
            .unwrap()
            .contains("credential_reference"));
        let changed = ProfileMetadata {
            model: "model-b".into(),
            ..profile
        };
        store.change(Some(changed), "one", true).unwrap();
        drop(store);
        let restarted = ProfileStore::open(&path).unwrap();
        assert_eq!(restarted.list().unwrap()[0].model, "model-b");
        restarted.change(None, "one", false).unwrap();
        assert!(ProfileStore::open(&path)
            .unwrap()
            .list()
            .unwrap()
            .is_empty());
        fs::write(&path, br#"{"version":1,"profiles":[],"api_key":"secret"}"#).unwrap();
        assert!(ProfileStore::open(&path).is_err());
        let _ = fs::remove_dir_all(dir);
    }
}
