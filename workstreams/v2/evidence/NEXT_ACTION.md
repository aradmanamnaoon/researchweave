# Next work, in priority order

Verified timeline increment: `project.timeline` and `project.timeline_export` now provide paginated redacted persisted event chronology and reject damaged hash chains. 26 focused tests, Ruff, strict mypy and compile passed after this change. Timestamp re-normalization of legacy events and full UI chronology remain outstanding.

Further branch milestone (before final suite): `reference.merge`/`reference.unmerge` now work with a reviewer rationale and reversible aliases. Fulltext DOCX/EPUB and optional PDF parsing are integrated with project persistence and page checksums; synthesis, risk appraisal, bibliography, manuscript checks and submission packet operations are exposed through the facade. 59 focused tests passed; initial full-tree Ruff/mypy issues remain in concurrently developing `collections.py`, `diagnostics.py`, `recovery.py`, `encrypted_archive.py` and `portability.py`. Re-run quality gates after those changes settle. Full supported PDF parser cannot be exercised in current dependency-free runtime.

1. Extend review protocol registry with multi-source search capture, study/report linkage and versioned standardized full-text exclusion reasons; generate independently checked PRISMA 2020 diagrams and exports. Existing search/retrieval ledger and reconciled counts are implemented.
2. Extend FTS5 with incremental indexing and persist provider lookup evidence for reference identity checks. Live provider checks remain opt-in.
3. Implement reversible logical dedup merge and undo, versioned source extraction, and PDF/DOCX/EPUB parsing with safe optional dependencies.
4. Add migrations from two earlier schema fixtures, authenticated encrypted .rwproj and crash/fuzz archive tests.
5. Add extraction forms, evidence matrix, evidence support classification and complete manuscript citation formatter.
6. Implement export/migration receipts for Zotero/Obsidian/Notion standard user-owned formats.
7. Expand end-to-end demonstrations and tests to support all features, increase branch coverage, run strict mypy and benchmark realistic large inputs.
8. Once operations are independently verified, ask integrator to wire UI and trusted host command bus. The integrator merges the isolated branch and verifies its canonical source path.
