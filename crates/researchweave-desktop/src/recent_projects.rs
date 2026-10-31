//! Small local, opt-in-by-use recent project index.
//! A shortcut never grants project authority: reopening still flows through
//! the existing project.open router and checks the actual project on disk.

use serde::{Deserialize, Serialize};
use std::{fs, io::Write, path::Path};

const MAX_RECENTS: usize = 8;
const MAX_BYTES: usize = 16 * 1024;
const MAX_TITLE_CHARS: usize = 160;
const MAX_PATH_BYTES: usize = 2048;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct RecentProject {
    pub(crate) title: String,
    pub(crate) path: String,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RecentIndex {
    version: u8,
    entries: Vec<RecentProject>,
}

fn index_path(root: &Path) -> Result<std::path::PathBuf, String> {
    if !root.is_absolute() {
        return Err("Recent-project index requires an absolute application data directory".into());
    }
    Ok(root.join("recent-projects.json"))
}

fn validate(entry: &RecentProject) -> Result<(), String> {
    if entry.title.trim().is_empty()
        || entry.title.chars().count() > MAX_TITLE_CHARS
        || entry.title.chars().any(char::is_control)
        || entry.path.is_empty()
        || entry.path.len() > MAX_PATH_BYTES
        || entry.path.chars().any(char::is_control)
        || !Path::new(&entry.path).is_absolute()
    {
        return Err("Invalid recent-project shortcut".into());
    }
    Ok(())
}

fn ensure_not_symlink(path: &Path) -> Result<(), String> {
    match fs::symlink_metadata(path) {
        Ok(metadata) if metadata.file_type().is_symlink() => {
            Err("Recent-project index must not be a symbolic link".into())
        }
        Ok(metadata) if !metadata.is_file() => {
            Err("Recent-project index is not a regular file".into())
        }
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(format!("Cannot inspect recent-project index: {error}")),
    }
}

pub(crate) fn load(root: &Path) -> Result<Vec<RecentProject>, String> {
    let path = index_path(root)?;
    ensure_not_symlink(&path)?;
    let raw = match fs::read(path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("Cannot read recent-project index: {error}")),
    };
    if raw.len() > MAX_BYTES {
        return Err("Recent-project index exceeds size limit".into());
    }
    let index: RecentIndex = serde_json::from_slice(&raw)
        .map_err(|_| "Recent-project index is corrupt; no shortcuts were overwritten")?;
    if index.version != 1 || index.entries.len() > MAX_RECENTS {
        return Err("Recent-project index has unsupported version or count".into());
    }
    for entry in &index.entries {
        validate(entry)?;
    }
    if index.entries.iter().enumerate().any(|(i, item)| {
        index.entries[..i]
            .iter()
            .any(|prior| prior.path == item.path)
    }) {
        return Err("Recent-project index has duplicate paths".into());
    }
    Ok(index.entries)
}

