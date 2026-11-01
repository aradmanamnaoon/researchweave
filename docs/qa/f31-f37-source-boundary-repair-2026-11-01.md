# F31/F37 source-boundary repair — 2026-11-01

## Scope and claim limits

This record describes source changes and local lightweight checks made on the
`mission/completion-20261031` branch after `1096f62`. The exact new commit,
hosted build, Rust unit results, and installed GUI verdict must be recorded
separately after they actually exist. **These repairs do not complete F31 or
F37 product parity and do not authorize a public release.**

## F31 — persisted manuscript to inert Quarto source

Previous risk: `writing.quarto_source_preview` accepts a caller-supplied valid
document AST. The native preparation projected `writing.inspect` correctly,
but the lower-level physical exporter previously re-rendered the caller AST
at final Save without independently proving that its body came from the
persisted manuscript. An internal caller could have conferred misleading
source-bound provenance on a different valid AST.

Repair: `manuscript_quarto_source::attest_source` derives the manuscript
identity from the canonical document title, independently fetches
`writing.inspect`, verifies persisted body SHA-256 receipts, and compares the
complete reconstructed AST to the supplied one. A private `SourceManifest`
binds manuscript ID, project revision, canonical AST digest, per-section
identity/revisions/body digest, and citation-array digests. Preparation
stores this manifest. Final Save independently re-inspects and reprojects,
then requires identical source manifest, project identity/revision, generated
bytes and SHA-256 before the existing single-use approval and exclusive
`create_new(true)` physical write. Original title-page metadata, citation
positions, rich formatting and Quarto execution are still not present.

Adversarial Rust test cases were added for a forged but syntactically valid
AST/title, a mismatched source body hash, a rehashed modified body, changed
section revisions/citations and direct persisted SQLite mutation without a
project-revision advance. Test implementation is **not** proof of execution.

## F37 — PDF caption-source identity and safe search geometry

Previous risk: a PDF caption scan exposed the SHA-256 of the scanned source,
but clicking the caption reopened the path without verifying source bytes.
An attacker or external program could replace the PDF at the same path. Path
edits could also leave a previous asynchronous rendered page visible.

Repair: each displayed caption carries the scan's SHA-256. The caption click
clears old rendered pixels, invalidates older work, and submits its SHA to the
native render callback. `render_search_at_verified` reads no more than 128 MiB
through one handle and verifies the exact bytes it passes to PDFium against
the scan's SHA-256. Substitution refuses the render and clears obsolete
caption candidates; ordinary user-triggered PDF navigation does not claim
scan-source verification. Path edits, native picker selections and project
changes invalidate stale page jobs and rendered state.

The PDFium extracted Unicode stream may differ from positioned glyph indices
because of synthesized whitespace or unsupported Unicode. Text search still
counts literal occurrences; highlight rectangles are now withheld unless
the complete text/glyph streams align 1:1 and the selected glyph geometry is
finite and contained in the page bounds. Per-page text loading now requests
a bounded character budget. This is conservative: valid matches may have no
highlight until an authoritative PDFium offset mapping is implemented.

Adversarial Rust test cases were added for same-path/same-length source
replacement, digest mismatch, multibyte UTF-8 match offsets, synthetic
whitespace, missing Unicode and invalid geometry. These are unit fixtures,
not physical installed GUI acceptance. F37 still extracts **caption anchors
only**, not figure pixels or table structure.

## Evidence and outstanding gates

Local checks run against the modified workspace on 2026-11-01:

- `python -m unittest discover -s scripts/qa -p 'test_native_*.py' -q`:
  45 source/contract tests passed after the complete patchset.
- `python -m unittest discover -s scripts/release -p 'test_*.py' -q`:
  7 tests passed.
- `cargo fmt --all -- --check`: passed.
- `git diff --check`: passed.

**Not established by these checks:** a successful new-source Rust compilation,
native PDFium test execution, an installed F31/F37 user interaction, or
scientific feature acceptance. The hosted quality and installed-candidate
runs for source `1096f62` are historical relative to this patchset and cannot
certify these repairs. Do not advance any F01–F45 ledger row to
`RELEASE_VERIFIED` on source contracts alone. The separate Liara CAS and
encrypted restore gates remain unresolved.

## Follow-up: bounded find-next and installed native regression harness

The `find_next_matching_page` path was additionally changed from the default
PDFium text extraction to `text_with_limit(MAX_PAGE_GLYPHS)`, sharing the
120,000-character preallocation ceiling with page rendering. The pinned
`firecrawl-pdfium` 0.1.0 implementation returns `TextTooLarge` **before**
allocating positioned glyphs when the page exceeds the limit; this is a
refusal, not silent truncation or a false claim that the page lacks a match.

The Windows installed UIA smoke script now also *attempts* a deterministic
real native F37 scan/navigation test: a disposable valid PDF with both figure
and table captions is generated on the host, independently hashed, opened
through the real picker, scanned and clicked. The test then substitutes a
same-length distinct PDF at the exact same path and demands a source mismatch
refusal, no stale page pixels, cleared caption controls and an unchanged
project database snapshot. The fixture/parser and source-contract checks
pass. **It has not yet passed on an installed application**, and its native
canvas/caption visibility observations must be checked against actual CI
results. F37 remains partial.
