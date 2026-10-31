# ResearchWeave recovery audit — 2026-10-31

The **original** `D:\coding\codex\researchweave` checkout is on `main` at `c84cdf1`, 74 commits behind the locally recorded `origin/main` `976656d`, with **271 Git-visible changed files** (11 modified tracked and 260 untracked). The untracked Rust workspace is meaningful unfinished development work and was not deleted, checked out, reset, staged or reformatted.

## Verified recovery

The folder `D:\coding\codex\researchweave-recovery\researchweave-working-20261031T1043` contains `git-visible-working-tree.zip` (271 entries), `manifest.json` (path, size and SHA-256 per file), `git-status.txt`, `git-log.txt` and `all-refs.bundle` (`git bundle verify` PASS; 76 refs and complete history). The existing `archive/python-final-c84cdf1` tag is present. Git-ignored application data and compilation artifacts remain in place but were not included in the targeted ZIP.

## State reconciliation

The newer `origin/main` is the published **local-only Rust v0.2.0** product, with nine workspace crates. The old root has eleven crates, including obsolete cloud/sync work. Commit `bf9baf7` and the current `AGENTS.md` explicitly record that remote project sync was removed at the user's request. Old untracked cloud code must never be mechanically copied into the current product.

`gh release view v0.2.0` confirmed that a public release exists with Windows installer, macOS arm64/x64 DMGs, Linux x86_64 AppImage/amd64 DEB and `SHA256SUMS.txt`. These prove the *existing* v0.2.0 asset listing, not any new changes in this mission.

New independent, clean worktrees were created from `976656d`: `target/mission-prime-20261031`, `target/mission-notes-20261031`, `target/mission-writing-20261031`. The original dirty working tree remains untouched. Two remote worker chats were attempted but failed during initialization; worker code changes must not be assumed.

## Initial defects and risk

- **PARTIAL:** Notebook screen exists without verified Google Keep style capture, cards, pin/archive/search and restart UX.
- **PARTIAL:** Manuscript supports structured text and persisted exports, but lacks a verified paginated Word-like rich document model.
- **PARTIAL:** Data and statistics have independently tested computations but advanced UI guidance, interactive tables, assumption help and screen-reader results need more work.
- **PARTIAL:** Existing semantic palette and icons are established, yet native control accent consistency and all-screen theme parity remain open.
- **PARTIAL:** Contextual opt-in AI, interrupted save recovery, UI focus/IME and cross-platform GUI evidence still require fresh acceptance.
- **WORKING (historical only):** project create/open, scientific revision history, encrypted local archive, published v0.2.0 release; must rerun after new changes.
- **RETIRED:** remote cloud project synchronization, consistent with the later v0.2.0 local-only decision.

Release work must be built/tested from an exact new source revision, including native OS GUI, signed-status honesty, versioned import/export, hashes and public links. The older release remains available and should not be replaced by an unverified candidate.
