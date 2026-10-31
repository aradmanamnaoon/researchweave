use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};

const MAX_DRAFT_BYTES: usize = 256 * 1024;

#[derive(Clone, Default, Serialize, Deserialize, PartialEq, Eq, Debug)]
pub struct Drafts {
    pub notebook: String,
    pub manuscript_id: String,
    pub section: String,
    pub citations: String,
    pub body: String,
    #[serde(default)]
    pub notebook_dirty: bool,
    #[serde(default)]
    pub manuscript_dirty: bool,
}

pub fn path(root: &Path, project_id: &str) -> PathBuf {
    let digest = Sha256::digest(project_id.as_bytes());
    root.join("writing-drafts").join(format!("{digest:x}.json"))
}

pub fn load(path: &Path) -> Result<Drafts, String> {
    match std::fs::read(path) {
        Ok(bytes) => {
            if bytes.len() > MAX_DRAFT_BYTES {
                return Err("Writing recovery draft exceeds size limit".into());
            }
            serde_json::from_slice(&bytes).map_err(|_| "Writing recovery draft is corrupt".into())
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(Drafts::default()),
        Err(error) => Err(format!("Cannot read writing recovery draft: {error}")),
    }
}

pub fn save(path: &Path, drafts: &Drafts) -> Result<(), String> {
    let data = serde_json::to_vec(drafts).map_err(|error| error.to_string())?;
    if data.len() > MAX_DRAFT_BYTES {
        return Err("Writing recovery draft exceeds size limit".into());
    }
    let parent = path.parent().ok_or("Invalid recovery path")?;
    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let temporary = path.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|error| error.to_string())?;
    // A successful draft acknowledgement must not depend on dirty pages only
    // held in the process/OS page cache. Keep the old revision intact until
    // the replacement bytes have been flushed to stable storage.
    if let Err(error) = file.write_all(&data).and_then(|_| file.sync_all()) {
        drop(file);
        let _ = std::fs::remove_file(&temporary);
        return Err(format!("Cannot durably write recovery draft: {error}"));
    }
    drop(file);
    let result = replace_file(&temporary, path).map_err(|error| error.to_string());
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result?;
    #[cfg(unix)]
    std::fs::File::open(parent)
        .and_then(|directory| directory.sync_all())
        .map_err(|error| format!("Cannot sync recovery draft directory: {error}"))?;
    Ok(())
}

#[cfg(windows)]
pub(crate) fn replace_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    if !destination.exists() {
        return std::fs::rename(source, destination);
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
    let destination = destination
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
            destination.as_ptr(),
            source.as_ptr(),
            std::ptr::null(),
            0,
            std::ptr::null(),
            std::ptr::null(),
        )
    } == 0
    {
        Err(std::io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
pub(crate) fn replace_file(source: &Path, destination: &Path) -> std::io::Result<()> {
    std::fs::rename(source, destination)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recovers_dirty_unicode_draft_and_isolates_projects() {
        let root = std::env::temp_dir().join(format!("rw-drafts-{}", uuid::Uuid::new_v4()));
        let a = path(&root, "project-a");
        let b = path(&root, "project-b");
        let expected = Drafts {
            notebook: "پژوهش".into(),
            body: "unfinished result".into(),
            notebook_dirty: true,
            manuscript_dirty: true,
            ..Drafts::default()
        };
        save(&a, &expected).unwrap();
        assert_eq!(load(&a).unwrap(), expected);
        let changed = Drafts {
            notebook: "second edit".into(),
            manuscript_dirty: false,
            ..expected.clone()
        };
        save(&a, &changed).unwrap();
        assert_eq!(load(&a).unwrap(), changed);
        assert_eq!(load(&b).unwrap(), Drafts::default());
        let oversized = Drafts {
            body: "x".repeat(MAX_DRAFT_BYTES),
            ..expected
        };
        assert!(save(&a, &oversized).is_err());
        assert_eq!(load(&a).unwrap(), changed);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn failed_new_write_does_not_replace_existing_valid_recovery() {
        let root = std::env::temp_dir().join(format!("rw-drafts-{}", uuid::Uuid::new_v4()));
        let path = path(&root, "stable-project");
        let first = Drafts {
            notebook: "نسخه اول".into(),
            notebook_dirty: true,
            ..Drafts::default()
        };
        save(&path, &first).unwrap();
        let invalid = Drafts {
            body: "x".repeat(MAX_DRAFT_BYTES),
            manuscript_dirty: true,
            ..Drafts::default()
        };
        assert!(save(&path, &invalid).is_err());
        assert_eq!(load(&path).unwrap(), first);
        std::fs::remove_dir_all(root).unwrap();
    }
}
