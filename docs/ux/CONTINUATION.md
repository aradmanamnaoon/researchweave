# ResearchWeave UX transformation — self-contained continuation

**Date:** 29 October 2026. **Status:** WIP commit preserved and pushed, further work ongoing; final UX acceptance and next product release remain blocked.

**Latest verified working-candidate checkpoint:** On executable SHA-256 `77295db0109768f108495a31d932238431aeb0a86988325a63dd4258318023c7`, a newer private Linux/Xvfb audit passed **40/40 native routes** with `source_changed_during_audit=false` and **eight remaining placeholders** (8, 25, 26, 27, 33, 34, 35, 38). Search (3) and Reader (6) are now real Rust-backed project-local text workflows. A **separate synthetic Linux Xvfb Search → Reader functional run PASS** tested actual two-source project creation, empty/no-match query feedback, Unicode result click, exact 207-character Reader text, invalid/empty IDs, source-list reopen and return navigation. The [tracked evidence receipt](screenshots/search-reader-xvfb/results.json) lists six captured screenshot hashes; original private run path `/home/saba/researchweave-gui-audits/search-reader-worker1-r4/`. This proves a short synthetic Linux task, **not** long 8,000-character pagination, a screen-reader pass, other operating systems or installed-package acceptance. The receipt notes that independent binary-to-source build provenance remains necessary. Published `v0.2.0` is unchanged.

## Exact checkout and authorization

- User's repository: `D:\coding\codex\researchweave`, remote `https://github.com/aradmanamnaoon/researchweave.git`.
- Isolated working tree: `D:\coding\codex\researchweave\target\ux-transformation-20261029`, branch `ux/researchweave-20261029`; initial baseline `976656d9ea5ce753f9b170383bf5cb65eb9f263d`. **Saved/pushed WIP recovery commit: `82e4dee33b676cd42c47330ff46b645f2eac008f`**, observed equal to `origin/ux/researchweave-20261029`. **New uncommitted edits after WIP** were observed in `crates/researchweave-desktop/src/document_navigation.rs`, `src/main.rs` and `ui/main.slint`. Recheck HEAD, dirty files, origin and final binary/source hashes after every new commit; WIP is a checkpoint, not the final candidate.
- Original working checkout had unrelated work and must remain untouched. No force push, reset, clean, or destructive history rewrite. A historical Python recovery tag and fixture material are preserved.
- The user explicitly authorized normal edits, tests, commits, push, new version tag and GitHub Release **only if all final cross-platform native installation, functional, accessibility and exact-SHA acceptance gates are verified**. No unverified release should be published. Latest preexisting public release is Rust `v0.2.0`.
- **All real native GUI tests must be invisible to the user's visible Windows desktop**, using private WSL2/Xvfb/VM or hosted native runners. Never operate the visible desktop.

## Source work currently present

