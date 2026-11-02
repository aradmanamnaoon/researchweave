# F14 — native candidate selection and preview binding

Source: `reference_dedup_view.rs`, desktop host and `main.slint`. Date: 2026-11-01.

## Interaction contract

The native References workspace has a scrollable list of duplicate *candidates* returned by `reference.dedup_candidates`. Each row presents a bounded, sanitized title pair, a 0–100 metadata-similarity score and whether its metadata conflicts. The rows are **not** automated deduplication recommendations or identity verification. Selecting a row only populates the canonical UUID, duplicate UUID and 64-digit revision-bound candidate fingerprint; it clears the rationale and any pending library authorization. The user must compare the original records, enter a reason, **Preview merge** or **Preview undo**, and separately click **Record reviewed decision**.

The desktop accepts a candidate list only from an actual successful, project-bound, read-only library scan with the exact current revision, no claimed writes or automatic merge, a complete library scan and consistent per-candidate eligibility/status, canonical distinct UUIDs, bounded score and valid digest. A malformed/truncated/stale reply fails closed and exposes no selectable rows. User edits to any of four decision fields invalidate pending approval; the host also compares the current four fields against the original preview arguments immediately before dispatch. It cannot record a different pair than the one the user previewed. Project switching clears the candidate list, selected IDs, digest, rationale, pending preview and screen status.

The existing low-level backend remains authoritative. Its `reference.dedup_approve` requires independently reviewed consistent metadata, matching project revision and fingerprint, and records only an audited reversible alias (never deletes bibliography/source rows). `reference.dedup_restore` is separately previewed and approved. No external scholarly identity has been confirmed by this UI.

## Test scope and limits

`reference_dedup_view.rs` tests real expected wrapper shapes and rejects stale project revisions, fictitious writes or automatic merges, incomplete scans, mismatched candidate counts, self/invalid/noncanonical UUIDs, malformed SHA, impossible score and contradictory review states. Unicode and control/bidirectional text in labels is sanitized without altering underlying stored original records. Run:

```powershell
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_BUILD_JOBS='1'
cargo test --offline --locked -p researchweave-desktop -j 1
cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -j 1 -- -D warnings
cargo fmt --all -- --check
```

Source tests are not installed Windows/macOS/Linux GUI acceptance. A populated-state private native Xvfb/AT-SPI and UIA test must verify actual row selection, restored references and an approved alias with no unintended writes. A selected row cannot prove it is the same scholarly work; that conclusion requires human source comparison. F14 is still PARTIAL.
