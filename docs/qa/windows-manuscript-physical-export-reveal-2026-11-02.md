# Installed Windows manuscript export destination — exact-source follow-up

## Observed failure

- Candidate `cc3929fcd6e476abbd8fd4d0e9321cacc6f2e20e`, installed-native run `41390351211`, Windows job `125103689742`.
- The **real physical F37 PDF ROI acceptance passed**: same `X547 Y556, 469×164` screen pixels, blank and source-swapped SHA `ED355337...`, verified rendered SHA `8DC9DAB5...`; same-path PDF substitution refused with no project writes.
- Native Windows build, installer, command-line smoke, reviewer workflows, data imports, statistics, analysis report, qualitative and manuscript Markdown preparation also passed.
- The next failure occurred at `windows-uia-smoke.ps1:2346`: from the `Export manuscript Markdown` button, nine real Tab key actions reached DOCX, HTML, PDF, Save, Quarto, Jobs, Notifications and Window, but **skipped** the `Manuscript export destination path` edit. Its UIA viewport/focus could not be established. The actual image shows a compact/clipped installed window with manuscript editor extending below the visible viewport. Neither nonexistence nor a focus-order bug alone is proven.

## Narrow QA repair

`Reveal-ManuscriptExportPath` now insists that the genuine UIA Edit has a nonoffscreen physical rectangle intersecting the Manuscript work area, native app window and monitor working area with at least `100×18` visible pixels. It first uses a native `ScrollPattern` where supported, otherwise a finite series of physical downward wheel events **inside the installed app's visible manuscript area**, reacquires the live target, and requires `EnsureLiveFocus` to observe actual Windows keyboard focus. Failure reports exact edit bounds and visible viewport; it does not silently write to an offscreen ValuePattern or mark the GUI accepted.

Unchanged mandatory checks after actual focus: physical Markdown file creation; persisted section text; filesystem SHA-256 matching displayed receipt; repeated-save rejection; no-overwrite with a new prepared artifact; all F37 physical screenshots and project source integrity.

## Validation

- Windows PowerShell AST: 0 parse errors.
- Native QA Python source tests: 67 passed, including new export-reveal regression.
- Rustfmt and Git whitespace checks: passed.
- **No newly installed Windows UI Automation receipt exists for this repair yet.** Hosted exact-source installed test must confirm real focus and complete physical export/no-overwrite flow. No desktop user data or personal Windows shell was touched by these source tests.
