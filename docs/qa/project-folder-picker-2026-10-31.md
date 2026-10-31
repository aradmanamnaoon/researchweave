# Native project-folder picker: offline verification

Date: 2026-10-31. Branch: `mission/completion-20261031`.

## User behavior and safety

The Start Center now offers **Browse local folders…** next to the editable absolute project path. A native platform folder dialog runs asynchronously, leaving the rest of the application usable. Choosing an existing ResearchWeave directory (containing `data/project.sqlite`) prepares that directory for **Open existing**. Choosing an ordinary parent directory proposes a new, unique `ResearchWeave-<UUID>` child in the text field for **Create at custom path**. The user can review or edit the path before creating anything. The native folder-selection operation only changes the UI path and status. Cancel restores the existing path without touching the project or an in-flight data approval.

The Rust helper refuses relative paths, nonexistent locations, symlink roots and ordinary files. It preserves Unicode paths. Distinguishing existing projects from parent folders matters: `ProjectStore::create` explicitly rejects an existing directory, so treating the dialog's existing directory as a new project root would make the Create button fail.

## Observed offline validation

| Gate | Result |
| --- | --- |
| Windows `cargo fmt --all -- --check`, `git diff --check` | PASS |
| Windows desktop locked unit tests | **59 passed**, 0 failed, including new folder-selection edge cases |
| Windows desktop strict `cargo clippy --offline --locked -p researchweave-desktop --all-targets --all-features -- -D warnings` | PASS |
| Windows PowerShell Windows UIA script parsing | PASS; native-installed folder chooser cancel flow added but not yet run |
| Native Ubuntu/WSL2 locked desktop build | PASS |
| Native Ubuntu/WSL2 `cargo test --offline --locked --workspace --all-features --quiet` | **200 passed**, 0 failed |
| Native Ubuntu/WSL2 `cargo clippy --offline --locked --workspace --all-targets --all-features -- -D warnings` | PASS |
| Real, isolated native Linux Slint UI through Xvfb/AT-SPI (full suite) | PASS: `AT_SPI_NAVIGATION_PROBE_OK` and `ISOLATED_XVFB_TEST_DONE` |
| Native folder picker accessible on first run and 850×600 Start Center | PASS: screenshots and accessibility node captures |
| Existing research flows retested during GUI suite | PASS: quick notes, checklist recovery, manuscript sections, native CSV import and descriptive statistics, project switch isolation, recent project reopening |

Evidence: `docs/qa/mission-xvfb-20261031-folder-picker-r3/` includes `atspi-navigation.txt`, the binary SHA-256, process logs, screenshots and the accessibility tree. Its PDF/data import check verifies a true imported immutable revision and mean = 2 from synthetic data. The Slint AT-SPI provider intermittently reports `NotImplementedError` for readback of an editor after actual keyboard input; the harness now retries a bounded number of times and only allows deferred readback for an import path whose effect is independently verified by the native preview and persisted statistical result. This is a provider limitation, not evidence of successful screen-reader editing.

Remaining gates: an installed Windows setup exercised by UI Automation, actual native folder-dialog selection on Windows/macOS/Linux, release-mode AppImage/DEB smoke, native macOS DMG acceptance, accessibility with NVDA/VoiceOver/Orca, and the complete cross-platform candidate workflow. None of these is inferred from the source-built GUI test.
