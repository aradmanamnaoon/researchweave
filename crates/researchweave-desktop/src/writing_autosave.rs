use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
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

/// Journal identity includes the canonical physical project directory.
/// Archive restoration retains the original UUID, so UUID-only journals
/// would otherwise contaminate an independent restored project copy.
pub fn scoped_path(root: &Path, project: &Path, project_id: &str) -> Result<PathBuf, String> {
    let canonical = project
        .canonicalize()
        .map_err(|error| format!("Cannot resolve writing project path: {error}"))?;
    let mut digest = Sha256::new();
    digest.update(project_id.as_bytes());
    digest.update([0]);
    digest.update(canonical.as_os_str().as_encoded_bytes());
    let fingerprint = digest.finalize();
    Ok(root
        .join("writing-drafts")
        .join(format!("scoped-{fingerprint:x}.json")))
}

/// Old UUID-only journals contain no authoritative project directory.
/// A user must explicitly choose which project, if any, adopts that draft.
pub fn load_for_project(root: &Path, project: &Path, project_id: &str) -> Result<Drafts, String> {
    let scoped = scoped_path(root, project, project_id)?;
    if scoped.exists() {
        return load(&scoped);
    }
    let legacy = path(root, project_id);
    if !legacy.exists() {
        return Ok(Drafts::default());
    }
    Err("An older UUID-only writing draft remains preserved. Confirm it belongs to this project and select Adopt legacy draft; no old text was applied automatically.".into())
}

/// Called only from the user's explicit Adopt action. Preserve the old journal
/// and atomically create a new, independently scoped copy without overwrite.
pub fn adopt_legacy_for_project(
    root: &Path,
    project: &Path,
    project_id: &str,
) -> Result<Drafts, String> {
    let scoped = scoped_path(root, project, project_id)?;
    if scoped.exists() {
        return Err(
            "This project already has a scoped writing journal; adoption cannot overwrite it"
                .into(),
        );
    }
    let legacy = path(root, project_id);
    if !legacy.is_file() {
        return Err("No older writing journal exists for this project UUID".into());
    }
    let recovered = load(&legacy)?;
    create_scoped_without_overwrite(&scoped, &recovered)
}

/// Start independent writing in the selected directory while preserving any
/// ambiguous legacy journal for a later deliberate import or forensic review.
pub fn start_fresh_for_project(
    root: &Path,
    project: &Path,
    project_id: &str,
) -> Result<Drafts, String> {
    let scoped = scoped_path(root, project, project_id)?;
    // A damaged scoped journal also blocks project editing. Explicit Start
    // Fresh must preserve that unreadable file before creating a new journal;
    // otherwise both recovery buttons would fail indefinitely.
    if scoped.exists() {
        let metadata = std::fs::symlink_metadata(&scoped).map_err(|error| error.to_string())?;
        if !metadata.file_type().is_file() {
            return Err("Writing journal is not a regular file; no data was replaced".into());
        }
        if load(&scoped).is_ok() {
            return Err(
                "A readable scoped writing journal already exists; it cannot be reset".into(),
            );
        }
        let preserved = scoped.with_extension(format!("preserved-{}.json", uuid::Uuid::new_v4()));
        // Publishing a second hard link is non-overwriting and preserves the
        // exact original bytes. Refuse to proceed on file systems where that
        // preservation cannot be guaranteed.
        std::fs::hard_link(&scoped, &preserved)
            .map_err(|error| format!("Cannot preserve unreadable writing journal: {error}"))?;
        std::fs::remove_file(&scoped).map_err(|error| {
            format!("Unreadable journal was preserved but cannot be moved: {error}")
        })?;
    }
    create_scoped_without_overwrite(&scoped, &Drafts::default())
}

