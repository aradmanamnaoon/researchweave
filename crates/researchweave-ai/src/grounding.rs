//! Host-indexed retrieval. No filesystem crawling, embedding service, or network calls.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};

#[derive(Debug, thiserror::Error)]
pub enum GroundingError {
    #[error("invalid retrieval input")]
    Invalid,
    #[error("retrieval storage error")]
    Storage,
    #[error("retrieval capacity exceeded")]
    Limit,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Passage {
    pub citation_id: String,
    pub source_id: String,
    pub revision: String,
    pub content: String,
}

#[derive(Default, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    projects: BTreeMap<String, BTreeMap<String, Passage>>,
}

pub struct GroundingStore {
    file: PathBuf,
    state: Mutex<Snapshot>,
}

fn identifier(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 128
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.' | b':'))
}

impl GroundingStore {
    pub fn open(file: &Path) -> Result<Self, GroundingError> {
        if !file.parent().is_some_and(Path::is_dir)
            || file.is_symlink()
            || file.with_extension("pending").is_symlink()
        {
            return Err(GroundingError::Invalid);
        }
        let state = if file.exists() {
            let bytes = fs::read(file).map_err(|_| GroundingError::Storage)?;
            if bytes.len() > 16_000_000 {
                return Err(GroundingError::Limit);
            }
            serde_json::from_slice(&bytes).map_err(|_| GroundingError::Storage)?
        } else {
            Snapshot::default()
        };
        Ok(Self {
            file: file.to_owned(),
            state: Mutex::new(state),
        })
    }

    pub fn index(&self, project: &str, passage: Passage) -> Result<(), GroundingError> {
        if !identifier(project)
            || !identifier(&passage.citation_id)
            || !identifier(&passage.source_id)
            || !identifier(&passage.revision)
            || passage.content.trim().is_empty()
            || passage.content.len() > 16_000
        {
            return Err(GroundingError::Invalid);
        }
        let mut guard = self.state.lock().map_err(|_| GroundingError::Storage)?;
        let mut next = guard.clone();
        let entries = next.projects.entry(project.to_string()).or_default();
        if !entries.contains_key(&passage.citation_id) && entries.len() >= 2048 {
            return Err(GroundingError::Limit);
        }
        entries.insert(passage.citation_id.clone(), passage);
        self.save(&next)?;
        *guard = next;
        Ok(())
    }

    /// Remove every passage of one source from one project. Revocation is
    /// idempotent and survives restart; unrelated projects remain untouched.
    pub fn revoke_source(&self, project: &str, source: &str) -> Result<usize, GroundingError> {
        if !identifier(project) || !identifier(source) {
            return Err(GroundingError::Invalid);
        }
        let mut guard = self.state.lock().map_err(|_| GroundingError::Storage)?;
        let mut next = guard.clone();
        let mut removed = 0;
        if let Some(entries) = next.projects.get_mut(project) {
            let before = entries.len();
            entries.retain(|_, passage| passage.source_id != source);
            removed = before - entries.len();
        }
        if removed > 0 {
            self.save(&next)?;
            *guard = next;
        }
        Ok(removed)
    }

    fn save(&self, next: &Snapshot) -> Result<(), GroundingError> {
        let bytes = serde_json::to_vec(next).map_err(|_| GroundingError::Storage)?;
        if bytes.len() > 16_000_000 {
            return Err(GroundingError::Limit);
        }
        let pending = self.file.with_extension("pending");
        let mut handle = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&pending)
            .map_err(|_| GroundingError::Storage)?;
        let saved = (|| {
            handle
                .write_all(&bytes)
                .map_err(|_| GroundingError::Storage)?;
            handle.sync_all().map_err(|_| GroundingError::Storage)?;
            drop(handle);
            replace_file(&pending, &self.file)
        })();
        if saved.is_err() {
            let _ = fs::remove_file(&pending);
        }
        saved?;
        Ok(())
    }

    pub fn search(
        &self,
        project: &str,
        query: &str,
        limit: usize,
        byte_budget: usize,
    ) -> Result<Value, GroundingError> {
        if !identifier(project)
            || query.trim().is_empty()
            || query.len() > 512
            || !(1..=20).contains(&limit)
            || !(1..=32_000).contains(&byte_budget)
        {
            return Err(GroundingError::Invalid);
        }
        let tokens: BTreeSet<_> = query
            .split(|c: char| !c.is_alphanumeric())
            .filter(|s| s.chars().count() >= 2)
            .map(str::to_lowercase)
            .collect();
        if tokens.is_empty() {
            return Err(GroundingError::Invalid);
        }
        let guard = self.state.lock().map_err(|_| GroundingError::Storage)?;
        let mut hits = Vec::new();
        if let Some(passages) = guard.projects.get(project) {
            for passage in passages.values() {
                let lower = passage.content.to_lowercase();
                let score = tokens
                    .iter()
                    .filter(|token| lower.contains(token.as_str()))
                    .count();
                if score > 0 {
                    hits.push((score, passage));
                }
            }
        }
        hits.sort_by(|a, b| {
            b.0.cmp(&a.0)
                .then_with(|| a.1.citation_id.cmp(&b.1.citation_id))
        });
        let mut consumed = 0;
        let mut results = Vec::new();
        for (score, passage) in hits {
            if results.len() == limit {
                break;
            }
            if consumed + passage.content.len() > byte_budget {
                continue;
            }
            consumed += passage.content.len();
            results.push(json!({"citation_id":passage.citation_id,"source_id":passage.source_id,"revision":passage.revision,"content":passage.content,"matched_terms":score}));
        }
        Ok(
            json!({"results":results,"context_bytes":consumed,"policy":"lexical_host_indexed_project_only","no_external_search":true}),
        )
    }
}