- Rust/Slint remains the authoritative application: 9 Rust workspace crates, Slint UI, 40 destinations under six activities.
- `crates/researchweave-project/src/quick_notes.rs`: additive project-scoped SQLite quick notes, revision history, title/labels, pin/archive/trash/restore/search, CAS conflict protection, durable one-row draft staging, recovery, cached `DraftSession`; existing research notebook remains separate.
- `main.slint`: substantial notes layout, compact/list view, expanded editor, simplified navigation, larger manuscript writing canvas, focus/writing-tools switch, word/character count, optional contextual AI side panel, contextual-sidebar auto-hide while AI is open, real read-only verified data grid and clearer statistics labels. **This is plain Slint text editing; it does not meet Word's rich-document feature set.**
- `crates/researchweave-ai/src/contextual.rs`: pure preview builder for 8 research contexts, selected project/object text bounded and treated as untrusted; no invisible egress, no invented citation IDs, offline/remote provider denial, no document overwrite. Desktop has explicit preview and local-only inference attempt; no end-to-end local model result has been verified.
- `crates/researchweave-desktop/src/main.rs`: Rust event handlers for quick notes, contextual AI, manuscript metrics, read-only dataset page state from immutable `dataset.inspect` results; Windows `windows_subsystem = windows` declaration to suppress unwanted console.
- **New source Search/Reader:** `main.slint` routes **3 Search** and **6 Reader** now expose a real project-local query, source result cards, 50-item indexed source-list pages, and read-only 8,000-Unicode-character text paging with Previous/Next. Rust `main.rs` callbacks use the bound `researchweave-library` operations `search.query`, `library.list`, `library.source_get`, `source.full_text` with background execution, schema validation, project/request freshness guards and reset on project changes. Literal search scans at most 10,000 local sources and returns at most 100; result snippets start at the beginning of source bodies. `cargo check --locked -p researchweave-desktop`, format check, and targeted source round-trip library/desktop Rust tests passed during implementation.
- `crates/researchweave-analysis/src/lib.rs`: invalid dataset page offsets now return a domain error instead of panicking.
- Existing manuscript autosave remains bounded by a **256 KiB encoded draft**. Synthetic 1/5/15/30/50-page journal fixtures measure data integrity; `docs/ux/LONG_FORM_EDITOR.md` documents actual limits.
- Safe source cleanup: `.gitignore` and `README.md` updated; only obsolete Python-era script `scripts/rust_rewrite/capture_python_capabilities.py` removed. Keep Python-based Rust installer helpers, test fixtures and recovery evidence: Rust packaging depends on them.
- 100 distinct project-authored UX skills under `docs/ux/skills/<slug>/SKILL.md`, recorded installed under `/skills/researchweave`. The matrix was **regenerated against post-`82e4dee` working files** and reports **97 literal source witnesses and 3 missing-marker probes**, with **zero skill-specific GUI acceptances proven**. Probe #064 still demands a `ListView` marker despite a real `StandardTableView`; fix that probe, rerun on frozen final source and validate runtime behavior independently.

## Actually observed native GUI acceptance

- Real private Ubuntu Xvfb/Openbox application run: `scripts/ux/isolated-xvfb-gui-smoke.sh`. Creates a synthetic managed project, enters and saves a real note; verifies SQLite title/body/labels/revision/history, pin/archive/unarchive/trash/restore, navigation, AI preview with missing local provider, after screenshots. Test data resides only in temporary private directories.
- `scripts/ux/isolated-xvfb-manuscript-15-pages.sh`: pastes **42,870 Unicode code points** / **50,370 UTF-8 bytes**, labeled as 15 synthetic pages, through real Slint GUI; checks on-disk recovery journal, closes/relaunches app, opens the same project, copies the **actual reopened editor** via clipboard and asserts exact text equality. Three screenshot artifacts under `docs/ux/screenshots/long-form-xvfb/`. This is neither genuine pagination nor proof of Word-class formatting.
- `scripts/ux/isolated-xvfb-dataset-grid.sh`: sets up a synthetic 3-row immutable revision, opens project via native GUI, reaches Data View and inspects ID/revision. The **tracked screenshot** `docs/ux/screenshots/data-view-xvfb/01-real-verified-dataset-grid.png` visibly shows the actual two-column, three-row `StandardTableView` and verified revision. `fixture.stdout.log` and `reopen-verify.log` contain matching native project/export hashes. **This is a limited earlier Linux fixture**; no attributable final-source binary fingerprint, multi-page paging, large-dataset or cross-OS installed GUI acceptance was established by this document review.
- `scripts/ux/isolated-xvfb-full-route-audit.sh`: an earlier source snapshot opened **40/40** registered routes through the real GUI and checked their AT-SPI work area names; saved **46 screenshots** (40 destinations plus keyboard/resize), with unique hashes. Evidence stored in private WSL `/home/saba/researchweave-gui-audits/full-route-20261029-exact-source-worker2/`. **Rerun after final source freeze; this earlier SHA does not cover subsequent UI changes.**
- **Later current-source native route audit:** **40/40 PASS**, binary `77295db0109768f108495a31d932238431aeb0a86988325a63dd4258318023c7`, `source_changed_during_audit=false`, exactly **eight placeholders** (8, 25, 26, 27, 33, 34, 35, 38). The prior ten-placeholder `c0cd1e8...` screenshots remain historical; no screenshots or source hashes are interchanged between candidates.
- **New Search → Reader GUI acceptance:** private Linux Xvfb `search-reader-worker1-r4` **PASS** with exact 207-Unicode-character source text, empty/missing-ID and zero-match validation, source-list reopening and return navigation. Three actual captures and the scoped [manifest](screenshots/search-reader-xvfb/results.json) are tracked under `docs/ux/screenshots/search-reader-xvfb/`; six full capture hashes are in the private run receipt. Long text pagination, performance and other OSes were **not** exercised.
- **Other fresh private Linux GUI cases:** synthetic **15-page Unicode manuscript clipboard/reopen equality PASS**, populated **Data View grid PASS**, and **exact found-text contextual AI preview PASS**. These are independent flows; found-text preview is constrained to the actual manuscript text selection/query path and does **not** verify citation-backed model output or unrelated objects. **Windows workspace tests 188 PASS, formatting and strict Clippy PASS** reported for the working source. This is not release-package/CI acceptance.
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

