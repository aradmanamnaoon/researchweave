# Analysis Results: automatic verified result selection and project isolation

Date: 2026-10-31. Source branch `mission/completion-20261031`; all work performed offline.

After an actual approved `analysis.result.save`, the desktop validates a 64-character hexadecimal result digest before presenting it as the selected inspect/replay result ID. The report ID input is prefilled with that digest only when its current selection is empty. A separate accessible **Use selected result** button lets the researcher explicitly replace a custom report ID list with the currently selected recorded result. The researcher retains complete control of custom 1–20-result lists. Switching active projects clears both selections before the next project is loaded.

The submitted result digest comes solely from the project's trusted successful approved `analysis.result.save` response; the preview, invalid result, denied action and variable metadata update paths cannot populate the selected result. The underlying report rendering and export handlers independently reload/verify every selected digest and bound dataset revision.

## Native validation performed

| Test | Result |
| --- | --- |
| Windows desktop `cargo test --offline --locked -p researchweave-desktop --quiet` | **60 passed** |
| Windows desktop strict Clippy | PASS |
| PowerShell native installed UIA script parser | PASS; newly asserted automatic-selection and report-shortcut behavior is pending installed package execution |
| Native Linux locked full workspace tests | **201 passed** |
| Native Linux all-target/all-feature strict Clippy | PASS |
| Native Linux full private Xvfb/AT-SPI GUI interaction suite | PASS: `ANALYSIS_RESULT_SELECTION_AND_REPORT_SHORTCUT_OK`, `ANALYSIS_RESULT_SELECTION_PROJECT_ISOLATION_OK`, `ANALYSIS_REPORT_PHYSICAL_MARKDOWN_PROVENANCE_AND_NO_OVERWRITE_OK`, `AT_SPI_NAVIGATION_PROBE_OK`, `ISOLATED_XVFB_TEST_DONE` |

The source-built native GUI suite used actual persisted immutable synthetic data and an approved saved statistical result. It checked both rendered result ID text editors, deliberately replaced the report ID with invalid data, then activated **Use selected result** and observed the original verified ID restored. It proceeded to physically export its Markdown report and checked file bytes and SHA-256. After switching to an entirely different project, both result-selection fields were empty and a previously pending data import was rejected.

Evidence: `docs/qa/mission-xvfb-20261031-result-shortcut/` includes the complete interaction trace, screenshots and accessible-node lists. Native Linux debug executable SHA-256 `7578dfa8070f2ae5e8d321af52270bf26cfdedc13bc545d6bd28a05548456fd1`.

Exact source SHA-256:

- `crates/researchweave-desktop/src/main.rs`: `6d2c1141f43791db135ef813580e575e3ea3260886881b877d2f212e15e43fae`
- `crates/researchweave-desktop/ui/main.slint`: `06aba31f3ab200096393bfcd58c6f3b395f64d3aa65af0d192f69abec09ae50c`
- `scripts/qa/mission-atspi-navigation.py`: `6f3b6587ab10cb2631fa162dd0335467e980086726462343a62c93da34815e7e`

Remaining gates: actual installed Windows UI Automation on this SHA, macOS native GUI/VoiceOver, release-level security verification and native platform package builds. This feature does not establish completion of full scientific method UI, rich report figure composition or the broader product matrix.
