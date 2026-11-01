# b5ce8f8 installed native candidate failure analysis and bounded corrections

## Source and genuine acceptance evidence

- Branch `mission/completion-20261031`, exact SHA `b5ce8f8e368a214982817eefa03226831e2b48cb`.
- GitHub native run `41303157274` completed **failure**; security, macOS ARM64 and macOS Intel passed; Windows x64 installed UIA and Ubuntu 22.04 full isolated scientific GUI failed; `verify-complete` skipped.
- Four-platform Rust quality `41303157278` and `41303151881` completed success. Passing unit/security/macOS is **not** evidence of full installed product acceptance.
- Archived actual failing artifacts in `target/qa/archived-b5ce8f8/rust-windows-native-smoke-diagnostics/` and `target/qa/archived-b5ce8f8/rust-linux-full-native-gui-evidence/`. Preserve these until new exact-source native QA completes.

## Windows: actual revision visible, PowerShell 5.1 Unicode mismatch

The real 886×567 screenshot `windows-installed-uia.png` shows native sidebar text `Project · r4` and registered reference state. The UIA diagnostic confirms a live Text node `Project Â· r4` (legacy encoding/mojibake in log), but `Get-VisibleProjectRevision` at `windows-uia-smoke.ps1:318` used a literal UTF-8 middle-dot regex. On hosted PowerShell 5.1 without a BOM, script decoding can differ from UIA Unicode values and lead to false-negative matching, despite the visible node. The test already correctly requires nonzero dimensions and complete containment in the live window's UIA coordinate space. No stored revision corruption is established.

The parser is now `Parse-NativeProjectRevision`: anchored, ASCII-only `^Project\\s+\\S{1,2}\\s+r([0-9]+)$` with the exact trusted sidebar prefix, a one- or two-character separator (normal middle dot or legacy double-decoding), and decimal revision. The live bounds/visibility test is **unchanged**; no result is supplied from SQLite or the displayed reference receipt. New `scripts/qa/test-windows-uia-project-revision-contract.ps1` extracts the actual parser from the UIA script with PowerShell AST (without executing the GUI harness) and tests genuine middle dot, legacy mojibake, and rejected unrelated/malformed labels. It also inspects the live-reader AST for bounds/source checks and output-pipeline contamination. Both this new contract and the existing protocol preview pipeline contract passed under local PowerShell 5.1.

## Linux: next real project-switch isolation gate reached

The full Xvfb log shows physical synthetic analysis report export, repeat no-overwrite, staged import before project switch, native focused/clipboard readback of empty dataset identity/revision and import path after switch, stale import approval refusal, analysis selection isolation and quick-note isolation all **passed**. The run reached `Notebook` and `Show long form project notebook` before failing at `scripts/qa/mission-atspi-navigation.py:2449` on `read_field(app, "Project notebook text")` with `Cannot read actual accessible field`. This establishes unavailable direct AT-SPI Text readback; it does not establish notebook content leakage.

The new-project notebook negative check now explicitly `reveal_bounded_control` on the **actual** editor, then `read_visible_field_keyboard(..., allow_empty=True, force_clipboard=True)` with native X11 focus, random fresh sentinel and Ctrl+A/C. Any nonempty native value remains an isolation failure; offscreen/unfocusable/clipboard-unavailable nodes remain failures; no database-derived fallback is introduced. This is consistent with the guarded new-project dataset negative readback that passed in this same run. Seven isolated regression tests for AT-SPI button/clipboard contracts and Python syntax checking passed locally. A fresh hosted Xvfb run is mandatory to prove the notebook scenario and continue the downstream F14 positive suite.

An additional **not-yet-native-verified** continuation guard applies the same visible/focused clipboard proof to the reopened original project's *nonempty* saved notebook. That check is deliberately stricter than the prior direct `wait_field(queryText)` call: the stored text must really be selected/copied from the native editor and include its exact synthetic saved marker. A missing Text interface, offscreen editor, failed focus or empty clipboard is never interpreted as a successful restore. This is a preemptive code hardening of the same known inaccessible Slint TextEdit class, not an assertion that the later recovery step already passed.

## Remaining acceptance

Both changes are source/tests only until exact-source Windows/Linux native installation and GUI scripts pass to completion. They do not resolve missing F01–F45 features, Word-style parity, Liara conditional-write proof, complete native release verification, main integration, or public GitHub release. All negative no-overwrite, hash, CAS, frozen baseline, F14 kept-separate and isolation assertions remain required.
