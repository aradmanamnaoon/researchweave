# Linux installed-native title-page preview readback

## Observed failure

Exact-source candidate `250708ddada3a0a6a5357fb7305a6fcd5910c144`:
[GitHub Actions run 41395135031](https://github.com/aradmanamnaoon/researchweave/actions/runs/41395135031),
Linux job `125117933672`, archived `rust-linux-full-native-gui-evidence`.
The installed DEB/AppImage checks entered the full private-Xvfb AT-SPI scientific GUI regression.
The project-A reopened identity, persisted note/checklist and notebook checks passed,
followed by actual entry of all four synthetic offline title-page form fields and
activation of its native **Preview offline title page without saving** action.

The next assertion failed at `scripts/qa/mission-atspi-navigation.py:2920`:

```text
RuntimeError: Cannot read actual accessible field: Copyable unsaved title page preview
```

This control is a real, visible, read-only Slint `TextEdit` in
`crates/researchweave-desktop/ui/main.slint`. The private-Xvfb script resolved
its exact named AT-SPI node and bounded onscreen rectangle, but its old
`read_field()` required the AT-SPI `Text` interface to succeed. Slint may
expose the node while the text range API is unimplemented. This is an observed
accessibility/readback limitation, **not proof** the preview content was wrong.

## Narrow correction

The regression now calls `read_visible_field_keyboard()` with
`force_clipboard=True` on the **same onscreen native read-only preview**,
retaining the exact `grabFocus`, private X11 `Ctrl+A`/`Ctrl+C`, sentinel
clipboard replacement, nonempty actual text, SHA-256 body equality, unsaved
caveat, zero project event changes and no Title Page section creation checks.
It cannot substitute a generated backend receipt, fixture, inaccessible
offscreen value or database text for what the actual native app shows.

`scripts/qa/test_native_strict_text_clipboard_contract.py` now guards this
specific path. Locally, all 68 native source-contract tests and 7 release
preflight tests passed. These are **not** installed binary acceptance results.

## Status

The correction needs a **new exact-source hosted installed Linux GUI pass**.
Windows x64 and macOS ARM64/Intel installed acceptance, the F01–F45 feature
ledger and Liara sync remain independent release blockers. This document
does not authorize tagging, publication or a claim of full cross-platform QA.
