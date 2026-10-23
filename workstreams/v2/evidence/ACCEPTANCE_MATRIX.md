# ResearchWeave V2 evidence — requirement-by-requirement acceptance audit

Audit date: 2026-10-23. Branch: `rebuild/v2-evidence`. Scope: RE-001 through RE-052.
Source and test paths are relative to the evidence worktree. This is an **acceptance audit**, not
a claim that every exposed command satisfies the original complete specification. "Complete"
means the observed offline implementation satisfies the principal behavior and negative checks;
"partial" denotes an explicit missing acceptance aspect. Test names identify relevant synthetic
behavioral evidence, not proof of live-provider, scientific or cross-platform correctness.

| ID | Status | Production implementation and facade | Observed verification / persistence | Remaining original acceptance gap |
|---|---|---|---|---|
| RE-001 | Partial | `storage.py`, `facade.py`; `project.create/open` | `test_workflows.py`, `test_five_journeys.py`; reopen and private defaults | Guided beginner/advanced wizard and lifecycle validation incomplete |
| RE-002 | Complete | `project_format.py`; `project.archive` | `test_workflows.py`, `test_encrypted_archive.py`; manifest checksums and atomic ZIP | Cross-OS runtime testing not available |
| RE-003 | Complete | `project_format.py`; `project.restore/archive_verify` | Malicious traversal, bad payload and restore tests; source restored elsewhere | Different-OS restore untested |
| RE-004 | Partial | `encrypted_archive.py`; three encrypted archive commands | Wrong password, tampering and authenticated roundtrip tests in `test_encrypted_archive.py` | Independent security review, lost-key UX and cross-platform runs not executed |
| RE-005 | Partial | `storage.py`; explicit schema 1→2 migration | `test_review_accounting.py`; backup and migration verification | Wider historical migration chain and schema-0 fixture absent |
| RE-006 | Complete | `storage.py`; mutation revision/event chain | `test_workflows.py`, `test_timeline.py`; stale revisions, replay and tampering denied | Multi-process conflict simulation not run |
| RE-007 | Complete | `storage.py`; immutable attachment CAS | `test_workflows.py`, `test_portability.py`; hashes verified through reopen/restore | Explicit orphan garbage-collection is unimplemented |
| RE-008 | Partial | `storage.py`, `diagnostics.py`; `project.integrity`, `library.diagnostics` | Corruption, missing object, index/duplicate checks; read-only | Complete project-index/dependency graph consistency not audited |
| RE-009 | Partial | `protocols.py`; `question.feedback` | `test_five_journeys.py`, protocol tests; no auto-confirmation | Design-specific coaching breadth and novice guidance incomplete |
| RE-010 | Partial | `protocols.py`; `protocol.create/amend/history` | Versioned immutable amendments survive reopen (`test_workflows.py`) | Structured protocol templates and publication exports incomplete |
| RE-011 | Partial | `bibliography.py`, `library.py`; bibliography import/preview | BibTeX/RIS/CSL/EndNote fixtures, malformed input; original raw preserved | Comprehensive parser format features and reconciliation receipts missing |
| RE-012 | Partial | `bibliography.py`, `library.py`; `reference.validate` | Invalid DOI rejects identity verification; raw record retained | Trusted provider-identity matching and correction/retraction verification absent |
| RE-013 | Partial | `bibliography.py`, `library.py`; `reference.merge/unmerge` | `test_reference_merge.py`; reversible aliases, rationale, no raw deletion | Canonical search/display, metadata conflict merge UI, all reference edges pending |
| RE-014 | Partial | `discovery.py`; `discovery.provider_search` Crossref | Offline mocked HTTP/pagination/timeout checks | Live opt-in endpoint acceptance not run |
| RE-015 | Partial | `discovery.py`; OpenAlex | Mocked source metadata, bounded transport | Live endpoint, credentials/rate quotas not verified |
| RE-016 | Partial | `discovery.py`; PubMed | Mocked E-utilities response tests | Live endpoint and full query result paging unverified |
| RE-017 | Partial | `discovery.py`; Europe PMC | Mocked XML/JSON adapter behavior | Live search and rate behavior unverified |
| RE-018 | Partial | `collections.py`; six collection/tag operations | `test_collections.py`; nested tree, membership and tags persist | Bulk export/import with interop fidelity and alias-awareness pending |
| RE-019 | Complete | `search_index.py`; `library.index_sync/rebuild/health/fts_search` | FTS query and incremental cache persistence (`test_search_index.py`) | Large scale query benchmark not conducted |
| RE-020 | Partial | `fulltext.py`, `library.py`; `library.import/source_pages` | Injected PDF parser fixture and page hash tests | Optional pypdf real-document acceptance and parser-version provenance pending |
| RE-021 | Partial | `fulltext.py`; `needs_ocr` page status | Empty PDF text never represented as OCR; `test_fulltext.py` | Reliable visual scanned-page detection and OCR opt-in absent |
| RE-022 | Partial | `fulltext.py`; DOCX/EPUB source import | Synthetic ZIP, traversal, malicious relationships, Unicode tests | Broad production document fixture matrix and EPUB asset hierarchy incomplete |
| RE-023 | Partial | `documents.py`, `fulltext.py`; `evidence.anchor` | Exact, normalized discrepancy, stale hash and ambiguous relocation checks | Full multi-revision quotation audit and claims validation missing |
| RE-024 | Partial | `fulltext.py`, `library.py` | Highlight offsets and relocation tested; persisted page hashes | Persistent highlight revision/relocation decisions and UI review missing |
| RE-025 | Partial | `library.py`; `evidence.note/notebook_export` | Notes persist/reopen and include source ID | Note revision/tombstone history and controlled readable exports incomplete |
| RE-026 | Partial | `provenance.py`; `provenance.graph` | Cycle/orphan graph verification, provenance tests | Confirmed inter-paper citation edges and source-read state not implemented |
| RE-027 | Partial | `reviews.py`; `review.register` | Stable record and study IDs persist (`test_review_accounting.py`) | Complete many-reports-per-study registry and publication linkage UI missing |
| RE-028 | Partial | `reviews.py`; `review.screen/status/advance` | Blinded independent votes and stage transition; Journey 2 | Complete exclusion taxonomy, role policy and multi-round workflow missing |
| RE-029 | Complete | `reviews.py`; `review.adjudicate` | Real conflict, independent votes and adjudicator rationale persisted | Institutional reviewer authorization belongs to integrator |
| RE-030 | Partial | `extraction.py`; `review.extract` | Typed value, units, missingness, numeric bounds, reopen | User-configurable form templates, version evolution and CSV exports incomplete |
| RE-031 | Partial | `synthesis.py`; `review.bias_assess/bias_history` | Manual domain responses and reopen; no automatic authoritative judgment | Established framework editions and source-anchor-per-domain checks incomplete |
| RE-032 | Partial | `reviews.py`, `prisma_export.py`; `review.prisma/prisma_export` | Journey 2 counts, duplicate reconciliation, Markdown/CSV/Mermaid; incomplete flagged | Full PRISMA 2020 publication-ready diagram/checklist not certified |
| RE-033 | Partial | `extraction.py`; `review.evidence_matrix` | Matrix contains attributable persisted extraction | Multi-outcome unit-preserving CSV/RIS-style exports and display incomplete |
| RE-034 | Partial | `synthesis.py`; `review.finding_add/contradictions` | Verified anchors required; incompatible measures not pooled | Multi-study design comparability and certainty-of-evidence rubric incomplete |
| RE-035 | Partial | `synthesis.py`; `review.gap_add/gaps` | Search/limitations history stored, reopen; uncertainty preserved | Structured priority and life-cycle resolution workflow incomplete |
| RE-036 | Partial | `synthesis.py`; `review.synthesis_compose/outline` | Traceable findings, warning on uncited interpretation, reopen | Complete structured synthesis export and support checker missing |
| RE-037 | Partial | `writing.py`; `writing.section_save/render` | Revisioned sections survive reopen; Markdown export | Rich manuscript lifecycle/editor/version diff incomplete |
| RE-038 | Partial | `publishing.py`; `writing.bibliography` | Deterministic plain/numbered output from mapped references | Full CSL/journal style engine and validated identity pipeline absent |
| RE-039 | Partial | `publishing.py`, `writing.py`; `writing.check/inspect` | Detects missing sections, placeholders and unmapped citations | Claims-to-evidence checking and full submission consistency checks absent |
| RE-040 | Partial | `publishing.py`; `writing.submission_packet` | In-memory checksummed Markdown/text packet; journal check explicit | Complete file packet layouts and venue-specific verified metadata absent |
| RE-041 | Partial | `migration.py`, `interoperability.py`; interop preview/receipt/undo | Zotero/Obsidian/Markdown synthetic fidelity and reversibility tests | General cross-tool mapping and lossless all-field fidelity not attained |
| RE-042 | Partial | `interoperability.py`; Obsidian preview/import/export/undo | Vault links, relative paths, raw-preserving adapters tested | Embed bytes, aliases, nested vault asset export incomplete |
| RE-043 | Partial | `interoperability.py`; Zotero preview/import/receipt | User-owned CSL-JSON, preserved unknown fields and loss report | Full Zotero RDF/SQLite bridge, collection recreation, attached binary transfer absent |
| RE-044 | Complete | `portability.py`; `project.artifact_export` | Portable checksum manifest and bounded ZIP files; `test_portability.py` | More third-party export formats remain optional |
| RE-045 | Complete | `portability.py`; `review.packet_export` | Review packet with privacy approval and provenance, negative tests | Journal-specific masking requires integrator UI controls |
| RE-046 | Partial | `portability.py`; `project.selective_clone` | Source/reference dependency copy, fresh IDs and audit tests | Arbitrary selection graph and comprehensive associated objects missing |
| RE-047 | Partial | `recovery.py`; `project.recovery_*` | Atomic native recovery snapshots and verification tested | Integrated timed autosave/crash scheduler and failure-injection matrix absent |
| RE-048 | Partial | `diagnostics.py`; `library.diagnostics` | Duplicate, missing metadata, corruption, FTS health, read-only checks | All orphan reference edges and unsupported document diagnostics incomplete |
| RE-049 | Complete | `timeline.py`; `project.timeline/timeline_export` | Chain-verified revisions, filter/pagination/export/reopen; tampering rejected | UI calendar view is integrator responsibility |
| RE-050 | Complete | `provenance.py`; `provenance.graph` | Deterministic graph, cycle and orphan checks through tests/reopen | Full citation-event coverage depends on remaining upstream domains |
| RE-051 | Complete | `data_management.py`; `data_management.*` | Versioned inventories, privacy/retention policy, immutable history and export | Cannot certify policy/legal compliance automatically |
| RE-052 | Partial | `reference_monitor.py`; `reference.watch/unwatch/update_*` | Opt-in observation change/retraction flag, raw metadata preserved | Actual background scheduler and live provider update validation missing |

Overall: **52/52 assessed individually; implementation remains partial.** Tests are run with
synthetic, self-authored research data. See `TEST_RESULTS.md`, `journey_traces/`, `LIMITATIONS.md`
and `NEXT_ACTION.md` for observed evidence and remaining work. Production module existence is
not treated as scientific validation.

Contract checkpoint: 104 operations now declare executable typed and bounded
arguments, shared result envelopes and risks. Most recent full suite: 122
passed; 90% coverage; 41 modules; 9,443 meaningful Python SLOC. The 11/41
status split remains conservatively unchanged because deeper format,
scientific and interoperability acceptance remains unresolved.
