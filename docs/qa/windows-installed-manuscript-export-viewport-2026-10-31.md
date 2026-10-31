# Windows installed manuscript export UIA — off-viewport destination recovery

Date: 2026-10-31. Base `0f1da425d8b1469fa5ad2bcbf70f0ef8f919e303`. Source: native GitHub Actions Windows job `124558094056` in run `41207467946` (commit `34a1fc8`). The actual failed-job diagnostic was retrieved from the `rust-windows-native-smoke-diagnostics` artifact.

## Verified failure evidence

The installed native Windows UI Automation log confirms all earlier manuscript stages succeeded, including persisted section inspection and the visible Markdown result after explicitly reopening and reclosing its details pane. The next action failed on `windows-uia-smoke.ps1` when querying **Manuscript export destination path** through the accessibility tree. The diagnostic tree still included the export action buttons and **Manuscript MARKDOWN prepared; no file saved yet**, but excluded the off-viewport destination field. This is a test navigation/viewport problem; the log does not prove the physical export itself failed.

## Non-weakening test correction

The installed Windows test now obtains a live **Export manuscript Markdown** UIA button and uses its existing `FocusByTab` helper to walk actual keyboard focus until the **Manuscript export destination path** edit is reachable. When it repeats the Markdown export, it uses `FocusByShiftTab` from the reachable destination instead of relying on the static accessibility tree after scrolling. DOCX preparation uses the same focus traversal from the real **Export manuscript DOCX** action. Both flows still require the actual file to exist with expected persisted manuscript bytes, verify SHA-256 and OOXML signature, reject consumed grants, and reject overwrite attempts.

## Gate status

- Windows PowerShell 5.1 syntax parser: **passed**.
- Git whitespace (`git diff --check`): **passed**.
- No application binary or backend operation was modified by this test correction.
- **Actual installed Windows UIA acceptance with the modified script has not yet passed**. A new exact-SHA GitHub Windows native job must exercise it before claiming the release gate is green. An additional failure may reveal further genuine or test-navigation issues; retain full diagnostics and fix what the next run actually demonstrates.

This correction is not evidence that a new Windows setup has passed. Nor does it establish macOS, Linux, screen-reader, or complete-product acceptance.
