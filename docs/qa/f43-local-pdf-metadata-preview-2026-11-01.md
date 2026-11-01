# F43 read-only local PDF metadata preview — initial backend slice

Source: `crates/researchweave-library/src/pdf_metadata_suggestions.rs`, registered as project-scoped `reference.pdf_metadata_preview` with `Effect::Read`.

Input is the selected project UUID and a previously indexed PDF `source_id` UUID. The handler rejects deleted or non-PDF sources, missing indexed text, oversized text, corrupt extraction-body SHA-256, malformed source digest, and mismatched expected project revisions. It does not perform network I/O or infer source identities from a filename. It scans at most 32 KiB of already extracted text to offer a weak first-line title hint and bounded literal `10.<registrant>/<suffix>` DOI-pattern matches, with case-insensitive deduplication, Unicode-safe scalar offsets, source/extraction SHA-256, and explicit ambiguous/missing DOI state. These are **unverified candidates only**, not validated bibliographic metadata.

It never writes or merges project references, applies DOI matching automatically, runs Crossref, or verifies the original PDF object bytes. Its output states `preview_only=true`, `automatic_reference_update=false`, `external_doi_verified=false`, `source_pdf_object_bytes_reverified=false`, and requires actual human inspection/approval before any future write. No journal/publisher verification, confidence calibration, citation correctness, PDF page geometry or native GUI workflow is claimed.

Tests cover Unicode title text, literal DOI finding/deduplication, malformed DOI refusal, project-scope/revision refusal, stable reopen, preview=execute read-only output, real project SQLite index receipt, hash corruption refusal, and no project revision or audit event mutation. The indexed PDF text is a **synthetic fixture**: these tests do not prove correct extraction from actual PDFs.

Status remains **PARTIAL**. Native PDF QA, real-document fidelity, trusted approval path, and external verification are still mandatory before any F43 completion claim.
