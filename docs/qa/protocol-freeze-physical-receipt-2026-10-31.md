# Physical local protocol baseline receipt — verification ledger

Source branch `mission/freeze-physical-receipt-20261031`, based on verified `a1887cc49f153d378450f2c205c226c136ca6c67`. Date: 2026-10-31.

## Research integrity and authorization

The new read-only, project-scoped `protocol.freeze_receipt` operation constructs deterministic Markdown from **the stored and revalidated baseline event**, not editor fields, with the complete canonical version SHA-256, local event hash/sequence, amendment count and project/protocol identity. The actor and local system timestamp are explicitly unverified; no external preregistration, submission, trusted timestamp, or external identity is asserted. Arbitrary record contents appear as indented JSON, not executable Markdown directives. An unfrozen baseline, wrong project, invalid or tampered historical version fails closed.

The desktop **Prepare baseline receipt .md** action invokes the read-only operation via the existing bounded physical-artifact adapter. Preparation does not write to disk. **Save verified receipt** is an independent, user-initiated `SensitiveExport` with one-use approval and audit; it rechecks the currently active canonical project and revision, regenerates the exact authoritative bytes, compares their SHA-256, requires an absolute `.md` filename in an existing directory, creates a new file only, and refuses replacement or stale reuse. Saving is local and never submits or uploads.

## Verification

1. Rust backend `freeze_preserves_protocol_version_and_exposes_later_amendments_without_relock`: passed, now covers receipt-before-freeze refusal, genuine freeze event hash, unchanged baseline digest after later amendments, project-scope mismatch, and tampered-version refusal.
2. Rust desktop `frozen_protocol_receipt_requires_approved_one_use_file_save_and_revalidates_amendments`: passed. Builds a disposable project, creates a protocol, rejects an unfrozen receipt, previews and records its freeze, prepares immutable Markdown, rejects wrong-screen save and wrong extension, physically writes once under audited approval, verifies exact SHA-256 and local semantics, refuses duplicate save, verifies host audit and rejects a stale receipt after a later amendment; freshly prepared receipt reflects amendment count without changing the baseline hash.
3. Native Linux Slint GUI on a private Xvfb/AT-SPI session: passed. The operator performs real protocol creation, freeze preview and approval, prepares the receipt, enters an absolute destination in the native control, explicitly saves an actual `.md`, reads it from disk, checks independent SHA-256 and local-only provenance, checks visible digest, attempts a duplicate Save without overwriting, and verifies SQLite still has exactly one freeze event. The remainder of the full notebook/manuscript/datasets/statistical-report/project isolation/reopen regression passed.

Full successful native evidence in `docs/qa/mission-xvfb-20261031-freeze-physical-r7/` (65 files, ~3.6 MB), including `verified-local-protocol-baseline.md` and screenshots, accessibility trees, binary digest and process log. Required markers observed:

```text
LOCAL_PROTOCOL_FREEZE_PHYSICAL_MARKDOWN_SHA_NO_OVERWRITE_OK
LOCAL_PROTOCOL_FREEZE_ONE_TIME_DIGEST_AND_NO_PREVIEW_WRITE_OK
LOCAL_PROTOCOL_FREEZE_POST_AMENDMENT_PROVENANCE_OK
MANUSCRIPT_METHODS_AUTOSAVE_SQLITE_VERIFIED
AT_SPI_NAVIGATION_PROBE_OK
ISOLATED_XVFB_TEST_DONE
```

Source-built native Linux desktop binary SHA-256 at the successful run: `71f1f94cbca3e297c08f198e15df2c9a146688c96ee1a11cc425100ea80fed10`.

Windows focused evidence and desktop tests passed; strict desktop/evidence Clippy passed before the cross-platform regression run. Windows and Linux **full-workspace** attempts on this source subsequently failed at compiler/linker infrastructure rather than assertion failures: Windows `rustc` reported a 2 MiB memory-allocation failure while simultaneously building another workspace; Linux `rust-lld` reported a truncated cached `libresearchweave_evidence-*.rlib` when multiple worktrees reused one shared target directory. These are **not full-workspace green gates**. The affected builds must be retried against isolated targets (or native CI clean checkout) with limited concurrency before release. The successfully executed native Linux desktop GUI and focused tests above remain independently evidenced.

**Unresolved release gates:** exact-commit installed Windows native UIA, macOS Intel/Apple-Silicon installed DMGs, final Linux AppImage/DEB native installation, encrypted archive/restore acceptance with this new event, full accessible screen-reader interaction, and a newly versioned/released cross-platform SHA-256 manifest. The current source is not proof that an installed native package passed; the latest published release has not been superseded.
