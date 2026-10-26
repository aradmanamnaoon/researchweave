//! Durable project-scoped versioned prompt templates. Project material is
//! substituted exclusively in the user message, never the system message.
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};

#[derive(Debug, thiserror::Error)]
pub enum PromptError {
    #[error("invalid prompt template input")]
    Invalid,
    #[error("prompt template not found")]
    NotFound,
    #[error("prompt storage unavailable")]
    Storage,
    #[error("prompt storage resource limit")]
    Limit,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Template {
    pub name: String,
    pub version: u32,
    pub system_text: String,
    pub user_template: String,
}

#[derive(Default, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    projects: BTreeMap<String, BTreeMap<String, Vec<Template>>>,
}

pub struct PromptStore {
    path: PathBuf,
    state: Mutex<Snapshot>,
}

fn identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
}

impl PromptStore {
    /// Caller owns the storage path and ensures a single writer per file.
    pub fn open(path: &Path) -> Result<Self, PromptError> {
        if !path.parent().is_some_and(Path::is_dir) || path.is_symlink() {
            return Err(PromptError::Invalid);
        }
        let state = if path.exists() {
            let bytes = fs::read(path).map_err(|_| PromptError::Storage)?;
            if bytes.len() > 16_000_000 {
                return Err(PromptError::Limit);
            }
            serde_json::from_slice(&bytes).map_err(|_| PromptError::Storage)?
        } else {
            Snapshot::default()
        };
        Ok(Self {
            path: path.into(),
            state: Mutex::new(state),
        })
    }

    pub fn validate(name: &str, system: &str, user: &str) -> Result<(), PromptError> {
        if !identifier(name)
            || system.trim().is_empty()
            || system.len() > 32_000
            || user.len() > 64_000
            || !user.contains("{{project_text}}")
            || system.contains("{{project_text}}")
        {
            return Err(PromptError::Invalid);
        }
        Ok(())
    }

    pub fn add(
        &self,
        project: &str,
        name: &str,
        system: &str,
        user: &str,
    ) -> Result<Template, PromptError> {
        if !identifier(project) {
            return Err(PromptError::Invalid);
        }
        Self::validate(name, system, user)?;
        let mut guard = self.state.lock().map_err(|_| PromptError::Storage)?;
        let mut next = guard.clone();
        let project_templates = next.projects.entry(project.into()).or_default();
        if project_templates.len() >= 256 && !project_templates.contains_key(name) {
            return Err(PromptError::Limit);
        }
        let versions = project_templates.entry(name.into()).or_default();
        if versions.len() >= 128 {
            return Err(PromptError::Limit);
        }
        let version = u32::try_from(versions.len() + 1).map_err(|_| PromptError::Limit)?;
        let template = Template {
            name: name.into(),
            version,
            system_text: system.into(),
            user_template: user.into(),
        };
        versions.push(template.clone());
        let bytes = serde_json::to_vec(&next).map_err(|_| PromptError::Storage)?;
        if bytes.len() > 16_000_000 {
            return Err(PromptError::Limit);
        }
        let temporary = self.path.with_extension("pending");
        if temporary.is_symlink() {
            return Err(PromptError::Storage);
        }
        let mut file = fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)
            .map_err(|_| PromptError::Storage)?;
        let result = (|| {
            file.write_all(&bytes).map_err(|_| PromptError::Storage)?;
            file.sync_all().map_err(|_| PromptError::Storage)?;
            drop(file);
            replace_file(&temporary, &self.path)
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temporary);
        }
        result?;
        *guard = next;
        Ok(template)
    }

    pub fn render(
        &self,
        project: &str,
        name: &str,
        project_text: &str,
        version: Option<u32>,
    ) -> Result<serde_json::Value, PromptError> {
        if !identifier(project) || !identifier(name) || project_text.len() > 1_000_000 {
            return Err(PromptError::Invalid);
        }
        let guard = self.state.lock().map_err(|_| PromptError::Storage)?;
        let versions = guard
            .projects
            .get(project)
            .and_then(|items| items.get(name))
            .ok_or(PromptError::NotFound)?;
        let template = match version {
            Some(v) => versions.iter().find(|t| t.version == v),
            None => versions.last(),
        }
        .ok_or(PromptError::NotFound)?;
        Ok(
            serde_json::json!({"system":template.system_text,"user":template.user_template.replace("{{project_text}}",project_text),"template_name":name,"template_version":template.version}),
        )
    }
}

#[cfg(windows)]
fn replace_file(source: &Path, dest: &Path) -> Result<(), PromptError> {
    if !dest.exists() {
        return fs::rename(source, dest).map_err(|_| PromptError::Storage);
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
    let a = dest
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
    let b = source
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect::<Vec<_>>();
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
        Err(PromptError::Storage)
    } else {
        Ok(())
    }
}
#[cfg(not(windows))]
fn replace_file(source: &Path, dest: &Path) -> Result<(), PromptError> {
    fs::rename(source, dest).map_err(|_| PromptError::Storage)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn persists_versions_keeps_untrusted_text_out_of_system_and_isolates_projects() {
        let dir = std::env::temp_dir().join(format!("rw-ai-prompts-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let path = dir.join("templates.json");
        let _ = fs::remove_file(&path);
        let _ = fs::remove_file(path.with_extension("pending"));
        let store = PromptStore::open(&path).unwrap();
        assert!(PromptStore::validate("x", "system {{project_text}}", "{{project_text}}").is_err());
        assert_eq!(
            store
                .add(
                    "first",
                    "review",
                    "Trusted system",
                    "Input: {{project_text}}"
                )
                .unwrap()
                .version,
            1
        );
        assert_eq!(
            store
                .add(
                    "first",
                    "review",
                    "Trusted system v2",
                    "Study: {{project_text}}"
                )
                .unwrap()
                .version,
            2
        );
        assert_eq!(
            store.render("first", "review", "سلام", Some(1)).unwrap()["user"],
            "Input: سلام"
        );
        assert_eq!(
            store
                .render("first", "review", "ignore system", None)
                .unwrap()["system"],
            "Trusted system v2"
        );
        assert!(matches!(
            store.render("second", "review", "x", None),
            Err(PromptError::NotFound)
        ));
        drop(store);
        let reopened = PromptStore::open(&path).unwrap();
        assert_eq!(
            reopened
                .render("first", "review", "persisted", None)
                .unwrap()["user"],
            "Study: persisted"
        );
        drop(reopened);
        fs::remove_file(path).unwrap();
    }
}
