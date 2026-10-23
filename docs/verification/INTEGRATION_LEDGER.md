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

Phase 01: merge the four committed V2 worker branches in evidence, analysis, AI, UI order; inspect
conflicts explicitly; run each domain's focused validation after its merge; then inventory legacy
application paths and integration gaps.
