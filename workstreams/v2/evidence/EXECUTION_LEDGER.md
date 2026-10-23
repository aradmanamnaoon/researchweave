# Execution ledger (append-on-milestone)

**Latest 52-row governing acceptance matrix:** `ACCEPTANCE_MATRIX.md`. The
milestones below are historical snapshots; older pending/absent statements
are superseded by the matrix. Read its per-requirement implementation,
facade IDs, tests, persistence checks and remaining scientific/security
limitations before using this branch for integration.

**Final local implementation checkpoint (2026-10-23):** the 52-row matrix now reports
**47 Complete / 5 Partial**. The only partial requirements are RE-014..RE-017 and RE-052 because
live public-provider validation was not authorized/executed. Full Windows regression: **153 passed,
89% coverage, 44 production modules, 11,579 meaningful SLOC, 147 facade operations**; Ruff, strict
mypy and compileall passed. Five end-to-end journeys passed independently. Real `pypdf 6.21.2`
text extraction/encrypted-PDF rejection and encrypted archive interruption cleanup were exercised.
Selective cloning now closes collection/review/protocol dependencies. Provider-watch checks are
explicit network operations and never silently mutate reference metadata.

2026-10-23 contract update: `contracts.py` supplies bounded typed argument
schemas and runtime enforcement for 104 registered facade operations; public
envelope schemas, write/network/privacy risk and constraints accompany the
capability manifest. `test_contracts.py` proves invalid types are rejected
before mutations. Full suite 122 passed, 90% coverage, 41 production modules,
9,443 meaningful SLOC; Ruff, strict mypy and compile passed.

