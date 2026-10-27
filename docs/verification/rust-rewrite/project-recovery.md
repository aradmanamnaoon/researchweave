# Native project crash-recovery slice — 2026-10-25

ResearchWeave now exposes the Python recovery model through the Rust
`ProjectHandler` without introducing a second project format. Recovery uses the
same verified `.rwproj` archive writer/reader as normal project portability and
therefore inherits archive bounds, manifest SHA-256 verification, object
checksums, schema compatibility checks, validate-before-extract restore and
fresh-destination/no-clobber behavior.

## Routed capabilities

- `project.recovery_snapshot` — `LocalWrite`, approval required and
  expected-revision guarded. The preview is side-effect free. Execution writes
  `<12-digit-revision>-<safe-label>.rwproj` under the project's private
  `.recovery` directory without changing the project revision/event chain.
- `project.recovery_list` — read-only verification of local snapshots. Corrupt
  or cross-project archives are reported as invalid rather than opened.
- `project.recovery_journal` — read-only, integrity-verifies the existing event
  chain and returns committed events after an explicit revision or the latest
  verified recovery snapshot.
- `project.recovery_status` — read-only due/status calculation using revision
  drift and a bounded snapshot-age policy. It never schedules or creates a
  snapshot itself.
- `project.recovery_restore` — `LocalWrite`, approval and expected-revision
  guarded. It accepts only a safe snapshot basename from the current project's
  `.recovery` directory, verifies project identity and restores to a new
  absolute destination whose real parent already exists.

The recovery directory is never created by a read or preview. Existing
`.recovery` symlinks and `.rwproj` symlink entries fail closed. Snapshot count is
bounded to 20, labels to 40 Unicode characters before filename sanitization,
and restore never overwrites an existing path.

## Validation

`cargo test -p researchweave-project --lib` passed 18/18 tests after this slice,
including:

- `recovery_snapshot_list_restore_and_corruption_are_fail_closed`: proves
  read-only status/preview, approval, no project-revision mutation, verified
  listing, restore/reopen, and corrupted-archive detection.
- `recovery_status_and_journal_track_committed_edits_after_snapshot`: proves
  verified event-journal reporting, revision-drift status, stale-CAS rejection,
  a new current snapshot clearing the unsnapshotted-edit state, and age-driven
  refresh status.

`cargo clippy -p researchweave-project --all-targets --all-features` with
`RUSTFLAGS=-D warnings` passed. Existing archive, encrypted archive, migration,
legacy Python fixture and project integrity tests remained green.

## Boundary

The native desktop already has explicit backup/recovery archive UI helpers, but
this verification note does not claim that the new periodic recovery-status and
snapshot capabilities have been scheduled by the desktop UI. The Rust handler
deliberately keeps snapshot creation explicit, matching the Python policy that
the trusted host decides when to create an autosave snapshot.
