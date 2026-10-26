//! Project-scoped durable conversations. The host selects the storage directory;
//! only user/system/assistant text is persisted, never provider secrets or tools.
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};

#[derive(Debug, thiserror::Error)]
pub enum ConversationError {
    #[error("invalid conversation input")]
    Invalid,
    #[error("conversation not found in project")]
    NotFound,
    #[error("conversation storage failed")]
    Storage,
    #[error("conversation capacity exceeded")]
    Limit,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Message {
    pub sequence: u64,
    pub role: String,
    pub content: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Conversation {
    title: String,
    messages: Vec<Message>,
}

#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    projects: BTreeMap<String, BTreeMap<String, Conversation>>,
}

pub struct ConversationStore {
    file: PathBuf,
    state: Mutex<Snapshot>,
}

fn identifier(input: &str) -> bool {
    !input.is_empty()
        && input.len() <= 128
        && input
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'-' | b'_'))
}

impl ConversationStore {
    /// Open a host-controlled path beneath an existing directory; reject symlinks.
    /// A single store instance serializes writes. Multiple writers to the same
    /// path are unsupported and must be coordinated by the host.
    pub fn open(file: &Path) -> Result<Self, ConversationError> {
        if !file.parent().is_some_and(Path::is_dir) || file.is_symlink() {
            return Err(ConversationError::Invalid);
        }
        let state = if file.exists() {
            let bytes = fs::read(file).map_err(|_| ConversationError::Storage)?;
            if bytes.len() > 32_000_000 {
                return Err(ConversationError::Limit);
            }
            serde_json::from_slice(&bytes).map_err(|_| ConversationError::Storage)?
        } else {
            Snapshot::default()
        };
        Ok(Self {
            file: file.to_path_buf(),
            state: Mutex::new(state),
        })
    }

    fn persist(&self, snapshot: &Snapshot) -> Result<(), ConversationError> {
        let bytes = serde_json::to_vec(snapshot).map_err(|_| ConversationError::Storage)?;
        if bytes.len() > 32_000_000 {
            return Err(ConversationError::Limit);
        }
        let temp = self.file.with_extension("pending");
        if temp.is_symlink() {
            return Err(ConversationError::Storage);
        }
        let mut handle = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|_| ConversationError::Storage)?;
        let result = (|| {
            handle
                .write_all(&bytes)
                .map_err(|_| ConversationError::Storage)?;
            handle.sync_all().map_err(|_| ConversationError::Storage)?;
            drop(handle);
            // Windows does not replace an existing file using rename.
            // Use the OS atomic replace primitive on Windows and rename elsewhere.
            replace_file(&temp, &self.file)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp);
        }
        result
    }

    fn update<R>(
        &self,
        f: impl FnOnce(&mut Snapshot) -> Result<R, ConversationError>,
    ) -> Result<R, ConversationError> {
        let mut guard = self.state.lock().map_err(|_| ConversationError::Storage)?;
        let mut next = Snapshot {
            projects: guard.projects.clone(),
        };
        let result = f(&mut next)?;
        self.persist(&next)?;
        *guard = next;
        Ok(result)
    }

    pub fn create(&self, project: &str, id: &str, title: &str) -> Result<(), ConversationError> {
        if !identifier(project) || !identifier(id) || title.trim().is_empty() || title.len() > 200 {
            return Err(ConversationError::Invalid);
        }
        self.update(|state| {
            let list = state.projects.entry(project.into()).or_default();
            if list.contains_key(id) || list.len() >= 1000 {
                return Err(ConversationError::Limit);
            }
            list.insert(
                id.into(),
                Conversation {
                    title: title.into(),
                    messages: Vec::new(),
                },
            );
            Ok(())
        })
    }

    pub fn list(&self, project: &str) -> Result<Vec<(String, String)>, ConversationError> {
        if !identifier(project) {
            return Err(ConversationError::Invalid);
        }
        let guard = self.state.lock().map_err(|_| ConversationError::Storage)?;
        Ok(guard
            .projects
            .get(project)
            .map(|items| {
                items
                    .iter()
                    .map(|(id, c)| (id.clone(), c.title.clone()))
                    .collect()
            })
            .unwrap_or_default())
    }

    pub fn append(
        &self,
        project: &str,
        id: &str,
        role: &str,
        content: &str,
    ) -> Result<Message, ConversationError> {
        if !identifier(project)
            || !identifier(id)
            || !matches!(role, "system" | "user" | "assistant")
            || content.trim().is_empty()
            || content.len() > 1_000_000
        {
            return Err(ConversationError::Invalid);
        }
        self.update(|state| {
            let conversation = state
                .projects
                .get_mut(project)
                .and_then(|items| items.get_mut(id))
                .ok_or(ConversationError::NotFound)?;
            if conversation.messages.len() >= 10_000 {
                return Err(ConversationError::Limit);
            }
            let message = Message {
                sequence: conversation.messages.last().map_or(1, |m| m.sequence + 1),
                role: role.into(),
                content: content.into(),
            };
            conversation.messages.push(message.clone());
            Ok(message)
        })
    }

    pub fn history(
        &self,
        project: &str,
        id: &str,
        limit: usize,
    ) -> Result<Vec<Message>, ConversationError> {
        if !identifier(project) || !identifier(id) || limit == 0 || limit > 256 {
            return Err(ConversationError::Invalid);
        }
        let guard = self.state.lock().map_err(|_| ConversationError::Storage)?;
        let conversation = guard
            .projects
            .get(project)
            .and_then(|items| items.get(id))
            .ok_or(ConversationError::NotFound)?;
        Ok(conversation
            .messages
            .iter()
            .rev()
            .take(limit)
            .cloned()
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect())
    }
}

