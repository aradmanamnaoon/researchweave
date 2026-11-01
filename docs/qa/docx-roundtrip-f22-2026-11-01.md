# F22 — bounded DOCX semantic fidelity and independent ZIP/OOXML parsing

**Date:** 2026-11-01
**Exact base:** `origin/mission/completion-20261031` at `95332d679e90dbc62a22ba0119714263797e5563
**Source touched:** `crates/researchweave-evidence/src/publishing_formats.rs
**New evidence:** this QA report. No `lib.rs`, UI, publishing callback, library, manifest, lockfile or Git mutation.

## Existing writer audi

Before F22, `docx()` already generated an offline, deterministic, uncompressed ZIP/OOXML package containing ten members: `[Content_Types].xml`, package relationships, core/app properties, `word/document.xml`, document relationships, styles, settings, header and footer. The document included semantic `Title` / `Heading1` and `Normal` paragraph styles, an A4 page section, a static application header and page-number field. Citation tokens were *literal input text*; no citation verification, CSL processing or dynamic bibliography update was claimed. Old unit tests examined ZIP local headers and strings, but did not independently parse every XML part or ZIP CRC.

F22 found three bounded weaknesses: XML escaping previously admitted illegal XML 1.0 code points U+FFFE/U+FFFF; platform-specific CRLF/CR line endings changed paragraph separation; and splitting paragraphs discarded explicit empty paragraphs.

## Implemented within one existing source file

- Sanitize only code points permitted by XML 1.0 while escaping `& < > " '` in text nodes. Ordinary Unicode (including Persian and emoji) and literal citation tokens remain intact. XML-invalid code points are **removed** (loss is intentional and documented, not an exact round trip of invalid XML input).
- Normalize CRLF and standalone CR to LF before composing DOCX headings, soft line breaks and paragraphs. Preserve explicit internal blank paragraphs as empty `Normal` paragraphs; an entirely empty section body creates no fabricated body paragraph.
- Bound direct DOCX rendering to at most 512 sections, at most 8 MiB combined raw title/body input, and the generated document-XML budget below 16 MiB with reserved ZIP/OOXML overhead. The preexisting external `export()` final-archive bound remains in force.
- Preserve established ten-part package names, relationships, title/heading/citation output semantics, footer field, no-network behavior and read-only submission/scientific-verification flags.

## Regression and independent parsing

The new Rust tests exercise:

1. One `Title Page` and two headings, a title body, three Methods paragraphs including a blank paragraph, empty Conclusion, CRLF-to-LF equivalence and soft line breaks.
2. UTF-8 Persian and emoji, literal `[local-ref-001]` placeholder (not a sourced citation), XML injection-like text, angle brackets, ampersands, and both quotation marks. Word text runs retain `xml:space="preserve"` for surrounding spacing.
3. XML-invalid C0 controls and U+FFFE/U+FFFF sanitization; zero-section refusal, over-512-section refusal, raw input >8 MiB refusal, and expansion into >16 MiB XML refusal.
4. Repeated byte-for-byte determinism, `export("docx")` SHA-256/byte-length agreement, preexisting no-submission and unverified-scientific-claims flags, and a fixed golden hash requiring intentional re-verification when changed.

The fixture's deterministic **SHA-256** is:


f68b6337bbf8be6ea1e8d94a1604ed502736d0a67da56fada3e70f2c190b4cb0


The Rust test writes this generated DOCX **only when** the operator supplies `RW_F22_DOCX_FIXTURE`, e.g., to an existing OS temporary directory. It does not normally write a fixture file or alter source data.

In the Windows worker, the Python 3 standard-library `zipfile.ZipFile` parser independently opened that generated DOCX, validated all 10 expected package members, verified ZIP CRC with `testzip()`, parsed every `.xml` and `.rels` with `xml.etree.ElementTree`, resolved document relationship targets, checked the WordprocessingML namespace and exact 7-paragraph ordered style/text sequence, checked the page-number footer and section properties, and confirmed invalid XML characters were absent. This is **real ZIP/OOXML parsing**, not a full Microsoft Word or LibreOffice import or an editable DOCX re-save/round-trip. No GUI editor was launched.

## Validation and limitations

Commands run from the detached isolated worktree using the **existing** Cargo target directory `D:\coding\codex\researchweave\target\mission-review-search-worker4\target` with `CARGO_INCREMENTAL=0`, `-j 1` and `--offline --locked`:

```powershell
cargo fmt --all -- --check
cargo test --offline --locked -p researchweave-evidence -j 1
cargo clippy --offline --locked -p researchweave-evidence --all-targets -j 1 -- -D warnings
git diff --check


**Final observed verification:** `cargo fmt --all -- --check` **PASS**; offline locked `researchweave-evidence` tests **32 passed, 0 failed, 0 ignored, 0 doc-tests**; strict Clippy with `-D warnings` **PASS**; `git diff --check` **PASS** (an informational Windows line-ending notice only). Independent Python 3 standard-library `zipfile`/`ElementTree` ZIP CRC and OOXML parse **PASS** for ten members and seven ordered paragraphs; actual generated fixture **8,471 bytes**, golden SHA-256 exactly as shown above.

The evidence-crate tests, Clippy and formatting were run locally; final receipts belong to the current isolated worktree and must not be treated as full workspace, native package or Microsoft Office acceptance. The JSON `fidelity` string remains unchanged for compatibility. It describes semantic structure, **not** a claim of fully lossless Word round-trip. No dynamic citation fields, full DOCX styles engine, tables, images, complex layout, tracked changes or manuscript import/reconstruction have been added. An independent Word/LibreOffice real import and visual inspection remain an explicit downstream validation gate.

**Safety:** no network calls, fabricated sources, user project files, Git commits/pushes, new dependency or separate build cache.
