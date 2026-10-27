# ResearchWeave DOCX export matrix

Snapshot: 2026-10-26. This matrix records only observed Rust behavior. A green row means a real OOXML artifact was generated and structurally inspected; it does not imply full Microsoft Word round-trip fidelity.

| Workflow | Current DOCX path | Observed verification | Status | Remaining gaps |
| --- | --- | --- | --- | --- |
| Manuscript | writing.manuscript_export with format=docx | Evidence tests parse the generated ZIP local entries and require content types, package relationships, core/app properties, document relationships, document.xml, styles.xml, settings.xml, header1.xml and footer1.xml. Tests verify Persian/Unicode text, XML escaping, single line breaks, semantic Title/Heading1/Normal styles, A4 page settings, page-number field, a 400-paragraph document, empty-input refusal and invalid XML-control sanitization. The Windows desktop exposes a real DOCX button and the broad UIA suite verifies the OOXML MIME receipt and structural feature receipt. | IMPLEMENTED_TESTED | Rich inline formatting, tables, figures/images, captions bound to actual figures/tables, footnotes/endnotes, equations, tracked changes, comments, content controls, bibliography fields, cross-reference fields and Word round-trip testing remain open. |
| Submission packet | `writing.submission_packet` reuses the manuscript exporter and includes `manuscript.docx` alongside the packet bibliography/manifest | Evidence tests validate deterministic ZIP/hash behavior; the broad Windows UIA suite requires the visible packet receipt to contain `manuscript.docx` with the OOXML MIME type, `submission_performed=false`, and `base64_omitted_from_ui=true`. | IMPLEMENTED_TESTED | Journal-specific forms, richer manuscript structures and actual host destination/export UX remain open; packet creation must continue to avoid claiming submission. |
| Protocol | No dedicated DOCX route observed | No DOCX acceptance evidence. | MISSING | Route immutable protocol revisions through the shared document builder, then inspect OOXML and UI export. |
| Research question / proposal | No dedicated DOCX route observed | No DOCX acceptance evidence. | MISSING | Add structured title/question/design/assumption sections and export receipt. |
| Literature review / evidence matrix | No dedicated DOCX route observed | No DOCX acceptance evidence. | MISSING | Add tables with source identifiers, provenance, quotations and review status. |
| Quantitative report | No dedicated DOCX route observed | Native analysis result persistence/plots exist, but DOCX report composition is unverified. | MISSING | Embed verified result tables/figures, exact dataset revision/hash, assumptions and machine-readable provenance. |
| Qualitative report | No dedicated DOCX route observed | Native coding/codebook/mixed-method persistence exists, but DOCX report composition is unverified. | MISSING | Export codes/themes/memos/evidence anchors while distinguishing human and AI-generated interpretation. |
| Systematic-review report | No dedicated DOCX route observed | Screening/PRISMA/extraction routes exist, but DOCX report composition is unverified. | MISSING | Include transparent counts, exclusion reasons, extraction tables and provenance. |
| Dataset/reproducibility report | No dedicated DOCX route observed | Analysis/data quality and provenance routes exist. | MISSING | Export data dictionary, transformations, software versions, hashes and rerun instructions. |

## Current manuscript OOXML contract

The current native exporter is deterministic and dependency-free. It emits an editable WordprocessingML package with semantic paragraph styles, UTF-8 Unicode text, A4 page geometry, one-inch margins, a header, a PAGE footer field, core/extended document properties and stable SHA-256/base64 receipts. Citation tokens remain literal; no fake bibliography-field semantics are invented.

Files: crates/researchweave-evidence/src/publishing_formats.rs, crates/researchweave-evidence/src/lib.rs, crates/researchweave-desktop/ui/main.slint, crates/researchweave-desktop/src/main.rs.

Observed commands:

- cargo test --locked -p researchweave-evidence -> 18 passed.
- cargo clippy --locked -p researchweave-evidence --all-targets -- -D warnings -> passed.
- cargo build --locked -p researchweave-desktop -> passed.
- cargo clippy --locked -p researchweave-desktop --all-targets -- -D warnings -> passed.
- powershell -NoProfile -ExecutionPolicy Bypass -File crates/researchweave-desktop/tests/windows-uia-smoke.ps1 -> passed after the DOCX UI addition, including manuscript DOCX assertions.
- powershell -NoProfile -ExecutionPolicy Bypass -File crates/researchweave-desktop/tests/windows-writing-autosave-uia.ps1 -VisualOnly -Screenshot docs/verification/rust-rewrite/manuscript-docx-ui-v5.png -> DOCX UI checkpoint passed and the screenshot was visually inspected.

Screenshot evidence: docs/verification/rust-rewrite/manuscript-docx-ui-v5.png. The editor, approved-save controls and Markdown/DOCX/HTML/PDF export row remain visible after DOCX generation; raw artifact base64 is intentionally omitted from on-screen JSON while byte length, digest and structural metadata remain visible.