#[cfg(windows)]
fn replace_file(source: &Path, dest: &Path) -> Result<(), ConversationError> {
    if !dest.exists() {
        return fs::rename(source, dest).map_err(|_| ConversationError::Storage);
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
        Err(ConversationError::Storage)
    } else {
        Ok(())
    }
}
#[cfg(not(windows))]
fn replace_file(source: &Path, dest: &Path) -> Result<(), ConversationError> {
    fs::rename(source, dest).map_err(|_| ConversationError::Storage)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn restart_project_isolation_and_bounded_history() {
        let dir = std::env::temp_dir().join(format!("rw-ai-{}-{}", std::process::id(), "history"));
        fs::create_dir_all(&dir).unwrap();
        let file = dir.join("history.json");
        let _ = fs::remove_file(&file);
        let _ = fs::remove_file(file.with_extension("pending"));
        {
            let store = ConversationStore::open(&file).unwrap();
            store.create("alpha", "chat", "Research").unwrap();
            store.append("alpha", "chat", "user", "سلام").unwrap();
            store
                .append("alpha", "chat", "assistant", "Response")
                .unwrap();
            assert!(matches!(
                store.append("beta", "chat", "user", "secret"),
                Err(ConversationError::NotFound)
            ));
            assert!(matches!(
                store.append("alpha", "chat", "tool", "{}"),
                Err(ConversationError::Invalid)
            ));
            assert_eq!(store.history("alpha", "chat", 1).unwrap()[0].sequence, 2);
        }
        let reopened = ConversationStore::open(&file).unwrap();
        assert_eq!(
            reopened.history("alpha", "chat", 10).unwrap()[0].content,
            "سلام"
        );
        assert!(reopened.list("beta").unwrap().is_empty());
        assert!(matches!(
            reopened.history("beta", "chat", 10),
            Err(ConversationError::NotFound)
        ));
        assert!(!fs::read_to_string(&file)
            .unwrap()
            .contains("credential_reference"));
        drop(reopened);
        fs::remove_file(file).unwrap();
    }
}
