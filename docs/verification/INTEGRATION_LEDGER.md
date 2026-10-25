# ResearchWeave V2 Integration Ledger

This ledger records **observed** evidence for `prompts/05_FINAL_INTEGRATION_RELEASE_V2.md`.
It deliberately distinguishes deterministic local acceptance from live-provider, native-platform, and
manual-user verification. A passing domain test alone is not treated as proof of a required integrated
cross-boundary path.

This is a historical integration snapshot. Its test counts and source metrics describe the integration
phase when they were observed. Later `v0.1.0` publication and post-release local hardening are recorded
in [`../release/RELEASE_READINESS.md`](../release/RELEASE_READINESS.md); do not substitute newer counts
into this ledger retroactively.

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
- `99722f0` — canonicalized UI asset integrity hashes so the tracked manifest is stable on the Windows
  checkout used for the final full-suite run.

No push was performed during this integration phase.

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
  output is in `CODE_METRICS.json`, now measured from the requested final source root
  `D:\coding\codex\researchweave\src\researchweave`.
- A fresh focused `detect-secrets` scan over `src` + `tests` reports **10 findings in 8 files**. The only new
  integration finding is the explicitly synthetic password/wrong-password fixture in `test_int_064_sync.py`.
  The full tracked scan reports **119 findings in 26 files**, dominated by deterministic hashes/manifests and
  the focused scan's own hashed metadata. `SECRETS_REVIEW.md` records the reviewed categories; no live
  credential/private research datum was identified. New findings remain release-blocking until reviewed.

### Final Windows package evidence

- Build command: `powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1`
- PyInstaller build: pass on Windows 11.
- ZIP: `dist/ResearchWeave-windows-x86_64.zip`
- ZIP bytes: **170,161,649**
- ZIP SHA-256: `953E2B5CF005FAB23B3F3DE890EAED5A1DF1579F550B6127C7AF995F527C28CE`
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
| 047 | verified-local | Kappa/undefined metric and human adjudication are verified through the shared bus; adjudication is an approved local write with optimistic concurrency and a hashed immutable event that survives restart without rewriting either coder's annotations. |
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
| 077 | verified-local | Original `main` was fast-forwarded data-safely to the validated V2 tip; `src/researchweave` is populated at the requested path, recovery artifacts remain present, locked dependencies were synchronized, runtime imports pass, integration suite is 60 passed/10 skipped, full suite is 701 passed/10 skipped/3 warnings, Ruff/mypy/compileall/skills/README/pip-audit gates pass from the original root. |

## Release blockers that are genuinely external or still partial

The implementation has completed every locally feasible gap identified in this continuation. The remaining
non-local blockers are deliberately not replaced with mocks: live/local model/provider credentials and quotas,
live Zotero/WebDAV/S3 services, native keyboard/screen-reader/performance/visual-regression harnesses, native
Linux/macOS release runners, and native installer uninstall/reinstall behavior. Partial local contracts are
listed individually above rather than hidden behind a blanket Gate B pass.

## Final Gate A/B/C status

- Gate A / recovery: **PASS** — pre-V2 ref/bundle/manifest and untracked prompt files preserved.
- Gate B / integrated Windows branch: **PASS for locally feasible checks**, with per-INT external/partial
  limitations above. Current package and validation evidence are recorded above.
- Gate C / original-root promotion: **PASS locally**. `main` was fast-forwarded from `7d8e647` to the validated
  integration tip without stash, clean, reset, deletion, or overwrite. The requested final source now exists at
  `D:\coding\codex\researchweave\src\researchweave`. The untracked `prompts/`,
  `researchweave-pre-v2.bundle`, and `legacy-tracked-files.pre-v2.txt` all remain present.
- The original checkout's pre-existing `.venv` was stale and initially lacked NumPy/Pandas; this was an
  environment-only collection failure. `uv sync --frozen --extra dev --extra formats --extra release` repaired
  the local environment from the repository lock without tracked-file changes. After synchronization, original-root
  runtime imports passed, integration acceptance passed **60/10**, full pytest passed **701/10** with the same
  three known warnings, Ruff check passed, the configured format scope (`src tests scripts packaging workstreams`)
  reported **358 files formatted**, mypy passed **152 source files**, `compileall` passed, **27 skills** validated,
  README links passed with **6 images**, and `pip-audit --local` reported no known vulnerabilities.
- A raw `ruff format --check .` from the original root is intentionally not the release oracle because it also
  inspects preserved untracked prompt Markdown; an explicit tracked-file probe likewise reaches vendored
  `.agents` skill code that the repository's normal Ruff discovery excludes. Neither user-owned prompts nor
  vendored skill internals were modified to manufacture a clean result.

No push was performed during this integration phase. The repository was locally integrated and promoted;
the external/native limitations listed above remained unverified and therefore prevented a claim of
universal cross-platform/live-service release readiness at this snapshot.
