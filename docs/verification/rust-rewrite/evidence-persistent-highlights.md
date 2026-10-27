# Persistent highlights and deterministic relocation (schema v4)

## Implementation

- Native project schema advances from v3 to **v4**, adding `evidence_highlights` (immutable source ID, page number, Unicode character offsets, exact quote, 48-character prefix/suffix context, source/content checksum, page checksum, extraction version, creation time) and `evidence_highlight_relocations` (append-only status, candidate count, selected page/offset/hash when proven, review flag, time). Both new projects and backward-compatible migration have the same tables and index. Legacy versions 0–3 migrate using existing backup, integrity and archive paths; no existing anchor is rewritten.
- `evidence.highlight_create` validates a 1-based source page, Unicode character-range span, exact quote, source and page SHA-256 checksums, and text bounds before inserting a record through the shared evidence `mutate` transaction/event chain.
- `evidence.highlight_relocate` searches for exact quotes with original context (prefix/suffix) in the target source's page text. Status is **unchanged** only with the exact original source/page/offset/page hash; **relocated** only with one defensible candidate; otherwise **ambiguous** or **missing**, with no selected replacement, and `review_required=true`. Every attempt appends a relocation record without editing the original highlight.
- `evidence.highlight_history` reads original provenance plus bounded ordered relocation history. Cross-project access is rejected by the existing project-scoped handler.

LocalWrite operations are approval-required in capability metadata and use the existing CommandRouter authority path, explicit expected revision, one-use request IDs, atomic record+project-revision+SHA-256 event transaction, and cloned-database side-effect-free preview. Invalid/ambiguous matches cannot silently change original provenance.

## Limits and differences from Python

Each quote is limited to **100,000 UTF-8 bytes**. Source/page input is limited to **4 MiB each**; at most **1,000 pages**, **1,000 relocation candidates**, and **1,000 history rows** are processed. Offsets are Unicode scalar-value positions, not UTF-8 bytes. If `fulltext_pages` is absent or has no rows, the verified document body is treated as page 1, as in the Python baseline; explicit full-text page geometry is not fabricated. Context filtering is intentionally stricter than the Python quote-only relocation baseline and can conservatively return missing/ambiguous, requiring manual review. No automatic OCR or user confirmation workflow is implemented here.

## Verification

Project migration and archive tests exercise backward compatibility, including old versions and encrypted `.rwproj` archives. Evidence tests cover Unicode-character offset semantics, creation/unchanged/relocated/ambiguous/missing cases, original immutability, restart, stale CAS and replay rejection, isolated snapshot preview and checksum corruption fail-closed behavior. Targeted commands: `cargo fmt --package researchweave-project --package researchweave-evidence`, `cargo test -p researchweave-project -p researchweave-evidence`, `cargo clippy -p researchweave-project -p researchweave-evidence --all-targets -- -D warnings`.