fn create_scoped_without_overwrite(scoped: &Path, recovered: &Drafts) -> Result<Drafts, String> {
    if scoped.exists() {
        return Err(
            "This project already has a scoped writing journal; it will not be overwritten".into(),
        );
    }
    let bytes = serde_json::to_vec(&recovered).map_err(|error| error.to_string())?;
    if bytes.len() > MAX_DRAFT_BYTES {
        return Err("Writing recovery draft exceeds size limit".into());
    }
    let parent = scoped.parent().ok_or("Invalid writing recovery path")?;
    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let stage = scoped.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| {
        let mut file = std::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&stage)
            .map_err(|error| error.to_string())?;
        use std::io::Write as _;
        file.write_all(&bytes).map_err(|error| error.to_string())?;
        file.sync_all().map_err(|error| error.to_string())?;
        // A hard link publishes fully staged bytes and fails if another
        // process has already created this scoped journal.
        std::fs::hard_link(&stage, scoped).map_err(|error| error.to_string())?;
        let verified = load(scoped)?;
        if verified != *recovered {
            return Err("The adopted writing draft did not verify".into());
        }
        Ok(verified)
    })();
    let _ = std::fs::remove_file(&stage);
    result
}

pub fn load(path: &Path) -> Result<Drafts, String> {
    match std::fs::File::open(path) {
        Ok(file) => {
            // Do not allocate the entire file before enforcing the journal
            // limit. A corrupt or adversarial multi-gigabyte file is bounded
            // to at most MAX_DRAFT_BYTES + 1 bytes during recovery.
            let mut bytes = Vec::new();
            file.take((MAX_DRAFT_BYTES + 1) as u64)
                .read_to_end(&mut bytes)
                .map_err(|error| format!("Cannot read writing recovery draft: {error}"))?;
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
    save_with_writer(path, drafts, |file, data| file.write_all(data))
}

// Keep the staging writer injectable so failures before the atomic replacement
// can be tested without depending on disk exhaustion or filesystem timing.
fn save_with_writer(
    path: &Path,
    drafts: &Drafts,
    write_stage: impl FnOnce(&mut std::fs::File, &[u8]) -> std::io::Result<()>,
) -> Result<(), String> {
    let data = serde_json::to_vec(drafts).map_err(|error| error.to_string())?;
    if data.len() > MAX_DRAFT_BYTES {
        return Err("Writing recovery draft exceeds size limit".into());
    }
    let parent = path.parent().ok_or("Invalid recovery path")?;
    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let temporary = path.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        write_stage(&mut file, &data)?;
        file.sync_all()?;
        // Windows ReplaceFileW requires all handles to the staging file closed.
        drop(file);
        replace_file(&temporary, path)?;
        #[cfg(unix)]
        sync_parent_directory(parent)?;
        Ok::<(), std::io::Error>(())
    })()
    .map_err(|error| error.to_string());
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
}