pub(crate) fn remember(
    root: &Path,
    opened_project: &Path,
    title: &str,
) -> Result<Vec<RecentProject>, String> {
    let project = opened_project
        .canonicalize()
        .map_err(|_| "Cannot remember a missing project directory")?;
    if !project.is_dir() {
        return Err("Recent project is not a directory".into());
    }
    let entry = RecentProject {
        title: title.to_owned(),
        path: project
            .to_str()
            .ok_or("Recent project path is not valid Unicode")?
            .to_owned(),
    };
    validate(&entry)?;
    // Fail closed on a malformed existing index. Do not silently destroy
    // previous history or follow a symbolic link to overwrite a user file.
    let mut entries = load(root)?;
    entries.retain(|old| old.path != entry.path);
    entries.insert(0, entry);
    entries.truncate(MAX_RECENTS);
    let data = serde_json::to_vec(&RecentIndex {
        version: 1,
        entries: entries.clone(),
    })
    .map_err(|_| "Recent-project serialization failed")?;
    if data.len() > MAX_BYTES {
        return Err("Recent-project index exceeds size limit".into());
    }
    fs::create_dir_all(root)
        .map_err(|error| format!("Cannot create recent-project folder: {error}"))?;
    let path = index_path(root)?;
    ensure_not_symlink(&path)?;
    let temporary = root.join(format!(".recent-projects-{}.tmp", uuid::Uuid::new_v4()));
    let mut file = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temporary)
        .map_err(|error| format!("Cannot create recent-project update: {error}"))?;
    if let Err(error) = file.write_all(&data).and_then(|_| file.sync_all()) {
        drop(file);
        let _ = fs::remove_file(&temporary);
        return Err(format!("Cannot durably save recent projects: {error}"));
    }
    drop(file);
    if let Err(error) = crate::writing_autosave::replace_file(&temporary, &path) {
        let _ = fs::remove_file(&temporary);
        return Err(format!("Cannot replace recent-project index: {error}"));
    }
    #[cfg(unix)]
    fs::File::open(root)
        .and_then(|dir| dir.sync_all())
        .map_err(|error| format!("Cannot sync recent-project directory: {error}"))?;
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root() -> std::path::PathBuf {
        let path = std::env::temp_dir().join(format!("rw-recent-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn remembers_and_reorders_real_paths_without_duplicates() {
        let root = temp_root();
        let a = root.join("a");
        let b = root.join("b");
        fs::create_dir(&a).unwrap();
        fs::create_dir(&b).unwrap();
        remember(&root, &a, "پژوهش MRI").unwrap();
        remember(&root, &b, "Methods").unwrap();
        let current = remember(&root, &a, "Updated پژوهش").unwrap();
        assert_eq!(current.len(), 2);
        assert_eq!(current[0].title, "Updated پژوهش");
        assert_eq!(current, load(&root).unwrap());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn bounded_index_ignores_unremembered_projects_and_keeps_latest_eight() {
        let root = temp_root();
        for index in 0..12 {
            let path = root.join(format!("project-{index}"));
            fs::create_dir(&path).unwrap();
            remember(&root, &path, &format!("Project {index}")).unwrap();
        }
        let entries = load(&root).unwrap();
        assert_eq!(entries.len(), MAX_RECENTS);
        assert_eq!(entries[0].title, "Project 11");
        assert_eq!(entries[7].title, "Project 4");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_corrupt_history_without_overwriting_or_creating_shortcuts() {
        let root = temp_root();
        let a = root.join("a");
        fs::create_dir(&a).unwrap();
        let history = root.join("recent-projects.json");
        fs::write(&history, b"not valid json").unwrap();
        assert!(remember(&root, &a, "Research").is_err());
        assert_eq!(fs::read(&history).unwrap(), b"not valid json");
        assert!(remember(&root, &root.join("missing"), "Research").is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rejects_invalid_titles_and_does_not_mutate_existing_history() {
        let root = temp_root();
        let a = root.join("a");
        fs::create_dir(&a).unwrap();
        remember(&root, &a, "Original").unwrap();
        let saved = fs::read(root.join("recent-projects.json")).unwrap();
        assert!(remember(&root, &a, "bad\0title").is_err());
        assert!(remember(&root, &a, &"x".repeat(MAX_TITLE_CHARS + 1)).is_err());
        assert_eq!(fs::read(root.join("recent-projects.json")).unwrap(), saved);
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn refuses_symlinked_index() {
        use std::os::unix::fs::symlink;
        let root = temp_root();
        let a = root.join("a");
        fs::create_dir(&a).unwrap();
        let sentinel = root.join("sentinel");
        fs::write(&sentinel, b"keep").unwrap();
        symlink(&sentinel, root.join("recent-projects.json")).unwrap();
        assert!(remember(&root, &a, "Research").is_err());
        assert_eq!(fs::read(&sentinel).unwrap(), b"keep");
        fs::remove_dir_all(root).unwrap();
    }
}