| IDs | Observed behavior and owned files | Status |
|---|---|---|
| AUDIT-001 | Git base audit, initial audit recorded, distinct clean worktree created | Verified |
| RE-001 | SQLite project create/open, private default, Unicode persisted; storage.py, facade.py; beginner test | Implemented |
| RE-002, RE-003 | Native plaintext rwproj export, hash manifest, safe restore; project_format.py; archive tests | Implemented |
| RE-005 | Initial schema 1 create and future schema rejection; storage.py | Partial; N-2 migrations absent |
| RE-006 | Immutable event digest chain, stale revisions, request conflict detection; storage.py | Implemented with tested audit |
| RE-007, RE-008 | SHA-256 objects, read-only corruption scan; storage.py; integrity test | Implemented |
| RE-009, RE-010 | Question checklist, append-only protocol amendments; protocols.py | Implemented; no full study-design wizard |
| RE-011, RE-012 | Four citation parsers and syntax-only DOI checks; bibliography.py, library.py | Partial; provider-based identity verification absent |
| RE-013 | Duplicate candidate scoring, no unsafe auto-merge | Partial; reversible merge absent |
| RE-013-REVERSIBLE | `reference.merge` and `reference.unmerge` preserve raw records in `reference` and store reviewer decisions in `reference_alias` with event hashes; library.py, facade.py, test_reference_merge.py | 2 new focused tests passed; richer conflict metadata and alias-aware result filtering still pending |
| RE-018, RE-019 | Basic reference library and literal local search | Partial; FTS and collections absent |
| RE-019 | Rebuildable SQLite FTS5 index with phrase search; search_index.py; test_fts_and_typed_extraction_roundtrip | Implemented with explicit cache rebuild |
| RE-030, RE-033 | Typed missingness, units, bounds and persisted extraction matrix; extraction.py; test_fts_and_typed_extraction_roundtrip | Partial; full UI and forms pending |
| RE-041, RE-042 | Safe Markdown export preview, provenance receipt, import and soft-delete undo; migration.py; test_markdown_migration_preview_import_undo_and_reopen | Implemented standard Markdown file handoff; complex Notion formats pending |
| RE-014..017 | Opt-in public metadata adapters for Crossref, OpenAlex, PubMed and Europe PMC; strict host permission, bounded responses, cooldown and deterministic HTTP fixtures; discovery.py and test_discovery.py | Mocked adapters verified; live requests untested |
| RE-023, RE-024, RE-025 | UTF-8 text extraction, exact/unverifiable quote anchoring, source-backed notebook | Partial; PDF and highlights UI absent |
| RE-027, RE-028, RE-029 | Review report registration, blinded votes, conflict and adjudication | Implemented basic round |
| RE-032 | Conservative persisted screening arithmetic | Partial; intentionally incomplete PRISMA flow |
| RE-027..032-V2 | Search provenance, per-hit dispositions, duplicate accounting, full-text retrieval, explicit finalized search runs, reconciled PRISMA report/study counts; reviews.py, storage.py, test_review_accounting.py | 3 V2 regression tests pass; external PRISMA report rendering pending |
| RE-005-V2 | Explicit schema 1→2 migration with SQLite backup, transaction and preserved project metadata; storage.py, test_explicit_v1_migration_preserves_data_and_backup | Tested; schema 0 migration not supported |
| RE-037, RE-039 | Manuscript section revisions and unverified citation lint | Partial |
| RE-050 | Provenance graph with orphan/cycle checks | Implemented service; further adversarial tests pending |
| RE-050-VERIFY | Reopen graph equivalence, persisted source/note/anchor causal links, orphan and cycle detection; test_provenance.py | 2 local tests passed |
| RE-049 | Verified chronological event projection, operation filtering, deterministic JSON export and fail-closed detection of tampered events; timeline.py, facade.py, test_timeline.py | Partial: 2 new tests pass, full 26-test suite passes; research-specific presentation and timestamp migration diagnostics remain |
| RE-020..022 | `fulltext.py` bounded PDF adapter, no-text scan flag, DOCX/EPUB extraction and ZIP checks; `library.import` persists page hashes in project SQLite, `library.source_pages` rechecks hashes; tests `test_fulltext.py`, `test_facade_extensions.py` | Partial: synthetic DOCX and EPUB plus injected PDF parser tests pass; live pypdf and cross-platform verification unavailable |
| RE-031, RE-034..036 | Manual appraisals, anchored findings, grouping by matching outcomes, evidence gaps and synthesis via `synthesis.py` facade handlers, `test_synthesis_publishing.py`, `test_facade_extensions.py` | Partial: focused tests passed; full scientific templates and comprehensive provenance audits pending |
| RE-038..040 | `publishing.py` deterministic plain/numbered bibliography, manuscript warnings, explicit unsubmitted publication packet, facade commands | Partial: focused tests passed; full CSL/DOCX/PDF packet export missing |
| RE-004, RE-014..017, RE-020..022, RE-026, RE-030..031, RE-033..036, RE-038, RE-040..049, RE-051..052 | Not implemented or incomplete; consult NEXT_ACTION.md | Pending |
| 2026-10-23 V2 capability expansion | Authenticated encryption; recovery and data-management plans; private export packets; Zotero/Obsidian imports; FTS sync; structured PDF/DOCX/EPUB; bibliographic identity, user-attested citation relationships, anchored research timeline, risk appraisal, evidence gaps, synthesis, publishing; `src/researchweave/evidence/` | See `ACCEPTANCE_MATRIX.md` for 52 distinct statuses; source and facade integration tested, live providers untested |
| JOURNEYS-001..005 | `test_five_journeys.py` and immutable normalized `journey_traces/*.json` | Five executed and passed on Windows; tested reopen, wrong provenance, disagreement, archive restore, and migration undo |
| PRISMA-EXPORT | `prisma_export.py`; `review.prisma_export`, `test_prisma_export.py` | Markdown, CSV and diagnostic Mermaid, unreconciled claims marked incomplete |
| RE-012-IDENTITY | `identity.py`, `reference_identity.py` with `reference.identity_record`, `reference.compare_metadata`, opt-in `reference.provider_identity` | Candidate mismatches and catalog-reported DOI distinguished; no claim support asserted; mocked network only |
| RE-026-CITATIONS | `citation_graph.py` and `reference.citation_*` command family | Anchored links rechecked against original source hashes; unanchored manual citations clearly labeled, never infer paper read |

The source is tracked at relative `src/researchweave/evidence/` in isolated branch `rebuild/v2-evidence`. Source layout verification, measured meaningful SLOC, test count and commit SHA are recorded in TEST_RESULTS.md and HANDOFF.md after final local checks.
