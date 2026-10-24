# ResearchWeave V2 Integration Ledger

This ledger records **observed** evidence for `prompts/05_FINAL_INTEGRATION_RELEASE_V2.md`.
It deliberately distinguishes deterministic local acceptance from live-provider, native-platform, and
manual-user verification. A passing domain test alone is not treated as proof of a required integrated
cross-boundary path.

## Provenance and recovery

- Original repository: `D:\coding\codex\researchweave`
- Original pre-V2 `main`: `af5c862d780d65c62a8c083fbfb64bd08a420092`
- Integration branch/worktree: `rebuild/v2-integration` at
  `D:\coding\codex\researchweave-v2-integration`
- Recovery ref: `archive/pre-v2-af5c862d780d` -> original pre-V2 SHA.
- Recovery artifacts intentionally preserved in the original checkout:
  `prompts/`, `researchweave-pre-v2.bundle`, and `legacy-tracked-files.pre-v2.txt`.
- The original checkout has no tracked modifications. A path-collision audit found **zero** collisions
  between those untracked recovery files and integration-branch tracked paths, so a normal fast-forward
  can preserve them without stash, reset, clean, deletion, or overwrite.
- Worker/domain branches were merged in the required evidence -> analysis -> AI -> UI order. Existing
  completed worker features were reused rather than reimplemented.

## Final implementation increments

The final integration continuation added these local commits after the original domain merge/release work:

- `f3b125a` — desktop-approved AI actions routed through the shared command bus.
- `71ed0e3` — advanced scientific analysis exposed through the desktop/shared bus.
- `35ec9ba` — reproducible Python/R syntax export exposed as analysis capabilities; repeated identical
  immutable dataset staging made idempotent.
- `3bb9bb5` — integrated evidence/analysis acceptance and project-aware descriptive analysis routing.
- `54418f6` — INT-001..019 integrated acceptance.
- `9d43ff3` — initial INT-039..077 integration/release acceptance coverage.
- `fd3834e` — integrated row-linked dataset quality screening and leakage warnings.
- `5aaf6eb` — deeper analysis/AI acceptance plus plot log-scale fail-closed behavior and accessible
  caption/data-table payloads.
- `527e6ae` — host-controlled MCP bridge and deterministic encrypted remote-sync integration.
- `bda910d` — positive and privacy-negative mixed-methods integration acceptance.
- `895c673` — clickable recent-history navigation with visible content hash and bus audit hashes.
- `0861a1b` — final Ruff formatting normalization for the new integration slices.

No push was performed.

## Current deterministic/local verification

- Full pytest: **701 passed, 10 skipped, 3 warnings** on Windows / Python 3.12.9. The skips are explicit
  unavailable live/native scenarios, not hidden passes.
- Ruff check: pass.
- Ruff format check: **382 files already formatted** after normalization.
- mypy: **152 source files clean** with the repository's documented `--ignore-missing-imports` policy for
  third-party scientific/document libraries.
- `compileall`: pass for `src/researchweave`.
- Skills validator: **27 skills valid**.
- README local-link validator: pass; **6 local image references**.
- `pip-audit --local`: **no known vulnerabilities found**; the local ResearchWeave package itself is not a
  PyPI dependency and is therefore reported as skipped by pip-audit.
- Source metric: **48,439 substantive first-party Python SLOC across 152 files**. Exact per-file/package
  output is in `CODE_METRICS.json`.
- `detect-secrets` produces heuristic candidates in deterministic hashes and synthetic security fixtures.
  Existing `SECRETS_REVIEW.md` documents the manual review categories; no live credential/private research
  dataset is claimed from the reviewed tracked findings. New findings remain release-blocking until reviewed.

### Final Windows package evidence

- Build command: `powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1`
- PyInstaller build: pass on Windows 11.
- ZIP: `dist/ResearchWeave-windows-x86_64.zip`
- ZIP bytes: **170,160,288**
- ZIP SHA-256: `01233AF9A980126865000EC73057AD01993F2D827D84B06A5ED1AF1E073ADCE2`
- Clean extraction/startup smoke: **pass**.
- Portable package removal retaining a separate user-profile sentinel: **pass**.
- This is portable-retention evidence, **not** a native MSI/OS uninstall/reinstall observation.

