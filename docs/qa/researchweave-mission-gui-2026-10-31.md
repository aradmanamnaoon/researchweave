# ResearchWeave: isolated native GUI and Rust QA, 2026-10-31

## Source and scope

- Starting repository source: locally recorded `origin/main` `976656d`, public Rust v0.2.0 lineage.
- Mission implementation: local `mission/prime-20261031` branch, initial UI commit `e404a0d` plus the later responsive layout adjustment. The final integrated commit identifier belongs in the Git log after this evidence is committed. This QA is specific to these UI source bytes; it is **not** evidence of a new distributable installer.
- Main source files affected: `crates/researchweave-desktop/ui/main.slint`, `crates/researchweave-desktop/src/display_contrast.rs`; design records `docs/design/RESEARCHWEAVE_DESIGN_SYSTEM.md` and `docs/design/PALETTE_SELECTION_2026-10-31.md`.
- Original dirty `D:\coding\codex\researchweave` root and its data remained untouched; tests used a separate clean worktree and disposable local project data.

## Windows native Rust verification

`CARGO_TARGET_DIR=%LOCALAPPDATA%\Temp\researchweave-mission-20261031-target` on drive C, `CARGO_INCREMENTAL=0`, `CARGO_BUILD_JOBS=3`:

| Command | Observed |
| --- | --- |
| `cargo fmt --all -- --check` | PASS |
| `cargo clippy --workspace --locked --all-targets --all-features -- -D warnings` | PASS |
| `cargo test --workspace --locked --all-features` | PASS, **172 unit tests**, 0 failures, doc tests 0 |
| Last responsive/UI change: `cargo clippy -p researchweave-desktop --locked --all-targets --all-features -- -D warnings` | PASS |
| Last responsive/UI change: `cargo test -p researchweave-desktop --locked --all-features --quiet` | PASS, **37 desktop tests**, 0 failures |

The 172 unit tests include scientific golden fixture tests, numerical and data import rules, project migration, local encrypted backup, AI approval boundaries, notebook/manuscript autosave, export, and tamper checks. A green library test does **not** certify the UI workflow, which is separately exercised below.

## Isolated Linux GUI interaction

The exact modified source was mirrored into `/home/saba/researchweave-mission-20261031` in Ubuntu under WSL2. A Linux native desktop binary was built with `cargo build --locked --offline -p researchweave-desktop`, using the pre-existing isolated `/home/saba/researchweave-linux/target` cache.

**Final Linux debug binary SHA-256:**

`e6a2d0259cdc7cd25a5c32d056412b5aa6ab92d5c31386edfcfa964818c2a736`

The final test used `dbus-run-session` + Xvfb (1440×1000 virtual display), a synthetic private HOME, isolated `RESEARCHWEAVE_HOST_DATA_DIR`, AT-SPI semantic actions and `xdotool` keyboard input **inside Xvfb only**. The active Windows desktop was not driven. The reproducible harness is `scripts/qa/mission-xvfb-ui-smoke.sh` and `scripts/qa/mission-atspi-navigation.py`.

**Observed final run:** `docs/qa/mission-xvfb-20261031-r6/atspi-navigation.txt`; `binary.sha256` records the same native binary hash. Assertions:

1. App appeared in native AT-SPI tree with 55 named accessibility nodes on Welcome.
2. `Create default project` activated; project dashboard and revision context appeared (65 named nodes).
3. Navigated through Synthesize to Notebook; entered synthetic text directly into the real editor, then read **the exact text back** using the AT-SPI Text interface. This corrected an earlier false-positive test that had focused the editor without actually inserting text.
4. Notebook reported `Notebook autosaved to project revisions`; `Load notebook history` was actionable. This is evidence of the on-screen autosave response; independent recovery-after-restart remains to be exercised in a future native GUI acceptance run.
5. In an 850×600 Xvfb window, Notebook Preview/Record/History/Export actions were all visible, and Manuscript Preview/Record/Inspect buttons remained accessible above the reading canvas. Screenshots and semantic node lists were captured at full and narrow layouts.
6. The GUI remained alive after interaction; the harness exited 0 with `AT_SPI_NAVIGATION_PROBE_OK` and `ISOLATED_XVFB_TEST_DONE`.

**Screenshots, visually inspected:** `docs/qa/mission-xvfb-20261031-r6/welcome.png`, `project-created.png`, `notebook.png`, `notebook-narrow.png`, `manuscript.png`, `manuscript-narrow.png`. Files under this final evidence directory include the semantic tree and binary digest.

## Limitations and outstanding gates

- No verified Windows isolated native GUI session was completed for this new source SHA. Earlier Windows GUI work is historical and is insufficient for new mission claims.
- No macOS arm64/x64 native build, test, signing or notarization was completed for this new source SHA. No updated Windows installer, Linux DEB or AppImage was packaged from it.
- No native PDF reader → Notebook return workflow with an actual PDF, complete scientific data import/analysis journey, AI provider approval journey, document save/restore after a process restart, or reference export GUI journey was run in this mission.
- Notebook remains a project-wide text surface, without independently verified Google Keep-like note cards, pin/archive/tag/search; manuscript remains an editable text section with DOCX/PDF export backend, **not** a page-based rich-text Word equivalent.
- Visuals were inspected at 1280×800 and 850×600 under Xvfb; light/dark/high contrast, 200% text scale, NVDA/VoiceOver and actual user usability trials still need new evidence. AT-SPI's editable text setter reported `NotImplementedError`; the test used isolated keyboard input and successful text readback.
- Two delegated CoS worker chats failed initialization. No worker output is claimed.
- The prior public v0.2.0 five-platform GitHub Release remains the latest verified public package set. This incremental branch is **not release ready** until remaining product and platform gates pass.
