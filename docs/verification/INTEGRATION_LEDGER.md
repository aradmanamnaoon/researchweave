# ResearchWeave V2 Integration Ledger

This ledger records observed integration work for `prompts/05_FINAL_INTEGRATION_RELEASE_V2.md`.
Claims here are limited to locally observed evidence. External CI and other operating systems are
recorded as pending until actually run.

## Phase 00 — repository provenance and reversible backup

- Status: complete for committed Git history; untracked data remains deliberately untouched.
- Original repository: `D:\coding\codex\researchweave`
- Original `main` SHA: `af5c862d780d65c62a8c083fbfb64bd08a420092`
- Integration branch: `rebuild/v2-integration`
- Integration worktree: `D:\coding\codex\researchweave-v2-integration`
- Recovery ref: `archive/pre-v2-af5c862d780d` -> `af5c862d780d65c62a8c083fbfb64bd08a420092`
- Git bundle: `D:\coding\codex\researchweave\researchweave-pre-v2.bundle` (committed history only)
- Legacy tracked-file manifest source: `D:\coding\codex\researchweave\legacy-tracked-files.pre-v2.txt`
- Original checkout status before integration: `main` with untracked `prompts/`.
- Worker branches all descend from the same `main` SHA:
  - `rebuild/v2-evidence` `bfa5f96678630403e8933b7aca063a43e39aab11`
  - `rebuild/v2-analysis` `b878adde6037ecbcd9146700bb767dcb96bfdd01`
  - `rebuild/v2-ai` `c1ac49e003ac6cf84781cfcfc01f8c059cd652f4`
  - `rebuild/v2-ui` `e00be109f8de4e2a892c5f42496a840b3f164dbb`
- Worker worktree state: evidence, AI and UI clean; analysis contains untracked verification
  outputs. Those files are not part of the committed worker tip and are intentionally untouched.
- Gate C note: final fast-forward promotion to the original checkout is currently blocked while
  that checkout contains untracked files. No stash, cleanup or deletion will be performed.

### Observed commands

```text
git status --short --branch
git worktree list
git branch -avv
git merge-base main <worker-branch>
git ls-tree -r --name-only <worker-branch> -- src/researchweave
git update-ref refs/heads/archive/pre-v2-af5c862d780d <main-sha>
git bundle create researchweave-pre-v2.bundle main
```

### Recovery

Committed pre-V2 state remains addressable as:

```powershell
git -C D:\coding\codex\researchweave show archive/pre-v2-af5c862d780d
```

The bundle is an additional recovery artifact for committed `main`; it does not contain untracked
files or private working-tree data.

## Current next phase

## Phase 01 — worker merge and conflict reconciliation

- Status: complete locally.
- Merge commits, in required order:
  - evidence: `2f2acde` from `bfa5f96678630403e8933b7aca063a43e39aab11`
  - analysis: `7c2aed0` from `b878adde6037ecbcd9146700bb767dcb96bfdd01`
  - AI: `c4239ec` from `c1ac49e003ac6cf84781cfcfc01f8c059cd652f4`
  - UI: `fb6ab24` from `e00be109f8de4e2a892c5f42496a840b3f164dbb`
- No merge conflicts occurred and no worker worktree was modified.
- The first integrated test attempt exposed missing worker-declared dependencies and a text-line-ending
  dependent UI SVG checksum. Shared dependency metadata and SVG normalization were corrected in the
  integration branch.
- Observed after dependency normalization on Windows CPython 3.12.9:
  - evidence: **176 passed**, one expected duplicate-ZIP warning.
  - analysis: **177 passed**, two statsmodels seasonal-start warnings.
  - AI: **138 passed, 2 skipped**.
  - UI: **141 passed**.
- Ruff and first-party mypy/compile checks run during merge inspection were clean for all four domain
  source trees. Scientific third-party packages remain typed according to their upstream metadata;
  analysis validation uses `--ignore-missing-imports` as documented by that worker.

## Phase 03 — dependency normalization (started early to unblock merge verification)

- Added the runtime scientific stack required by the merged analysis package and the audited
  encryption/PDF/credential dependencies used by evidence and AI.
