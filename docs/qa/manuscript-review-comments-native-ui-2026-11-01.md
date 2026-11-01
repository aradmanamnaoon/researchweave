# F03 — project-scoped immutable reviewer comments in the native Manuscript UI

Date: 2026-11-01. Source: `crates/researchweave-project/src/lib.rs`, `crates/researchweave-evidence/src/manuscript_comments.rs`, `crates/researchweave-desktop/src/manuscript_review_anchor.rs`, `src/main.rs` and `ui/main.slint`.

## Workflow

The collapsed Manuscript **Reviewer comments** panel takes a reviewer label, bounded comment text, and an exact unique quote copied from the **latest saved** version of a named section. The desktop reads that immutable `writing.section_history` from the active project, independently checks the body's SHA-256, locates the quote as a unique UTF-8 substring, and converts its byte position to **Unicode scalar offsets** (not grapheme-cluster or cursor coordinates). Missing or repeated quotes are refused rather than guessed.

**Preview comment** calls the trusted project-bound `writing.comment_record` preview. The backend rechecks project CAS, source manuscript revision, SHA, exact quoted span, reviewer metadata and overlap; the response exposes only hashed/redacted comment and reviewer details plus a preview-binding digest. The desktop validates a no-write preview before staging its exact arguments and digest. The digest is **not** a secret, digital signature or user identity proof.

**Record comment** is a different, explicit user action. It consumes the pending preview, compares the current manuscript ID/section/quote/reviewer/text to the approved arguments, then executes through the existing one-use host authorization and project revision checks. The backend revalidates source and overlap *inside* the atomic transaction and adds a new immutable comment and hash-chain event; manuscript text is untouched. Any input or manuscript draft edit invalidates the pending preview. Project switch also clears the form, results and pending approval. **Load comments** shows historical, current or invalid source anchors without silently relocating them.

## Schema and validation

SQLite schema v6 adds `manuscript_comments` with a foreign key to its exact `(manuscript_id, section, source_revision)` and `UPDATE`/`DELETE` denial triggers, installed transactionally through `execute_batch` on v5→v6 migration. The explicit project migration flow remains necessary for older projects; it backs up the original first. The backend stores full comments locally but records only hashes in the provenance event, not sensitive comment text. The source tests cover Unicode anchors, stale project/source/actor changes, different preview/execution request IDs, overlap refusal, bounded size and single-use CAS, migration integrity and RWENC1 archive recovery. A reviewer label is user-supplied; no multi-user authentication or collaborative permission model is claimed.

The native UI is an early vertical slice, **not** Microsoft Word Track Changes. It lacks accepted/rejected edit diffs, comment replies, cursor-selection anchoring, rendered margin balloons, multi-reviewer ACL, DOCX reviewer-note round-trip, and native screen-reader acceptance. Source tests and strict Clippy are necessary but not sufficient for installed Windows/macOS/Linux acceptance.

## Reproducible source verification

```powershell
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_BUILD_JOBS='1'
cargo test --offline --locked --workspace --all-features -j 1
cargo clippy --offline --locked --workspace --all-targets --all-features -j 1 -- -D warnings
cargo fmt --all -- --check
git diff --check
```

No successful installed native GUI test or full Word interoperability is claimed by this source-only record. Use a synthetic project for any future F03 native scenario, and preserve the original manuscript body and event-chain checks before and after approval.
