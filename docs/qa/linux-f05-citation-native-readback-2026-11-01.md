# Linux F05 citation editor native readback follow-up (2026-11-01)

## Exact-source evidence, not a successful installed run

- GitHub candidate: `41314931146`, source `4aca0dd37ac838ab9e0418a524d90715c2901cda`.
- Native Ubuntu 22.04 job `124875549325`: **failure** during full private Xvfb/AT-SPI GUI acceptance.
- Original artifact: `rust-linux-full-native-gui-evidence`, copied into ignored `target/qa/archived-4aca0dd-linux/` without modifying the source artifact or research data.
- Verified previous F14 panel-collapse and native F05 source registration markers:
  `F05_NATIVE_REFERENCE_FORM_RECOVERED_BY_ACCESSIBLE_F14_PANEL_COLLAPSE_OK` and
  `F05_REFERENCE_REGISTERED_VIA_AUDITED_NATIVE_PREVIEW_AND_APPROVAL_OK`.
- Verified registration used the actual Slint form, audited `library.reference_add`, immutable revision/event increment and exact raw BibTeX bytes. Screenshot `mission-full-native/f05-reference-registered.png` shows a populated native References form and local-write result.
- First observed failure after returning to Manuscript: `RuntimeError: Cannot read actual accessible field: Manuscript citations` in `exercise_f05_project_citation` at the pre-insertion citation comparison. This is an unsupported/failed **AT-SPI Text read**, not evidence that the manuscript's actual citations are missing.

## Bounded correction

Both exact `Manuscript citations` readback sites in `scripts/qa/mission-atspi-navigation.py` now use the existing `read_visible_field_keyboard` path instead of assuming `queryText` works. The helper first considers AT-SPI Text; when not supported, it requires an exact named native LineEdit with nonzero visible viewport bounds, successful native focus, an X11 window, fresh randomized clipboard sentinel, actual Ctrl+A/C and a real clipboard response. It never substitutes a SQLite value for live GUI content.

For the expected-empty initial citation list, clipboard verification is forced, so an unsupported or stale AT-SPI empty string cannot be accepted as evidence that the visible editor is empty. For the expected-nonempty post-Apply list, a missing/empty AT-SPI result requires a nonempty native clipboard read. Both results are still compared against independently persisted immutable citation lists and events; all existing missing-reference/no-write, exact UUID, autosave, history and cross-project negative checks remain enabled.

Local validation of the correction:

```text
python -m py_compile scripts/qa/mission-atspi-navigation.py scripts/qa/test_native_empty_editor_readback.py
python -m unittest discover -s scripts/qa -p 'test_native_*.py' -q
Ran 11 tests: OK
git diff --check: passed
```

The newly added source contract asserts that both F05 citation reads use the actual native field path and do not silently revert to inaccessible `read_field` or database-derived synthetic GUI data. These are local unit/source-contract tests, **not installed-native verification**. New hosted native Linux execution, subsequent F05 citation preview/Apply/persistence and all remaining F14/F07/F03 scenarios must pass on the new exact source before marking the native suite accepted.
