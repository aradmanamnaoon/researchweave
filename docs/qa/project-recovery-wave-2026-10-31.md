# F02 project archive / recovery hardening — 2026-10-31

## Scope

Implemented within `crates/researchweave-project` without schema changes, network calls, dependency changes, visible GUI work, or Git operations. This report records scoped unit-test evidence; it is not a desktop restore certification.

## Previously observed failure modes and fixes

1. **Inconsistent archive under concurrent local edits.** `archive_project` previously called SQLite's online backup and then read the object digests and project metadata (including revision) from the **live** database. If a writer committed a new revision/object after the backup finished, the manifest or object inventory could describe a different state from the archived SQLite database. Archive generation now uses a single frozen SQLite backup to read metadata and select the object inventory, checks SQLite integrity/foreign keys, and validates project metadata. A deterministic interleaving regression confirms that a post-backup edit remains only in the live project; an archived restore retains the original revision and exactly the original object.
2. **Malformed object identifier panic.** The old `digest[..2]` indexing could panic on a malformed SQLite object digest. Archive creation now rejects digests that are not exactly 64 lowercase hexadecimal ASCII characters before any slicing. A negative test inserts an invalid digest and asserts an integrity error and no published archive. It also checks that a missing object fails without publishing a destination.
3. **Future filesystem timestamp suppresses recovery recommendation.** `project.recovery_status` previously calculated negative snapshot age when an existing snapshot's modified time was ahead of the supplied clock, then treated it as fresh indefinitely. Snapshots more than five minutes in the future now trigger `autosave_due=true` with `snapshot_timestamp_in_future`. A deterministic timestamp test uses an older RFC3339 clock to verify this while confirming zero new committed edits.

All changes preserve existing `.rwproj` archive format, approval gates, restore-as-copy semantics and current command response fields (the clock-skew reason is an additive reason string).

## Verification

| Check | Observed outcome |
| --- | --- |
| `cargo test -p researchweave-project --offline --locked` | **PASS** — 23 unit tests, 0 failed; 0 doc tests, 0 failed. Existing Python v0.1.2 plaintext/encrypted fixture compatibility tests passed. |
| `cargo fmt --package researchweave-project -- --check` | **PASS** |
| Workspace Clippy / all-workspace tests | Not run in this worker. Shared drive C was observed at **0 free bytes**, and the prime directed all workers to stop additional Cargo builds. |
| Native GUI / cross-OS restore | Not executed in this wave. |

The scoped test command used the existing shared `C:\Users\saba\AppData\Local\Temp\researchweave-mission-20261031-target` cache, `CARGO_INCREMENTAL=0`, `CARGO_BUILD_JOBS=2`, and no downloads. It completed successfully before the build pause. Package formatting was checked after edits. No caches or unrelated files were removed.

## Limits

**Prime integration update (2026-10-31):** The source-modified Linux workspace passed **181 offline locked unit tests**, strict all-target/all-feature workspace Clippy and an offline desktop build. The tested `crates/researchweave-project/src/lib.rs` SHA-256 is `fe5e5819af7a996eb2c9e09eb4ae26ed0b288922aa31dd90c9d47c37e0457df1`. These tests establish native source-level coverage, not GUI archive/restore acceptance or crash durability.

The archive format uses SHA-256 to detect accidental corruption, not a cryptographic signature that authenticates the producer of an unencrypted archive. Source-object deletion during an archive can still prevent completion; missing files produce an error and a temporary staging file is discarded without publishing an archive. Cross-process crash and power-loss durability, destination filesystem race behavior, cross-platform native GUI restore, and all-workspace integration need separate evidence before release.
