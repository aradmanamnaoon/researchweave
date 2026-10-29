# ResearchWeave UX transformation — self-contained continuation

**Date:** 29 October 2026. **Status:** feature worktree under verification; not a verified product release.

## Exact checkout and authorization

- User's repository: `D:\coding\codex\researchweave`, remote `https://github.com/aradmanamnaoon/researchweave.git`.
- Isolated working tree: `D:\coding\codex\researchweave\target\ux-transformation-20261029`, branch `ux/researchweave-20261029`; initial HEAD `976656d9ea5ce753f9b170383bf5cb65eb9f263d`. **Initial HEAD does not identify the modified candidate.** Obtain the latest commit with `git rev-parse HEAD` after commit.
- Original working checkout had unrelated work and must remain untouched. No force push, reset, clean, or destructive history rewrite. A historical Python recovery tag and fixture material are preserved.
- The user explicitly authorized normal edits, tests, commits, push, new version tag and GitHub Release **only if all final cross-platform native installation, functional, accessibility and exact-SHA acceptance gates are verified**. No unverified release should be published. Latest preexisting public release is Rust `v0.2.0`.
- **All real native GUI tests must be invisible to the user's visible Windows desktop**, using private WSL2/Xvfb/VM or hosted native runners. Never operate the visible desktop.

## Source work currently present

- Rust/Slint remains the authoritative application: 9 Rust workspace crates, Slint UI, 40 destinations under six activities.
- `crates/researchweave-project/src/quick_notes.rs`: additive project-scoped SQLite quick notes, revision history, title/labels, pin/archive/trash/restore/search, CAS conflict protection, durable one-row draft staging, recovery, cached `DraftSession`; existing research notebook remains separate.
- `main.slint`: substantial notes layout, compact/list view, expanded editor, simplified navigation, larger manuscript writing canvas, focus/writing-tools switch, word/character count, optional contextual AI side panel, contextual-sidebar auto-hide while AI is open, real read-only verified data grid and clearer statistics labels. **This is plain Slint text editing; it does not meet Word's rich-document feature set.**
- `crates/researchweave-ai/src/contextual.rs`: pure preview builder for 8 research contexts, selected project/object text bounded and treated as untrusted; no invisible egress, no invented citation IDs, offline/remote provider denial, no document overwrite. Desktop has explicit preview and local-only inference attempt; no end-to-end local model result has been verified.
- `crates/researchweave-desktop/src/main.rs`: Rust event handlers for quick notes, contextual AI, manuscript metrics, read-only dataset page state from immutable `dataset.inspect` results; Windows `windows_subsystem = windows` declaration to suppress unwanted console.
- `crates/researchweave-analysis/src/lib.rs`: invalid dataset page offsets now return a domain error instead of panicking.
- Existing manuscript autosave remains bounded by a **256 KiB encoded draft**. Synthetic 1/5/15/30/50-page journal fixtures measure data integrity; `docs/ux/LONG_FORM_EDITOR.md` documents actual limits.
- Safe source cleanup: `.gitignore` and `README.md` updated; only obsolete Python-era script `scripts/rust_rewrite/capture_python_capabilities.py` removed. Keep Python-based Rust installer helpers, test fixtures and recovery evidence: Rust packaging depends on them.
- 100 distinct project-authored UX skills under `docs/ux/skills/<slug>/SKILL.md` and installed under `/skills/researchweave`; `docs/ux/100_SKILLS_APPLICATION_MATRIX.md` records source probes, **not 100 real usability acceptances**.

## Actually observed native GUI acceptance

- Real private Ubuntu Xvfb/Openbox application run: `scripts/ux/isolated-xvfb-gui-smoke.sh`. Creates a synthetic managed project, enters and saves a real note; verifies SQLite title/body/labels/revision/history, pin/archive/unarchive/trash/restore, navigation, AI preview with missing local provider, after screenshots. Test data resides only in temporary private directories.
- `scripts/ux/isolated-xvfb-manuscript-15-pages.sh`: pastes **42,870 Unicode code points** / **50,370 UTF-8 bytes**, labeled as 15 synthetic pages, through real Slint GUI; checks on-disk recovery journal, closes/relaunches app, opens the same project, copies the **actual reopened editor** via clipboard and asserts exact text equality. Three screenshot artifacts under `docs/ux/screenshots/long-form-xvfb/`. This is neither genuine pagination nor proof of Word-class formatting.
- `scripts/ux/isolated-xvfb-dataset-grid.sh`: runs real native synthetic import/analysis harness to create a known 3-row immutable revision, opens project via GUI, navigates to Data View, enters exact ID/revision, clicks Inspect, asserts AT-SPI read-only table and verified row status 1–3 of 3 and then verifies saved project through native smoke. `docs/ux/screenshots/data-view-xvfb/01-real-verified-dataset-grid.png` records the actual populated table.
- `scripts/ux/isolated-xvfb-full-route-audit.sh`: an earlier source snapshot opened **40/40** registered routes through the real GUI and checked their AT-SPI work area names; saved **46 screenshots** (40 destinations plus keyboard/resize), with unique hashes. Evidence stored in private WSL `/home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2/`. **Rerun after final source freeze; this earlier SHA does not cover subsequent UI changes.**
- Historical Windows debug `--smoke-project` completed with exit code 0 and `SMOKE_OK` through redirected stdout. This validates the debug native Rust command path, **not** Windows Explorer/start-menu invisible console or installed GUI acceptance.
- Android/iOS and other unsupported platforms were not promised. **Windows installed GUI native and macOS ARM/Intel target acceptance are still missing for this UX candidate.**

