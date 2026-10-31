# Windows native candidate CI follow-up — 2026-10-31

## Source and scope

- Candidate: [GitHub Actions run 41197931223](https://github.com/aradmanamnaoon/researchweave/actions/runs/41197931223), exact source SHA `2d2e031f013605efdf7dc0a4753e9a570390800b`, Windows job `124530256414`.
- Previous candidate: [run 41186077884](https://github.com/aradmanamnaoon/researchweave/actions/runs/41186077884), source SHA `7f4e877cb3c0a5cc922d386b0768b6d4faf0eb30`, Windows job `124495086212`.
- Evidence: GitHub Actions job steps, decoded job logs, and the current run's downloadable `rust-windows-native-smoke-diagnostics` artifact `13042356201`, containing `windows-installed-cli.log` and `windows-installed-uia.log`.
- This analysis is read-only with respect to the Windows installer/smoke implementation. The failure is in a separate UI Automation test outside this worker's file ownership.

## Current candidate: exact observed failure

The Windows native desktop build, pinned PDFium download, Inno Setup installer build, and the separately gated **Windows installed candidate command-line smoke** all succeeded. The command-line diagnostic log confirms the installed executable's project, PDFium and persisted workflow smokes, uninstall-preserved user data (`USER_DATA_RETENTION_OK`), and final packaged binary/runtime SHA-256 checks (`PACKAGED_QA_OK`). Its final output records installed executable SHA-256 `40A6F58F64667A806292C186C722FAEDF75DA9F4FD41FC3B340C8594F5E526E0` and installed PDFium SHA-256 `03CC8DE22238EA9FFBBF41703F8EF8AAE77FAEAB735583815481F5C2C70A63C7`.

The **Windows installed candidate UI Automation smoke** failed in step 12. The `windows-installed-uia.log` contains successful assertions for first-run creation, accessible controls, Unicode editing, project persistence, native file pickers, PDFium, imports, statistical analysis, reference review, extraction and manuscript persistence. The first failure is:

```
UIA element missing: System.Windows.Automation.ControlType 'Export manuscript Markdown'.
At .../crates/researchweave-desktop/tests/windows-uia-smoke.ps1:41
```

The call site is `crates/researchweave-desktop/tests/windows-uia-smoke.ps1:1242`; `packaging/rust/windows-installed-smoke.ps1:138` only rethrows the child script's exit code 1. The reported UI Automation tree ends at the visible `Manuscript section body`; the requested export control is absent from the enumerated tree. The earlier `Inspect manuscript` test passed with the expected persisted Results body and citation.

In the Slint source, `crates/researchweave-desktop/ui/main.slint:2361-2379` contains a 370–560px preferred manuscript editor panel, followed by the Markdown/DOCX/HTML/PDF export controls at `:2380-2398`. The manuscript operation-details toggle at `:2273-2298` gates only the results panel, **not** the export buttons. This structure and the observed UIA tree are consistent with export controls being outside the current scroll viewport. This is a supported diagnosis, not a demonstrated fix: a native UI test must explicitly reveal/scroll to the exports and prove their UIA reachability before invoking them. Do not remove the existing physical export, digest, format and no-overwrite assertions to make the gate pass.

## Older candidate

Run `41186077884` reached a successful Windows build, PDFium stage and installer build. Its combined installed candidate UIA step failed at `crates/researchweave-desktop/tests/windows-uia-smoke.ps1:1237`:

```
Persisted manuscript body was not visible through manuscript inspect
```

The newer exact-SHA candidate advances past that assertion and fails later at the inaccessible export button. The older macOS x64/arm64 and Linux native jobs passed; the older overall run failed its Windows gate.

## Follow-up needed in files owned by the prime/UIA worker

Inspect the manuscript UI's scroll container and the `Named`/navigation helpers in `crates/researchweave-desktop/tests/windows-uia-smoke.ps1`. Add deterministic UIA scrolling or keyboard navigation to bring the actual export controls into the accessible tree. Verify Markdown export first and the later DOCX/PDF/HTML, destination path and no-overwrite steps; keep the full test fail-closed. Then run the exact-SHA Windows installed command-line + UIA smoke against a newly built installer, and re-run the complete multi-platform release-candidate workflow on the resulting committed SHA. A passing old SHA does not certify a changed source tree.

No change was justified in `packaging/rust/windows-installed-smoke.ps1`: its own install, hash, native workflow, uninstall and retention gates passed. The UIA failure was propagated, not swallowed. The Windows UIA test was not rerun locally by this worker, so a repaired outcome is **not** claimed.

At the time of this follow-up check, run `41197931223` had successful `security` and Linux native jobs; both macOS native jobs were still in progress and had no established failures. Their results require a later status check.
