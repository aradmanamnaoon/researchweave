# Native desktop display preferences — Windows local verification

Scope: `crates/researchweave-desktop` only. This evidence describes the current Slint shell; it is not a claim of complete Python UI parity.

## Implemented

- The Preferences destination (legacy page 36) now presents accessible buttons for dark theme and high contrast, applying the choice immediately through the Slint `Theme` global.
- Preferences persist in `display-preferences.json` under the operating system application data directory (or `RESEARCHWEAVE_HOST_DATA_DIR`) and are loaded at launch. Invalid saved values produce a status message and keep the defaults.
- Repeated preference saves use a unique temporary file and a rollback backup of the preceding version, supporting Windows where renaming over an existing destination fails.
- The command palette handles Ctrl+K regardless of uppercase K event text.

## Verified and pending

### 2026-10-26 expanded theme and scale audit

- Slint Theme now applies an entire high-contrast palette first, regardless of the dark toggle: black canvas, #111111 surfaces, #1B1B1B raised panels, white body/muted text and borders, yellow accent with black accent text, cyan focus. Dark/light colors remain separate. Remaining identified hard-coded light text and panel border colors were replaced with semantic Theme colors.
- Explicit Slint text `font-size` values now multiply by `Theme.ui-scale / 100`, in addition to `default-font-size`. The UI scale reads, saves, and permits 80–200% in 10% steps, including Python's 100/150/200 settings. At 200%, clipped layouts/reflow still require visual inspection and are not certified.
- Pure Rust WCAG 2.x relative-luminance calculation checks light/dark/contrast body and muted text against canvas and surface, primary text against accent, and accent text against surface, with 4.5:1 minimum. This is a palette audit, not a full visual WCAG evaluation. `cargo test -p researchweave-desktop --locked`: 22 tests passed; desktop build, Clippy `-D warnings`, formatting passed.
- **Focused Windows UIA display acceptance: two consecutive passes.** `powershell.exe -NoProfile -ExecutionPolicy Bypass -File crates/researchweave-desktop/tests/windows-uia-display-preferences.ps1 -Exe target/debug/researchweave-desktop.exe` launched an isolated host root, navigated via the accessible command palette, invoked accessible dark/high-contrast buttons and larger-scale control, verified JSON with `ui_scale=200`, verified accessible theme/scale text, killed and restarted the process, and reasserted restored state. It also toggled dark off while preserving high contrast and 200%, demonstrating high contrast's independence in the UI. Each of the final two runs exited 0. The script never changes the broad suite's Agent/Sources assertions.
- **Layout mitigation at 200%:** explicit heading/font scaling, taller header/object rows, wrap-enabled long labels, constrained/scaled activity rail with vertical `ScrollView`, sidebar collapse at large scale, and scrollable Preferences content; the high-contrast activity rail uses a dark surface token (not white `Theme.ink`), and standard widgets use dark styling whenever high contrast is selected regardless of the dark toggle. The UIA test confirms controls remain accessible, but programmatic evidence does not establish complete pixel-level or assistive-technology compliance.
- **Screenshot limitation:** attempted independent screenshot capture after verified UIA state. Windows screen capture intermittently recorded a black window or a different foreground application despite PID-targeted UIA and foreground/topmost requests. These images are invalid evidence and were removed. No trustworthy current focused screenshot supports a claim that all 200% layouts are visually free of clipping. Re-test visually on a dedicated desktop session without competing windows.
- `cargo fmt --package researchweave-desktop -- --check`, `cargo test -p researchweave-desktop --locked` (**22 passed**), `cargo build -p researchweave-desktop --locked`, and `cargo clippy -p researchweave-desktop --locked --all-targets -- -D warnings`: **passed** after desktop changes. During a build the Slint compiler reported layout binding-loop warnings involving window width and sidebar/inspector visibility; these are not Rust/Clippy errors but remain a defensible follow-up before declaring complete responsive-layout robustness.

Historic baseline evidence above predates this focused acceptance and should not be used to infer a green result for the independent broad Windows UIA suite. Full-screen-reader testing, Windows forced-colors mode, true 200% DPI/reflow certification, and native visual verification remain outside current observed evidence.

Keep the application-data preference file and any backup recovery artifact outside repository artifacts. No cloud transfer is performed for these preferences.