## INT-001..077 status matrix

Status vocabulary: **verified-local** = required deterministic/local path observed; **partial** = useful
integrated evidence exists but an exact contract facet remains unobserved; **external/native-blocked** = the
required provider/service/platform/hardware or native harness was unavailable and no mock is substituted for
success.

| INT | Status | Evidence / remaining limitation |
|---|---|---|
| 001 | verified-local | Offline/no-key launch, UI project create, denied unapproved write. |
| 002 | verified-local | Project persistence across service restart plus invalid creation. |
| 003 | verified-local | Protocol create/export and denied unapproved amendment. |
| 004 | verified-local | Archive roundtrip/conflict plus crafted traversal rejection before writes. |
| 005 | partial | Unsupported/future schema migration refuses mutation; successful staging migration path not separately exercised in INT suite. |
| 006 | partial | Stale revision write preserves state; explicit revision-undo happy path is not in integrated INT fixture. |
| 007 | verified-local | Offline bibliography import/list persistence and malformed Base64 failure. |
| 008 | verified-local | Reference merge/unmerge reversible with approval. |
| 009 | partial | Crossref offline hard-stop verified; live public-provider success not observed. |
| 010 | partial | OpenAlex offline hard-stop verified; live public-provider success not observed. |
| 011 | partial | PubMed offline hard-stop verified; live public-provider success not observed. |
| 012 | partial | Anchoring/quote verification through bus uses deterministic text fixture; real/scanned PDF path is covered by domain tests, not this INT fixture. |
| 013 | partial | Quote/anchor integrity negative behavior exists; altered-PDF end-to-end fixture not independently observed. |
| 014 | partial | Source anchor path works; page-navigation-specific integrated fixture remains absent. |
| 015 | partial | Offline search failure path is integrated; complete faceted/paginated happy path remains domain-level. |
| 016 | verified-local | Protocol amendment preserves original and exposes diff/export. |
| 017 | verified-local | Screening blinding/disagreement path through shared bus. |
| 018 | partial | PRISMA counts/incomplete gate integrated; exhaustive full PRISMA fixture breadth remains domain-level. |
| 019 | verified-local | Typed extraction plus missingness behavior integrated. |
| 020-024 | verified-local | Evidence claim/citation/export/submission grouped integrated journey plus domain integrity tests. |
| 025-027 | verified-local | Migration/import preservation and approval behavior integrated with deterministic local fixtures. |
| 028-030 | verified-local | SPSS/spreadsheet/dictionary paths exercised through analysis bus with optional-format environment. |
| 031-038 | verified-local | Advanced statistics grouped integrated execution/failure paths plus scientific domain oracle suites. |
| 039 | verified-local | Meta-analysis pooled oracle, persistence/audit, incompatible-scale refusal. |
| 040 | verified-local | Time-series chronology/timezone path and invalid-input/no-leakage scientific tests. |
| 041 | verified-local | New `dataset.quality` emits row-linked missingness, duplicate-subject, configured test leakage and optional residual-outlier warnings with immutable transformation lineage; invalid configuration fails without stored result. |
| 042 | verified-local | Version-bound Python/R syntax export through desktop/shared bus; unsupported R target rejected. |
| 043 | verified-local | Python runtime requires trusted approval and emits receipt; timeout behavior remains covered by runtime domain suite. |
| 044 | partial | Optional-R absence behavior exists; a live installed R runtime was not observed on this host. |
| 045 | verified-local | Real SVG/PNG artifacts, SHA-256, caption, alt text, structured data table; log scale now fails closed on non-positive input. |
| 046 | verified-local | Durable Unicode qualitative coding and stale-anchor conflict through bus. |
| 047 | partial | Kappa/undefined metric and human adjudication receipt/rationale/audit verified; adjudication is returned/audited but not stored as a separate qualitative-state adjudication event. |
| 048 | verified-local | Positive linked joint display, privacy-minimum behavior, sensitive approval denial and unrelated-project isolation. |
| 049 | verified-local | Local AI capability entry and host/offline policy boundaries. |
| 050 | external/native-blocked | No locally installed/running model endpoint supplied; no fake success. |
| 051 | external/native-blocked | No verified free hosted-provider account/limits supplied; no fake success. |
| 052 | external/native-blocked | No authorized BYO credential/keyring fixture supplied. |
| 053 | partial | Evidence-only retrieval citations/digests and unsupported-query abstention verified; no generated live-model prose answer claimed. |
| 054 | partial | Durable plan/preview/execute/recover and service reopen verified; process-kill/exactly-once execution recovery not observed. |
| 055 | verified-local | Exact one-use approval rejects replay and argument substitution. |
| 056 | verified-local | Offline/network boundary enforced. |
| 057 | verified-local | Privacy/classification and approval boundary integrated with shared bus. |
| 058 | partial | Offline provider failure after proper approval produces no successful/unauthorized fallback and no prompt audit payload; live quota/transport failure not observed. |
| 059 | partial | Durable checkpoint recovery across service reopen verified; hard process-kill recovery not observed. |
| 060 | external/native-blocked | No running authorized Zotero local API instance. |
| 061 | verified-local | Host-injected mock MCP manifest/allowlist, schema/scope enforcement, hostile-description non-escalation, exact approval/replay and payload-free audit. |
| 062 | external/native-blocked | No WebDAV server/credentials supplied. |
| 063 | external/native-blocked | No S3-compatible endpoint/credentials supplied. |
| 064 | verified-local | Two injected app clients share deterministic encrypted CAS backend; divergence preserves local revision, HEAD is not overwritten, wrong password/tamper fail closed. Live service is not claimed. |
| 065 | verified-local | Approved local backup/create/inspect/restore checksum path and denied unapproved operation. |
| 066 | partial | Workspace preset persistence, geometry clamping, restart/list/delete reset verified through desktop gateway; native visual restoration was not automated. |
| 067 | external/native-blocked | Native keyboard-only GUI automation not exercised. |
| 068 | external/native-blocked | Native screen-reader harness unavailable. |
| 069 | external/native-blocked | Timed native long-PDF responsiveness harness unavailable. |
| 070 | external/native-blocked | Native visual-regression reference/oracle unavailable. |
| 071 | verified-local | Activity entry clicked into Reader; visible source content hash and command-bus input/output SHA-256 verified; audit stores no source payload. |
| 072 | verified-local | Reproducible syntax/output receipt through desktop/shared analysis path. |
| 073 | partial | Current Windows portable build and clean-extraction startup pass; Linux/macOS native runner builds and missing-library clean-machine fault injection remain unobserved. |
| 074 | partial | Portable deletion preserves separate user-profile sentinel; native installer uninstall/reinstall retention is not observed. |
| 075 | verified-local (Windows) | Six native Windows screenshots and manifest hashes/metadata exist and README links are validated; no cross-platform screenshot claim. |
| 076 | verified-local | README first-run command plus deterministic create/reopen persistence/invalid-input acceptance; manual outsider usability session not claimed. |
| 077 | pending-promotion | Integration branch gates pass locally; original-root promotion and post-promotion audit must complete before this becomes verified-local. |

## Release blockers that are genuinely external or still partial

The implementation has completed every locally feasible gap identified in this continuation. The remaining
non-local blockers are deliberately not replaced with mocks: live/local model/provider credentials and quotas,
live Zotero/WebDAV/S3 services, native keyboard/screen-reader/performance/visual-regression harnesses, native
Linux/macOS release runners, and native installer uninstall/reinstall behavior. Partial local contracts are
listed individually above rather than hidden behind a blanket Gate B pass.

## Gates before original-root promotion

- Gate A / recovery: **PASS** — pre-V2 ref/bundle/manifest and untracked prompt files preserved.
- Gate B / integrated Windows branch: **PASS for locally feasible checks**, with per-INT external/partial
  limitations above. Current package and validation evidence are recorded above.
- Gate C / original-root promotion: **READY, not yet executed in this ledger snapshot**. `main` is an ancestor
  of the integration branch, the original root has no tracked modifications, and a direct/path-prefix collision
  audit found no conflicts between original untracked recovery data and integration tracked paths. Promotion must
  use normal fast-forward semantics only; no clean/reset/stash/delete is authorized.

After promotion, rerun import/smoke/selected/full validation from the original root, verify the preserved
recovery files are still present, then update INT-077 and this Gate C section. No push is authorized.
