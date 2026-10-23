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