#[cfg(unix)]
fn sync_parent_directory(parent: &Path) -> std::io::Result<()> {
    let directory = std::fs::File::open(parent)?;
    match directory.sync_all() {
        Ok(()) => Ok(()),
        // Directory fsync is unsupported on some Unix-backed filesystems.
        Err(error)
            if error.kind() == std::io::ErrorKind::Unsupported
                || matches!(error.raw_os_error(), Some(22 | 45 | 95)) =>
        {
            Ok(())
        }
        Err(error) => Err(error),
    }
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
    use std::fmt::Write as _;
    use std::time::{Duration, Instant};

    // A "page" in this test is a deterministic synthetic unit of 25 text
    // lines, NOT a Slint page or a guarantee of print pagination. Keep the
    // UTF-8 content mixed-script and non-private to exercise JSON escaping,
    // byte ceilings, newline boundaries, and Unicode scalar persistence.
    const SYNTHETIC_LINE: &str =
        "Question: evidence + method; پژوهش و نتیجه؛ العربية والتجربة; 日本語; e\u{301}; 🧪👩‍🔬; \"quote\" \\ path.\n";
    const EDIT: &str = "\n✍️ ویرایش — تعديل — 改訂 (synthetic interrupted edit)\n";

    struct TempDraftRoot(PathBuf);

    impl TempDraftRoot {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!("rw-long-draft-{}", uuid::Uuid::new_v4()));
            std::fs::create_dir_all(&root).unwrap();
            Self(root)
        }

        fn path(&self, project: &str) -> PathBuf {
            super::path(&self.0, project)
        }
    }

    impl Drop for TempDraftRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn synthetic_drafts(pages: usize) -> Drafts {
        assert!([1, 5, 15, 30, 50].contains(&pages));
        let mut body = String::with_capacity(pages * 4_000);
        for page in 1..=pages {
            writeln!(&mut body, "=== SYNTHETIC PAGE {page:02}/{pages:02} ===").unwrap();
            for line in 1..=25 {
                write!(&mut body, "{line:02}: {SYNTHETIC_LINE}").unwrap();
            }
            body.push('\n');
        }
        Drafts {
            notebook: "Review notes: محقق 🔬; revision α → β\n".into(),
            manuscript_id: "synthetic-paper".into(),
            section: "Results — نتایج".into(),
            citations: "synthetic-ref-1,synthetic-ref-2".into(),
            body,
            notebook_dirty: true,
            manuscript_dirty: true,
        }
    }

    fn median_us(samples: &mut [Duration]) -> u128 {
        samples.sort_unstable();
        samples[samples.len() / 2].as_micros()
    }

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
    fn same_uuid_in_restored_directory_cannot_read_original_draft() {
        let temp = TempDraftRoot::new();
        let host = temp.0.join("host");
        let source = temp.0.join("source");
        let restored = temp.0.join("restored");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::create_dir_all(&restored).unwrap();
        let source_journal = scoped_path(&host, &source, "same-uuid").unwrap();
        let restored_journal = scoped_path(&host, &restored, "same-uuid").unwrap();
        assert_ne!(source_journal, restored_journal);
        let original = Drafts {
            body: "Uncommitted source-only manuscript".into(),
            manuscript_dirty: true,
            ..Drafts::default()
        };
        save(&source_journal, &original).unwrap();
        assert_eq!(
            load_for_project(&host, &source, "same-uuid").unwrap(),
            original
        );
        assert_eq!(
            load_for_project(&host, &restored, "same-uuid").unwrap(),
            Drafts::default()
        );
        save(&path(&host, "same-uuid"), &original).unwrap();
        // A legacy journal cannot be assigned to either arbitrary directory.
        assert!(load_for_project(&host, &restored, "same-uuid").is_err());
        assert_eq!(load(&source_journal).unwrap(), original);
    }

    #[test]
    fn legacy_journal_requires_explicit_adoption_and_preserves_original() {
        let temp = TempDraftRoot::new();
        let host = temp.0.join("host");
        let managed = host.join("projects").join("stable-id");
        std::fs::create_dir_all(&managed).unwrap();
        let legacy = path(&host, "stable-id");
        let original = Drafts {
            notebook: "پژوهش".into(),
            notebook_dirty: true,
            ..Drafts::default()
        };
        save(&legacy, &original).unwrap();
        assert!(load_for_project(&host, &managed, "stable-id").is_err());
        assert_eq!(
            adopt_legacy_for_project(&host, &managed, "stable-id").unwrap(),
            original
        );
        assert!(adopt_legacy_for_project(&host, &managed, "stable-id").is_err());
        assert_eq!(
            load_for_project(&host, &managed, "stable-id").unwrap(),
            original
        );
        assert_eq!(
            load(&scoped_path(&host, &managed, "stable-id").unwrap()).unwrap(),
            original
        );
        assert_eq!(load(&legacy).unwrap(), original);
    }

    #[test]
    fn explicit_start_fresh_preserves_corrupt_scoped_journal_without_resetting_valid_text() {
        let temp = TempDraftRoot::new();
        let host = temp.0.join("host");
        let project = temp.0.join("project");
        std::fs::create_dir_all(&project).unwrap();
        let scoped = scoped_path(&host, &project, "same-uuid").unwrap();
        let original = Drafts {
            body: "Valid draft must never be erased".into(),
            manuscript_dirty: true,
            ..Drafts::default()
        };
        save(&scoped, &original).unwrap();
        assert!(start_fresh_for_project(&host, &project, "same-uuid").is_err());
        assert_eq!(load(&scoped).unwrap(), original);

        let corrupt_bytes = b"{unfinished JSON: \xff}";
        std::fs::write(&scoped, corrupt_bytes).unwrap();
        assert!(load_for_project(&host, &project, "same-uuid").is_err());
        assert_eq!(
            start_fresh_for_project(&host, &project, "same-uuid").unwrap(),
            Drafts::default()
        );
        assert_eq!(load(&scoped).unwrap(), Drafts::default());
        let parent = scoped.parent().unwrap();
        let preserved = std::fs::read_dir(parent)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .filter(|path| {
                path.file_name()
                    .unwrap()
                    .to_string_lossy()
                    .contains(".preserved-")
            })
            .collect::<Vec<_>>();
        assert_eq!(preserved.len(), 1);
        assert_eq!(std::fs::read(&preserved[0]).unwrap(), corrupt_bytes);
    }

    #[test]
    fn unicode_long_form_persistence_reopen_recovery_and_edit_cost() {
        const SAMPLES: usize = 7;
        let root = TempDraftRoot::new();
        // Diagnostic-only timings: no absolute latency threshold or GUI
        // performance claim. Use --nocapture to collect machine-local results.
        eprintln!(
            "WRITING_BENCH_CSV pages,body_chars,json_bytes,save_p50_us,reopen_p50_us,copy_insert_p50_us,recovery_us"
        );
        for pages in [1, 5, 15, 30, 50] {
            let draft = synthetic_drafts(pages);
            let json = serde_json::to_vec(&draft).unwrap();
            assert!(
                json.len() <= MAX_DRAFT_BYTES,
                "{pages} synthetic pages use {} bytes, above {MAX_DRAFT_BYTES}",
                json.len()
            );
            assert!(
                draft.body.len() >= pages * 2_000,
                "the synthetic case must not be mostly empty pages"
            );
            assert!(draft
                .body
                .contains(&format!("SYNTHETIC PAGE {pages:02}/{pages:02}")));
            let expected_hash = Sha256::digest(draft.body.as_bytes());
            let destination = root.path(&format!("unicode-{pages}"));
            let mut save_times = Vec::with_capacity(SAMPLES);
            let mut reopen_times = Vec::with_capacity(SAMPLES);
            let mut edit_times = Vec::with_capacity(SAMPLES);
            let midpoint = draft
                .body
                .char_indices()
                .nth(draft.body.chars().count() / 2)
                .map(|(position, _)| position)
                .unwrap();

            for _ in 0..SAMPLES {
                let started = Instant::now();
                save(&destination, &draft).unwrap();
                save_times.push(started.elapsed());

                let started = Instant::now();
                let reopened = load(&destination).unwrap();
                reopen_times.push(started.elapsed());
                assert_eq!(reopened, draft);
                assert_eq!(Sha256::digest(reopened.body.as_bytes()), expected_hash);
                assert!(reopened.manuscript_dirty && reopened.notebook_dirty);

                // Copying the existing model string and inserting near its
                // middle approximates the Rust-side cost of one text change;
                // it does NOT measure Slint layout/typing or UI responsiveness.
                let started = Instant::now();
                let mut changed = draft.body.clone();
                changed.insert_str(midpoint, EDIT);
                edit_times.push(started.elapsed());
                assert!(changed.starts_with("=== SYNTHETIC PAGE 01/"));
                assert!(changed.ends_with(SYNTHETIC_LINE) || changed.ends_with("\n\n"));
                assert_eq!(changed.len(), draft.body.len() + EDIT.len());
                assert_eq!(changed.matches(EDIT).count(), 1);
            }

            // Simulate a process restart BEFORE the debounced project save:
            // only the journal is persisted, and dirty flags must survive.
            let mut interrupted = draft.clone();
            interrupted.body.insert_str(midpoint, EDIT);
            let expected_edited_body = interrupted.body.clone();
            let started = Instant::now();
            save(&destination, &interrupted).unwrap();
            drop(interrupted);
            let mut recovered = load(&destination).unwrap();
            let recovery_us = started.elapsed().as_micros();
            assert!(recovered.manuscript_dirty && recovered.notebook_dirty);
            assert_eq!(recovered.body, expected_edited_body);

            // Represent a successful routed project flush by clearing both
            // flags in the journal. This does NOT execute the project router.
            recovered.manuscript_dirty = false;
            recovered.notebook_dirty = false;
            save(&destination, &recovered).unwrap();
            assert_eq!(load(&destination).unwrap(), recovered);
            eprintln!(
                "WRITING_BENCH_CSV {pages},{},{},{},{},{},{recovery_us}",
                draft.body.chars().count(),
                json.len(),
                median_us(&mut save_times),
                median_us(&mut reopen_times),
                median_us(&mut edit_times),
            );
        }
    }

    #[test]
    fn near_256k_limit_accepted_one_extra_byte_rejected_without_losing_previous_draft() {
        let root = TempDraftRoot::new();
        let destination = root.path("at-boundary");
        let baseline = Drafts::default();
        let overhead = serde_json::to_vec(&baseline).unwrap().len();
        let mut at_limit = Drafts {
            body: "x".repeat(MAX_DRAFT_BYTES - overhead),
            ..baseline
        };
        assert_eq!(
            serde_json::to_vec(&at_limit).unwrap().len(),
            MAX_DRAFT_BYTES
        );
        save(&destination, &at_limit).unwrap();
        assert_eq!(load(&destination).unwrap(), at_limit);
        at_limit.body.push('x');
        assert!(save(&destination, &at_limit)
            .unwrap_err()
            .contains("size limit"));
        assert_eq!(
            load(&destination).unwrap().body.len(),
            MAX_DRAFT_BYTES - overhead
        );

        // On-disk oversized JSON is rejected, not silently truncated.
        std::fs::write(&destination, serde_json::to_vec(&at_limit).unwrap()).unwrap();
        assert!(load(&destination).unwrap_err().contains("size limit"));
        std::fs::write(&destination, vec![b'X'; MAX_DRAFT_BYTES * 4]).unwrap();
        assert!(load(&destination).unwrap_err().contains("size limit"));
    }

    #[test]
    fn incomplete_temporary_write_does_not_replace_committed_unicode_journal() {
        let root = TempDraftRoot::new();
        let destination = root.path("interrupted-stage");
        let earlier = synthetic_drafts(5);
        save(&destination, &earlier).unwrap();

        // Simulate a crash after a temporary write but before replacement.
        // The application only reads the committed .json file.
        let abandoned = destination.with_extension("incomplete.tmp");
        std::fs::write(&abandoned, b"{\"body\":\"truncated").unwrap();
        assert_eq!(load(&destination).unwrap(), earlier);
        assert!(abandoned.exists());

        let mut latest = earlier.clone();
        latest.body.push_str(EDIT);
        save(&destination, &latest).unwrap();
        assert_eq!(load(&destination).unwrap(), latest);
        assert!(abandoned.exists());

        // A corrupted committed journal must produce an explicit error; it
        // must not masquerade as a clean, empty draft.
        std::fs::write(&destination, b"{\"body\":").unwrap();
        assert!(load(&destination).unwrap_err().contains("corrupt"));
    }

    #[test]
    fn injected_partial_staging_failure_keeps_previous_bytes_and_cleans_temporary() {
        let root = TempDraftRoot::new();
        let destination = root.path("partial-stage-failure");
        let previous = synthetic_drafts(1);
        save(&destination, &previous).unwrap();
        let original_bytes = std::fs::read(&destination).unwrap();
        let mut updated = previous.clone();
        updated.body.push_str(EDIT);

        let error = save_with_writer(&destination, &updated, |file, bytes| {
            file.write_all(&bytes[..bytes.len() / 2])?;
            Err(std::io::Error::other("injected partial staging failure"))
        })
        .unwrap_err();
        assert!(error.contains("injected partial staging failure"));
        assert_eq!(std::fs::read(&destination).unwrap(), original_bytes);
        assert_eq!(load(&destination).unwrap(), previous);
        assert!(std::fs::read_dir(destination.parent().unwrap())
            .unwrap()
            .all(|entry| !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .ends_with(".tmp")));

        // A failed journal update cannot prevent a later valid edit/restart.
        save(&destination, &updated).unwrap();
        assert_eq!(load(&destination).unwrap(), updated);

        let fresh = root.path("failed-first-save");
        assert!(save_with_writer(&fresh, &updated, |_, _| {
            Err(std::io::Error::other("injected first staging failure"))
        })
        .is_err());
        assert!(!fresh.exists());
        assert!(std::fs::read_dir(fresh.parent().unwrap())
            .unwrap()
            .all(|entry| !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .ends_with(".tmp")));
    }

    #[test]
    fn failed_replacement_keeps_error_and_removes_new_temporary_file() {
        let root = TempDraftRoot::new();
        let destination = root.path("directory-is-not-a-draft-file");
        std::fs::create_dir_all(&destination).unwrap();
        assert!(save(&destination, &synthetic_drafts(1)).is_err());
        let journal_dir = destination.parent().unwrap();
        assert!(
            std::fs::read_dir(journal_dir).unwrap().all(|entry| !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .ends_with(".tmp")),
            "failed replacement should not leak UUID .tmp drafts"
        );
    }
}
