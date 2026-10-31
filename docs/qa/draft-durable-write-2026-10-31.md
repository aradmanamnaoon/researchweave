# Draft recovery file durability — 2026-10-31

**Scope:** Local writing recovery snapshots for notebook and manuscript text; no project schema changes or remote services. Exact worktree: `mission/prime-20261031` after `2d2e031`.

## Change

`crates/researchweave-desktop/src/writing_autosave.rs` previously wrote to a UUID-named temporary file and atomically renamed/replaced it, but did not force the temporary file contents to stable storage. A sudden power interruption could therefore leave an acknowledged draft without a durable payload. The replacement now uses `OpenOptions::create_new`, `write_all`, and `File::sync_all` **before** the atomic replacement. On Unix, it synchronizes the containing directory after replacement. On error while writing or syncing the temp file, it removes the temp and leaves the prior recovery file intact. Windows uses the existing `ReplaceFileW`/rename logic; Windows parent-directory sync is not claimed.

## Evidence and limitations

- Offline locked Linux desktop targeted test command: `cargo test --locked --offline -p researchweave-desktop writing_autosave -- --nocapture`: **2 passed**. Includes Persian Unicode draft restoration, project isolation, repeated replacement and invalid oversized draft preservation.
- `cargo fmt --all`, `git diff --check` passed. Full workspace and native acceptance to be re-run when manuscript outline integration is complete.
- This is stronger best-effort durability, **not proof of survival of a physical power loss**. No disk fault injection, NTFS flush benchmark, or Windows/macOS crash test was run. The user-facing UI still needs an independent interruption-before-debounce recovery scenario. The recovery file size limit remains 256 KiB, with explicit error upon exceeding it.
