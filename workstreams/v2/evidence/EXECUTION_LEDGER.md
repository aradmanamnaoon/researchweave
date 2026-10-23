# Execution ledger (append-on-milestone)

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
| RE-004, RE-014..017, RE-020..022, RE-026, RE-030..031, RE-033..036, RE-038, RE-040..049, RE-051..052 | Not implemented or incomplete; consult NEXT_ACTION.md | Pending |

The source is tracked at relative `src/researchweave/evidence/` in isolated branch `rebuild/v2-evidence`. Source layout verification, measured meaningful SLOC, test count and commit SHA are recorded in TEST_RESULTS.md and HANDOFF.md after final local checks.
