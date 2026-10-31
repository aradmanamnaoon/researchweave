# ResearchWeave native candidate follow-up, 2026-10-31

This follow-up addresses concrete failures in the existing full-install workflow at source `330c4483d399e7113c64606af33691823bd41d4a` (GitHub Actions run `41202524337`). It is a test and diagnostics correction, not a release acceptance assertion.

## Windows installed UI Automation failure

GitHub's retained artifact `rust-windows-native-smoke-diagnostics` contains the installed Windows CLI smoke receipt `PACKAGED_QA_OK` followed by a native UI Automation failure after manuscript inspection:

```text
Manuscript Markdown export was not generated from persisted section revisions
... windows-uia-smoke.ps1:1258
```

The existing test explicitly collapsed the manuscript operation result panel to reach Export using the native keyboard Tab order, invoked the Markdown export callback, then immediately asserted that the generated result text remained in the Windows accessibility tree. That text belongs to the **collapsed panel**, so the observation cannot establish an export failure. The callback also reports `Manuscript MARKDOWN prepared; no file saved yet` in the always-accessible status.

The test now requires this visible preparation status, explicitly expands the details panel, checks the real persisted section and Markdown content, then collapses the panel again so the physical Save path remains usable. It still requires the physical, non-overwriting exported file and digest checks later in the test; those assertions have not been relaxed.

The updated PowerShell file parsed successfully with `System.Management.Automation.Language.Parser.ParseFile` on Windows. The final installed UI Automation result is pending hosted verification on a fresh exact candidate.

## macOS Intel packaging failure

The same run passed macOS arm64, Linux, and security gates, but macOS Intel failed at `macOS/Linux native packages` before the DMG was uploaded. GitHub's run details report exit code 1 without a package-stage log artifact. A log retrieval attempt through `gh run view --log-failed` hit a remote TLS handshake timeout, so the cause remains **unverified**.

The workflow now captures the complete Unix packaging step output with `tee` and `pipefail`, then uploads the macOS package log on any failed native job. This preserves the existing failure gate and produces the needed diagnostic evidence for the next candidate. Both PowerShell script syntax and GitHub YAML parsing succeeded locally; no macOS installed-package outcome has been claimed yet.

## Next exact-source gates

Wait for the next GitHub Actions run on the updated head SHA, inspect the Windows installed candidate UIA receipt and Intel DMG diagnostics, correct any remaining actual failures, then require the complete Windows/Linux/macOS package set and full checksum manifest before considering a new public tag.
