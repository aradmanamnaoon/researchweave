# ResearchWeave: isolated native GUI and Rust QA, 2026-10-31

## Source and scope

- Starting repository source: locally recorded `origin/main` `976656d`, public Rust v0.2.0 lineage.
- Mission implementation: isolated `mission/prime-20261031` branch, source commits `e404a0d`, `47341f2` and `d469fe5`. The screenshot suite applies to source-built debug binaries corresponding to these changes, **not** a new distributable installer.
- Source files affected: `crates/researchweave-desktop/ui/main.slint`, `src/main.rs`, `src/display_contrast.rs`, with design records `docs/design/RESEARCHWEAVE_DESIGN_SYSTEM.md` and `docs/design/PALETTE_SELECTION_2026-10-31.md`.
- Original dirty `D:\coding\codex\researchweave` root and its data remained untouched; tests used a separate clean worktree and disposable local project data.

## Windows native Rust verification

`CARGO_TARGET_DIR=%LOCALAPPDATA%\Temp\researchweave-mission-20261031-target` on drive C, `CARGO_INCREMENTAL=0`, `CARGO_BUILD_JOBS=3`:

| Command | Observed |
| --- | --- |
| `cargo fmt --all -- --check` | PASS |
| `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings` | PASS |
| Earlier base: `cargo test --workspace --locked --all-features` | PASS, **172 unit tests**, 0 failures, doc tests 0 |
| Updated desktop: `cargo clippy -p researchweave-desktop --locked --all-targets --all-features -- -D warnings` | PASS |
| Updated desktop: `cargo test -p researchweave-desktop --locked --all-features --quiet` | PASS, **38 desktop tests**, 0 failures |
| Latest full mission source: `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings`; `cargo test --workspace --locked --all-features --quiet` | PASS, **173 workspace unit tests**, 0 failures |

The 173 unit tests include scientific golden fixture tests, numerical and data import rules, project migration, local encrypted backup, AI approval boundaries, notebook/manuscript autosave, export, and tamper checks. A green library test does **not** certify the UI workflow, which is separately exercised below.

## Isolated Linux GUI interaction

The exact modified source was mirrored into `/home/saba/researchweave-mission-20261031` in Ubuntu under WSL2. A Linux native desktop binary was built with `cargo build --locked --offline -p researchweave-desktop`, using the pre-existing isolated `/home/saba/researchweave-linux/target` cache.

**Latest verified Linux debug binary SHA-256:**

`9ab4a4c0220851083a3915638796a67fd32fa6ea51241c090f5ee18b25ff627f`

The final test used `dbus-run-session` + Xvfb (1440×1000 virtual display), a synthetic private HOME, isolated `RESEARCHWEAVE_HOST_DATA_DIR`, AT-SPI semantic actions and `xdotool` keyboard input **inside Xvfb only**. The active Windows desktop was not driven. The reproducible harness is `scripts/qa/mission-xvfb-ui-smoke.sh` and `scripts/qa/mission-atspi-navigation.py`.

**Observed latest run:** `docs/qa/mission-xvfb-20261031-r19/atspi-navigation.txt`; `binary.sha256` records this exact source-built binary. Assertions:

1. App appeared in native AT-SPI tree with 55 named accessibility nodes on Welcome.
2. `Create default project` activated; project dashboard and revision context appeared (65 named nodes).
3. Navigated through Synthesize to Notebook; entered synthetic text directly into the real editor, then read **the exact text back** using the AT-SPI Text interface. This corrected an earlier false-positive test that had focused the editor without actually inserting text.
4. Notebook and manuscript synthetic text was actually entered via Xvfb keyboard, independently read back, and both reported successful project autosave after the debounce period. `Load notebook history` was actionable.
5. A controlled synthetic CSV with `score=[1,2,3]` was previewed and imported as an immutable dataset. The actual dataset ID and 64-character revision were automatically propagated into **Variables** and **Statistics**. Native descriptives displayed mean 2.0000, median 2.0000, SD 1.0000 and n=3 with revision provenance. Verified raw JSON disclosure opened and closed on user action.
6. Creating project B after data analysis cleared the former project's import file path, dataset ID/revision, statistical results, notebook and manuscript drafts; an explicit GUI assertion failed against the prior implementation with stale statistical JSON. The source fix resets project-scoped result state and invalidates staged pending previews on project switch.
7. A separate import preview staged in project A was **rejected** after switching to project B (`STALE_IMPORT_PREVIEW_REJECTED_AFTER_PROJECT_SWITCH`); the destination project had no newly imported dataset. This specifically tested the preview/approval invalidation path.
8. **Reopened project A** using its real managed project path and verified the originally autosaved note and manuscript content was restored exactly. The restart-while-unsaved/corruption scenario remains a separate future recovery gate.
9. In an 850×600 Xvfb window, Notebook Preview/Record/History/Export actions were all visible, and Manuscript Preview/Record/Inspect buttons remained accessible above the reading canvas.
10. The native GUI remained alive after interaction; the final harness exited 0 with `NOTES_AND_MANUSCRIPT_REOPEN_PERSISTENCE_OK`, `PROJECT_RESULT_ISOLATION_OK`, `AT_SPI_NAVIGATION_PROBE_OK` and `ISOLATED_XVFB_TEST_DONE`.

**Screenshots, visually inspected:** `docs/qa/mission-xvfb-20261031-r19/` contains `welcome.png`, `project-created.png`, `notebook.png`, `notebook-narrow.png`, `manuscript.png`, `manuscript-narrow.png`, `data-after-import.png`, `statistics-result.png`, `statistics-technical-details.png`, `data-after-project-switch.png`, `reopened-project-writing.png`; it also contains AT-SPI node listings, complete synthetic interaction trace and binary digest.

## Limitations and outstanding gates

- No verified Windows isolated native GUI session was completed for this new source SHA. Earlier Windows GUI work is historical and is insufficient for new mission claims.
- No macOS arm64/x64 native build, test, signing or notarization was completed for this new source SHA. No updated Windows installer, Linux DEB or AppImage was packaged from it.
- No native PDF reader → Notebook return workflow with an actual PDF, full missing-data cleaning/transformation, AI provider approval journey, document recovery after **process restart or corruption**, or reference export GUI journey was run in this mission. Data import and basic descriptives **were tested** with an independent 3-row synthetic fixture; this is not the full statistics matrix.
- Notebook remains a project-wide text surface, without independently verified Google Keep-like note cards, pin/archive/tag/search; manuscript remains an editable text section with DOCX/PDF export backend, **not** a page-based rich-text Word equivalent.
- Visuals were inspected at 1280×800 and 850×600 under Xvfb; light/dark/high contrast, 200% text scale, NVDA/VoiceOver and actual user usability trials still need new evidence. AT-SPI's editable text setter reported `NotImplementedError`; the test used isolated keyboard input and successful text readback. **Observed accessibility defect:** after staging another import, the otherwise visible/enabled Home project's Start Center button was present in AT-SPI but `doAction(0)` returned false. A private-Xvfb pointer click at its semantic button bounds succeeded. This discrepancy requires remediation before full assistive-technology acceptance.
- Four attempted delegated CoS worker chats failed initialization. No worker implementation or skill usage is credited.
- The prior public v0.2.0 five-platform GitHub Release remains the latest verified public package set. This incremental branch is **not release ready** until remaining product and platform gates pass.
