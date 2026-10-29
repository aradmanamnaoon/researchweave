use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::Read;
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
    let data = serde_json::to_vec(drafts).map_err(|error| error.to_string())?;
    if data.len() > MAX_DRAFT_BYTES {
        return Err("Writing recovery draft exceeds size limit".into());
    }
    let parent = path.parent().ok_or("Invalid recovery path")?;
    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let temporary = path.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    std::fs::write(&temporary, &data).map_err(|error| error.to_string())?;
    let result = replace_file(&temporary, path).map_err(|error| error.to_string());
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
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