#[cfg(windows)]
fn replace_file(src: &Path, dst: &Path) -> Result<(), GroundingError> {
    if !dst.exists() {
        return fs::rename(src, dst).map_err(|_| GroundingError::Storage);
    }
    use std::os::windows::ffi::OsStrExt;
    unsafe extern "system" {
        fn ReplaceFileW(
            a: *const u16,
            b: *const u16,
            c: *const u16,
            d: u32,
            e: *const u8,
            f: *const u8,
        ) -> i32;
    }
    let a: Vec<u16> = dst.as_os_str().encode_wide().chain(Some(0)).collect();
    let b: Vec<u16> = src.as_os_str().encode_wide().chain(Some(0)).collect();
    if unsafe {
        ReplaceFileW(
            a.as_ptr(),
            b.as_ptr(),
            std::ptr::null(),
            0,
            std::ptr::null(),
            std::ptr::null(),
        )
    } == 0
    {
        Err(GroundingError::Storage)
    } else {
        Ok(())
    }
}
#[cfg(not(windows))]
fn replace_file(src: &Path, dst: &Path) -> Result<(), GroundingError> {
    fs::rename(src, dst).map_err(|_| GroundingError::Storage)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn durable_scoped_bounded_and_offline() {
        let dir = std::env::temp_dir().join(format!("rw-ground-{}-{}", std::process::id(), "one"));
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("index.json");
        let _ = fs::remove_file(&file);
        let p = Passage {
            citation_id: "cit:one".into(),
            source_id: "src-one".into(),
            revision: "v1".into(),
            content: "Neurons signal through synapses. حافظه".into(),
        };
        {
            let store = GroundingStore::open(&file).unwrap();
            store.index("project-one", p.clone()).unwrap();
            store.index("project-one", p).unwrap();
            assert_eq!(
                store.search("project-two", "neurons", 5, 1024).unwrap()["results"]
                    .as_array()
                    .unwrap()
                    .len(),
                0
            );
            assert!(store.search("project-one", "neurons", 5, 1).is_ok());
            assert!(store.search("project-one", "neurons", 21, 1024).is_err());
        }
        let store = GroundingStore::open(&file).unwrap();
        assert_eq!(
            store.search("project-one", "synapses", 5, 1024).unwrap()["results"][0]["citation_id"],
            "cit:one"
        );
        assert!(
            store.search("project-one", "password", 5, 1024).unwrap()["results"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        let _ = fs::remove_file(file);
    }

    #[test]
    fn source_revocation_is_durable_idempotent_and_project_scoped() {
        let dir = std::env::temp_dir().join(format!("rw-ground-revoke-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("revocation.json");
        let _ = fs::remove_file(&file);
        let _ = fs::remove_file(file.with_extension("pending"));
        let store = GroundingStore::open(&file).unwrap();
        for (project, citation, source) in [
            ("a", "c1", "s1"),
            ("a", "c2", "s1"),
            ("a", "c3", "s2"),
            ("b", "c4", "s1"),
        ] {
            store
                .index(
                    project,
                    Passage {
                        citation_id: citation.into(),
                        source_id: source.into(),
                        revision: "r1".into(),
                        content: "recalled memory".into(),
                    },
                )
                .unwrap();
        }
        assert_eq!(store.revoke_source("a", "s1").unwrap(), 2);
        assert_eq!(store.revoke_source("a", "s1").unwrap(), 0);
        assert!(store.revoke_source("a", "../bad").is_err());
        drop(store);
        let reopened = GroundingStore::open(&file).unwrap();
        assert_eq!(
            reopened.search("a", "memory", 10, 2048).unwrap()["results"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            reopened.search("b", "memory", 10, 2048).unwrap()["results"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        let _ = fs::remove_file(file);
    }
}
