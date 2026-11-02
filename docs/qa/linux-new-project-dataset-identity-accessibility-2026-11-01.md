# Linux installed native project-switch dataset readback: follow-up

## Verified failure on exact older source

- Native candidate `41300357835` on `939f27c0ea3cfb7dd7355f004b7cb90b863e7421`, Ubuntu 22.04, `rust-linux-full-native-gui-evidence`, archived at `target/qa/archived-939f27c-linux/`.
- Full native Xvfb/AT-SPI progressed through real project creation, manuscript+Protocol, dataset import, Variable and Statistics Views, actual synthetic descriptive mean **2.0000**, immutable analysis-result creation, physical analysis Markdown save and repeat no-overwrite refusal.
- It staged another import in original project A, switched to a newly created project B, activated Analyze, then failed at `scripts/qa/mission-atspi-navigation.py:2381` in `read_field(app, "Analysis dataset ID")` with `RuntimeError: Cannot read actual accessible field: Analysis dataset ID`.
- Failure means **native readback was not obtained** at that point. It does **not** establish either a dataset identity leak or a successful isolation check. The original test used conditional `nodes_named(..."Analysis dataset ID")` to decide whether to navigate to Data View, which could see an offscreen tree node, and then called an unconditional AT-SPI Text-interface read on unexposed/unsupported native fields.

## Bounded stricter repair

The project-switch step now explicitly opens the native `Data View` and reveals the actual `Analysis dataset ID`, `Analysis dataset revision`, and `Analysis import path` editors inside the usable viewport. Because an empty AT-SPI `queryText()` response is unreliable in Slint/AccessKit, this negative test uses `read_visible_field_keyboard(..., allow_empty=True, force_clipboard=True)`: focus the **exact visible editor**, prefill the clipboard with a newly random sentinel, then send native X11 `Ctrl+A, Ctrl+C`. Any copied nonempty data fails; no selection may count as empty only for this explicitly approved negative state and only after bounded visibility and successful focus. Incorrect/nonempty clipboard output remains a failure. No project DB result is substituted for native readback, and the surrounding project event, reference, import approval and revision checks remain untouched.

Regression `scripts/qa/test_native_empty_editor_readback.py` proves the force mode refuses a simulated misreported empty Text-interface value when native clipboard has nonempty content, the random sentinel path is opt-in, and offscreen editors fail closed. Together with the existing 4 push-button contract cases, **7 isolated Python tests passed** under Windows Python 3.11. These are static/fake-native unit tests, **not successful Linux installed native GUI acceptance**.

The corrected workflow must pass again on a fresh exact-source Ubuntu 22.04 native Xvfb package before any feature or release claim. The full F14 positive, Protocol amendment, F03/F05, F26/F43 and subsequent cold reopen checks remain mandatory.
