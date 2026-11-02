# Linux private native GUI — exact editable control targeting

Date: 2026-11-01. Scope: `scripts/qa/mission-atspi-navigation.py` only; source verification is not a native rerun.

## Observed failure (not inferred)

Exact-source candidate [GitHub Actions 41277449988](https://github.com/aradmanamnaoon/researchweave/actions/runs/41277449988), source `e9d59d10c1ef3034c16bb1b6872f912fe65fd9b8`, passed security and reached the full isolated Linux Xvfb/AT-SPI scientific GUI job. Its `rust-linux-full-native-gui-evidence` artifact records `Traceback ... edit_text(app, "Manuscript section", "Methods") ... RuntimeError: Text never appeared in the real app's accessible editor: Manuscript section` after a successful `Inspect manuscript` and `Toggle manuscript operation details`.

The native `manuscript-inspect-nodes.txt` captured the rendered bottom of a long Slint Manuscript form. It included `Manuscript section` only as parts of **other** controls such as `Manuscript section body`/`Preview manuscript section`, but not the exact editable `Manuscript section` entry. The trace shows `XVFB_TYPED_TEXT=Manuscript section chars=7`, then repeated `AT_SPI_TEXT_READBACK_MISMATCH=Manuscript section observed_length=50`. Since the helper previously selected any substring `nodes_named`, there was a credible risk of sending input to a *different* visible control rather than the intended hidden section field. The screenshot alone cannot prove exactly which control accepted the keystrokes, and no test PASS is inferred.

## Fail-closed correction

1. The general-purpose `edit_text` helper now filters returned AT-SPI nodes to an **exact casefolded accessible name**, for both editing and post-edit text readback. A missing exact field is an error, never a substitute for a same-prefix body field or status label.
2. Before changing the section from Abstract to Methods, the test first calls `reveal_bounded_control(app, "Manuscript section", down=False)`, which requires actual native component geometry in the private `1280×800` Xvfb viewport after at most 24 bounded scroll steps.
3. The next body change similarly requires exact visible `Manuscript section body` and retains existing literal text/SQLite autosave checks. Other scientific, protocol, F03/F04/F05/F14/F27 and project provenance assertions remain unchanged. The GUI script still fails when the actual control is unreachable or persistence fails.

## Verification and remaining gate

`py -3 -m py_compile scripts/qa/mission-atspi-navigation.py`, `git diff --check`, source checks of exact string matching and expected UI labels are the local static gates. The fix is **not** accepted until a new native Linux candidate executes the same full Xvfb session, captures screenshots and completes both `ISOLATED_XVFB_TEST_DONE` and `AT_SPI_NAVIGATION_PROBE_OK`, alongside the explicit F03/F14 positive markers added after this original candidate.

The failure artifact belongs to the old `e9d59d1` build, not the newer local F03 schema-v6/native UI source. Never use its result to claim the new code passed installed GUI acceptance.