- Added optional `formats` dependencies for XLSX/ODS/Parquet/SAV import support.
- Regenerated `uv.lock` and successfully ran `uv sync --extra dev --extra formats`.
- Declared SVG files as LF-normalized text and refreshed the two UI asset SHA-256 values against the
  checked-out bytes so hashes are stable across Windows checkout behavior.

## Current next phase

## Phase 04/06 — shared contracts, command bus and application composition

- Status: implemented; broader acceptance validation remains in progress.
- Added a versioned `OperationRequest` used by desktop/headless callers, deterministic request/result
  hashing, and the common integration error vocabulary.
- Added a process-local host approval authority. Non-read operations require an exact, expiring,
  one-use approval bound to operation, project, request ID, arguments, revision and actor.
- Added a unified command bus that registers all four worker capability manifests, rejects duplicate
  operation IDs, preserves facade previews, and delegates only after the host gate succeeds.
- Analysis writes receive a fresh analysis-owned one-use `HostCapability` after the shared approval
  succeeds. AI writes/network actions likewise receive an AI-owned signed approval. Evidence is
  instantiated write-capable only behind the shared host gate and remains network-disabled by default.
- Added an SQLite/WAL integration audit containing timestamps, IDs, actor, operation, effect, status,
  error code and SHA-256 input/output hashes. Argument/result payloads are not stored in this audit.
- Replaced the placeholder desktop entry point with the V2 `ResearchWindow` and real application
  composition root. The desktop gateway sends the same `ui.*` operation IDs through the command bus;
  a direct human desktop gesture is the trust event that causes the host to issue its exact one-use
  approval. Existing export/backup/agent confirmation gates remain active inside the UI facade.
- Added `researchweave-cli` using the same composition root for health and capability discovery.
- Connected the UI analysis adapter to the production analysis facade. A UI dataset is staged as an
  ephemeral CSV, imported through the analysis facade with its own capability, analyzed from the
  immutable analysis revision, provenance/hashes are returned to UI result storage, and the staging
  file is deleted afterward.
- Added integration tests for all-domain registration/offline defaults, approval substitution/replay,
  payload-free audit metadata, analysis import/describe routing, production desktop analysis and the
  desktop gateway audit route. Current focused result: **6 passed**.
- Shared source-wide Ruff passes. First-party mypy with `--ignore-missing-imports` passes across
  **151 source files** after removing two obsolete reportlab suppressions exposed by the integrated
  dependency environment.
- Added `reportlab>=4.4,<5` to the canonical runtime because the evidence subsystem's implemented PDF
  export path imports it. `uv.lock` now resolves 95 packages.

## Current next phase

Phase 07/08: exercise cross-domain vertical journeys through the integrated services, run scientific
oracles and failure injection, then consolidate obsolete placeholder package paths only when their
replacement is covered by tests.

## Phase 07/08 — cross-domain and repository-wide validation

- Shared integration tests now cover UI, analysis and AI domain routing through the same command bus.
  The focused integration suite currently has **6 passing tests**.
- AI cross-domain coverage verifies restricted-project remote egress is denied, local retrieval ingest
  requires approval, a durable agent plan executes a local evidence query, and all operations appear in
  the shared audit store.
- Full merged repository collection was repaired with pytest importlib mode because isolated workers had
  duplicate test basenames. The resulting integrated run completed **647 tests passed, 3 warnings** on
  Windows CPython 3.12.9. The warnings are two statsmodels seasonal-start warnings and the intentional
  duplicate-ZIP fixture warning.
- Strict first-party mypy passes **151 source files**. Missing-type exceptions are restricted to named
  third-party scientific/document libraries without complete `py.typed`/stub coverage.
- Repository-wide Ruff passes after integration/release tooling changes.
- The locally observed desktop startup test passes with the integrated V2 window and no provider keys.

## Phase 09/10/11 — metrics, screenshots and release engineering

- Added an AST/tokenize source counter. Current observed report:
  - AI: 6,163 substantive lines
  - analysis: 11,579
  - app: 407
  - core: 366
  - evidence: 16,536
  - UI: 12,610
  - package root: 3
  - **total: 47,664 substantive first-party Python SLOC across 151 files**
