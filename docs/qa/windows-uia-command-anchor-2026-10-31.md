# Windows installed UIA: command shortcut anchor after opening a project

Date 2026-10-31. Source parent `05351f203612e9242f0ef8a54b899d30af1b32d9`.

The native Windows job `41220921713` at `a1887cc` failed inside `windows-uia-smoke.ps1` after successfully creating, cancelling a native folder chooser, reopening and displaying project metadata. Its downloaded `rust-windows-native-smoke-diagnostics/windows-installed-uia.log` showed a **Dashboard work area**, not Welcome, while the test queried the Welcome-only `Project path` input as a keyboard anchor before Ctrl+K. That input is correctly absent from the Dashboard accessibility tree.

The correction obtains **Open Start Center to switch projects** (a visible Dashboard button), focuses it, and invokes the actual Ctrl+K keyboard route. It retains the strict check that the keyboard shortcut focuses the command palette and that Enter navigates to About and produces the visible status. The stale Project-path lookup was not an actual missing application feature; no production code is changed by this focused test fix.

Validation: PowerShell syntax parser and whitespace check must pass. **An installed-package Windows UIA run containing this correction remains mandatory before release acceptance**; a parser check alone does not claim a successful installed flow.