## Repeatable local checks

Run in the isolated worktree. Set `CARGO_INCREMENTAL=0` on Windows: the D: build-cache drive previously filled; removing *only* disposable `target/debug/incremental` recovered about 11 GiB without removing source or project data.

```powershell
$env:CARGO_INCREMENTAL = '0'
$env:CARGO_TARGET_DIR = 'D:\coding\codex\researchweave\target'
cargo fmt --all -- --check
cargo clippy --workspace --locked --all-targets --all-features -- -D warnings
cargo test --workspace --locked --all-features
py -3 scripts/verify_readme.py
git diff --check
```

Build/recheck the actual Ubuntu desktop in WSL2:

```bash
cd /mnt/d/coding/codex/researchweave/target/ux-transformation-20261029
CARGO_TARGET_DIR=/home/saba/researchweave-linux/target CARGO_INCREMENTAL=0 cargo build --locked --release -p researchweave-desktop
bash scripts/ux/isolated-xvfb-gui-smoke.sh /home/saba/researchweave-linux/target/release/researchweave-desktop docs/ux/screenshots/after-xvfb modern
bash scripts/ux/isolated-xvfb-manuscript-15-pages.sh /home/saba/researchweave-linux/target/release/researchweave-desktop docs/ux/screenshots/long-form-xvfb
bash scripts/ux/isolated-xvfb-dataset-grid.sh /home/saba/researchweave-linux/target/release/researchweave-desktop docs/ux/screenshots/data-view-xvfb .
```

When ready to freeze source, rerun full-route audit with a **new** output directory outside the worktree; its script refuses overwriting existing evidence. Record `git rev-parse HEAD`, `sha256sum` for binary and `main.slint` and `main.rs`, exact CI run links, artifacts, and target OS test receipts. The native candidate is version `0.2.0` in Cargo until a **verified next semantic release** is coordinated; do not point the README to invented next-version asset links.

## Important unsatisfied user acceptance gates

1. The registered routes **3 Search, 6 Reader, 8 Evidence, 25 Privacy, 26 Integrations, 27 Exports, 33 Tutorials, 34 Guidance, 35 Shortcuts and 38 About** remain explicit placeholders. Route reachability is not workflow completion.
2. Word-class rich text (structured document model, headings/bold/italic/underline/lists/tables/links/real page layout, selection-grounded edits, robust IME/focus at scale) is **not complete**. A 15-synthetic-page plain-text round trip passed, which is narrower evidence.
3. The full dedicated conversational AI experience, grounded per-object selection context, remote provider privacy consent, streamed AI responses and live local provider result acceptance have not been demonstrated. Existing optional AI preview is user-controlled and local-only.
4. End-to-end qualitative/review, source reader/evidence/search, all 30 active workflows and entire keyboard/AT/screen-reader UI behavior need comprehensive task-level GUI verification. Skills source probes are not equivalent to GUI UX tests.
5. Current source still needs a **fresh exact-source** full Windows native UIA/installed package check, macOS arm64/x86_64 native hosted checks, Linux .deb/AppImage installation, repo-wide CI, security/PE console gate, and SHA256 asset verification from an immutable release commit.
6. No new release has been created. If any critical gate stays blocked, preserve the tested UX branch/PR and log its precise blocker; never make an unverified tag/release.

## Preferred next execution

1. Finish final Slint visual/accessible sizing issues exposed by real screenshots; validate notes/AI/Data View and 15-page manuscript on fresh native binary.
2. Run full Rust tests, Clippy, README/asset links, and deterministic 100-skill source probes against exact candidate.
3. Safely commit and push the feature branch; open a reviewable PR and collect hosted quality/native candidate run results. A feature PR is **not** a release.
4. Implement remaining functionality in focused vertical slices and rerun its native GUI and data-compatibility checks.
5. After all user acceptance criteria and target OS CI/installed packages pass against final merged SHA: version/tag, build Windows/macOS x64/arm64/Linux packages, verify SHA256SUMS and published download links. Until then, report the release as **blocked**.
