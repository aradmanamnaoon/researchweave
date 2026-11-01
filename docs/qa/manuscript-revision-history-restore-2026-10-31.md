# Manuscript revision history and safe restore

Date: 2026-10-31. Parent `e2ca233afe9bdb3ce0b9fc0a54f011a8b0a8ac93`.

## Native user workflow

The Manuscript workspace now has a collapsed-by-default **Revision history / Restore** panel, preserving the primary writing canvas. **Load revisions** reads the project's persisted, section-scoped `writing.section_history` through the authorized read-only host route and displays the six latest revision IDs, SHA-256 body digests, and local edit times. There is no fabricated history or external backup claim. A large document does not overwhelm the UI: restore preview shows at most 2,000 Unicode characters, the actual source SHA-256, the current/source version numbers, and the omitted-character count. The full persisted body and citations are retained for recording, not truncated.

**Preview restore** requires a positive source version, verifies the source exists in the current saved manuscript history and is not already current, and flushes pending notebook/manuscript autosave before binding a project revision to the proposal. It explicitly states that preview did not change the project. The reviewed proposal is held separately from ordinary manuscript save/other evidence previews. **Record restore** checks the exact current project, manuscript/section identity, source revision displayed in the field, and absence of unsaved manuscript edits. It then uses the original `writing.section_restore` host command with the same revision-bound, human-initiated approval and audited mutation semantics as other evidence operations. The backend appends a new immutable version instead of replacing any old version, including exact citations. The native editor and its recovery journal reload the newly recorded persisted bytes. A failed reload is reported as requiring reinspection rather than claiming an unsuccessful write was rolled back.

Project switch invalidates the pending restore proposal. Ordinary manuscript saves use their original independently held approval; no new remote tools, automatic external submission, untrusted HTML, or network egress are involved.

## Validation performed

- Windows Rust `cargo test --offline --locked -p researchweave-desktop --quiet -j 1`: **64 passed, 0 failed**.
- Windows strict `cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -- -D warnings`: **passed**.
- Rust formatting and source whitespace checks: **passed**.
- Existing evidence integration test exercises `writing.section_save` → newer section → `writing.section_history` → `writing.section_restore` creating revision 3 → manuscript export containing restored first version. This is source-level evidence, not a claim that the new GUI controls have passed installed-platform acceptance.
- Expanded `scripts/qa/mission-atspi-navigation.py` to create a genuine further manuscript revision, read real saved SQLite version history, check that preview performs no write, activate the actual native Slint restore controls, prove source and previous versions are unchanged, and prove one new revision has the exact prior body/citations. This new native Linux scenario is **not yet executed successfully** because the local WSL filesystem returned `Input/output error` for system executables during source synchronization. Its future result must be reported separately, not inferred from older Xvfb runs.

## Explicit remaining limits

This is a safe **manuscript section** revision-history/restore workflow. It does not implement Word-compatible track changes/comments, a visual side-by-side semantic diff, peer reviewer identities, journal-specific templates, or automatic reconciliation of conflicting concurrent editors. Full cross-platform installed Windows/macOS/Linux GUI test gates and the original rich-document parity remain incomplete; do not mark ResearchWeave's entire manuscript workstream or product release complete on this evidence alone.
