# Installed Linux manuscript revision-history button accessibility/fallback

## Reproduced exact-source failure

- Native candidate run: `41297206361` at `05ab920af5269114435b9c0193e565cbd410fccb`.
- Linux native job: `124824087106`, failed during **Full isolated Linux scientific GUI interaction regression**.
- Archived artifact: `rust-linux-full-native-gui-evidence`, captured locally beneath `target/qa/archived-05ab920-linux/mission-full-native/`.
- The script successfully created and saved versioned synthetic manuscript text, opened the Saved sections outline, loaded the saved Abstract r3, and expanded **VERSION HISTORY AND SAFE RESTORE**.
- Actual 1280x800 screenshot `manuscript-revision-history-expanded.png` visibly shows **Load revisions** at approximately x383–506/y323–355. No claim of successful AT-SPI action follows from that screenshot alone.
- The companion AT-SPI tree snapshot did not expose the conditional panel's `Load manuscript section revision history` child, despite the visible native button. The subsequent bounded `reveal_bounded_control` found the target at some point, but `activate()` returned `AT_SPI_ACTION_NOT_AVAILABLE` and the suite failed with `Visible native control could not be activated`. No restore/undo/F14 positive acceptance was reached in that run.

## Narrow verified test-harness defect and repair

`scripts/qa/mission-atspi-navigation.py::activate()` previously required `node.getRoleName() == "button"` for its **exact-name and independently bounded-rect** Xvfb mouse fallback. The installed AT-SPI tree reports actual Slint `Button` objects as **`push button`**. This mismatch prevented the fallback even when the button was genuinely visible and named. The fallback now accepts both actual known role spellings, retains exact accessible-name checks and bounds inside the private 1280x800 display, and rejects clicks over the permanent Jobs tray. `activate_bounded_control()` also performs at most four re-resolutions of the *same exact named node* for transient Slint tree updates; it never uses screenshot-predicted coordinates, and a click alone never establishes a persisted result.

`scripts/qa/test_native_atspi_button_fallback.py` compiles the actual `activate()` function AST with controlled pyatspi and xdotool substitutes. Its four tests cover native Action first, exact accessible `push button` mouse fallback, wrong name/nonbutton refusal, and offscreen-tray refusal. Python 3.11 locally: **4 tests passed**, plus both Python files syntax-compiled. The regression was added to native security, quality and release preflight CI.

## Still unverified

These source/isolated tests are not a successful installed Linux GUI rerun. The conditional panel's temporary AT-SPI tree omission still needs empirical root-cause assessment; the revised bounded fallback might still fail closed if the exact name remains absent. The subsequent visible revision-inspector hashes, preview-no-write, append-only approved restore and F14 positive scenario must pass on a newly built exact-source native package. Do not mark the Linux release gate green from this isolated fixture.