1. The registered routes **8 Evidence, 25 Privacy, 26 Integrations, 27 Exports, 33 Tutorials, 34 Guidance, 35 Shortcuts and 38 About** remain the **eight** explicit placeholders. Search (3) and Reader (6) are now live stored-text workflows with a successful **short synthetic Linux GUI** exercise; longer pagination and cross-platform functionality remain untested.
2. Word-class rich text (structured document model, headings/bold/italic/underline/lists/tables/links/real page layout, selection-grounded edits, robust IME/focus at scale) is **not complete**. A 15-synthetic-page plain-text round trip passed, which is narrower evidence.
3. The full dedicated conversational AI experience, grounded per-object selection context, remote provider privacy consent, streamed AI responses and live local provider result acceptance have not been demonstrated. Existing optional AI preview is user-controlled and local-only.
4. End-to-end qualitative/review, source-to-evidence/claim, long Reader paging, all **32 concrete routes** and entire keyboard/AT/screen-reader UI behavior need broader task-level GUI verification. The **short synthetic source Search → Reader Linux flow passed**, but 40/40 route navigation and skills source probes alone are not comprehensive GUI UX tests.
5. Source edits made **after WIP `82e4dee`** still need a fresh immutable final commit, exact-source whole-workspace Rust tests and security checks, Windows native UIA/installed package test, macOS arm64/x86_64 native hosted checks, Linux .deb/AppImage installation, PE console gate, accessibility/IME checks, and package SHA256 verification.
6. **The existing Rust `v0.2.0` public release is historical**, and its five native assets plus `SHA256SUMS.txt` were independently listed with `gh release view`. **No new UX release has been created.** Preserve the pushed UX recovery branch, open/review a PR if appropriate, and report blocked gates before any later release.

## Preferred next execution

1. Review the new passing short Search/Reader and fresh manuscript/grid/found-text AI GUI receipts, then extend long Reader pagination, error handling, accessibility and source→Evidence; finish visual/accessible sizing issues on final native source.
2. Run full Rust tests, Clippy, README/asset links, and deterministic 100-skill source probes against exact candidate.
3. Preserve the already pushed `82e4dee` WIP backup, then safely commit and push the **subsequent** source changes after review; open a reviewable PR and collect hosted quality/native candidate runs for the same immutable final commit. A feature PR is **not** a release.
4. Implement remaining functionality in focused vertical slices and rerun its native GUI and data-compatibility checks.
5. After all user acceptance criteria and target OS CI/installed packages pass against final merged SHA: version/tag, build Windows/macOS x64/arm64/Linux packages, verify SHA256SUMS and published download links. Until then, report the release as **blocked**.