- Counter scope excludes tests, fixtures, generated/vendor files, blanks, comment-only lines and
  module/class/function docstrings. `cloc` and `tokei` were not installed locally, so no second counter
  result is claimed.
- Canonical `ruff format .` was applied after merge integration because the repository lint task requires
  format conformance. The full test suite is rerun after this formatting-only normalization before commit.
- Added reproducible integrated screenshot capture from a deterministic synthetic project. Six current
  screenshots cover Dashboard, Statistics and Review in light/dark themes. Native Windows recapture was
  required because Qt offscreen mode exposed no system font families and rendered tofu glyphs. The final
  checked-in screenshots were visually inspected and are readable. SHA-256 metadata is in
  `assets/screenshots/manifest.json`.
- Added PyInstaller portable-build definitions for Windows/Linux/macOS and a three-OS GitHub Actions
  build matrix. Only the Windows build is locally observed in this session.
- Windows portable build completed successfully and produced
  `dist/ResearchWeave-windows-x86_64.zip` (not tracked) with SHA-256
  `F264A3F89D6C5F613FC6272A2FD0C25899108EBF08A7222C1454E85B8BE1FFEC` after the
  cryptography security upgrade. Final observed ZIP size: 170,145,206 bytes.
- The packaged executable remained alive for four seconds in an offscreen smoke process and was then
  terminated by the harness. A separate clean-extraction smoke test passed both `portable_startup` and
  `user_data_retention`: deleting the extracted portable package did not delete a simulated user-profile
  sentinel.
- Generated reproducible release evidence:
  - `docs/verification/SBOM.cdx.json` — CycloneDX environment SBOM.
  - `docs/verification/DEPENDENCY_LICENSES.json` — machine-readable pip-licenses inventory.
  - `docs/verification/SECRETS_SCAN.json` — detect-secrets scan output. Reported candidates are hashes,
    cache tags and synthetic/test credential fixtures; no private research dataset path was found in the
    tracked-file audit. A release reviewer should continue treating any new secret finding as blocking.
- An initial connected `pip-audit --local` found seven advisories in `cryptography 47.0.0`. The runtime
  constraint was upgraded to `cryptography>=50,<51`, `uv.lock` resolved 50.0.2, focused crypto/archive
  tests passed **19/19**, and a repeat `pip-audit --local` reported **no known vulnerabilities**. The
  Windows portable package was rebuilt and re-smoke-tested after this upgrade.
- `detect-secrets` candidates in tracked files were manually reviewed. They are deterministic hashes,
  safe-character alphabets, deliberately fake/redaction-test credentials, and synthetic recovery
  passphrases. Review details are recorded in `docs/verification/SECRETS_REVIEW.md`.

## Phase 12 — public docs and support truthfulness

- Replaced bootstrap README claims with observed V2 behavior, actual screenshots, architecture, first-run
  commands, Windows packaging evidence, source metrics, privacy/security evidence and explicit blockers.
- Added `docs/INTEGRATIONS.md`, `docs/INSTALL.md`, `CITATION.cff`, expanded changelog and dependency-license
  documentation. README local-link validation currently passes with **6 local image references**.
- Advanced AI backend operations are verified through the common bus, but the desktop Provider/Agent
  screens do not yet surface the entire AI facade. Remote sync also requires an injected live transport.
  These remain product-completeness gaps and are documented as limited/experimental rather than complete.

## Current release blockers

1. Linux and macOS portable-build workflows are defined but not observed on their native runners in this
   local Windows session.
2. Advanced AI facade operations are not all wired to end-user desktop controls.
3. The original repository checkout still contains untracked `prompts/`; Gate C forbids stashing,
   cleaning, deleting or overwriting that material, so fast-forward promotion to original `main` is
   blocked until the user-owned working tree is clean without data loss.

## Current next phase

Run the final full suite/static/release checks after the documentation and packaging changes, save compact
INT-073/074/075/077 traces, commit the validated release-engineering slice, then perform the final Gate A/B/C
audit without pushing or deleting original/worker data.
