# Changelog

## Unreleased

- Corrected the installed Windows Data View native-format QA assertion: `dataset.inspect` returns immutable revision, original source hash and rows, while the dataset ID is read from the selected UI control. The native installer must still pass hosted installed Windows smoke on the new commit.

- Reject a delayed contextual local-model result when the active workspace or exact source/task changed after its explicit preview; the UI preserves the new work context and permits another request. Added deterministic cancel/project/page lifecycle coverage.

- Continued the Rust/Slint UX redesign on draft PR #16: accessible Data View paging/full-value inspection, scoped Quick Notes, manuscript/navigation improvements, source-backed Evidence previews, PDF page text access, and offline encrypted archive recovery. The branch remains under native GUI and scientific acceptance testing; these changes are not part of the published v0.2.0 release.
- Reworked the Windows installed UI Automation Data View probe to read the import identity from its visible fields and locate the expanded, read-only page inspector through keyboard navigation. Native Windows acceptance of this change is pending.
- Prevented Quick Notes navigation, archiving, restoring and view switches from replacing a visible draft when its SQLite optimistic save fails. The guard preserves staged recovery data and now has successful-save and concurrent-writer regression tests.
- Bound each contextual local-AI completion to an exact request UUID, active project and project generation, discarding stale canceled responses after a new request or project switch. Two deterministic race regressions pass. Local-only AI permissions are unchanged.
- Added a 200%-scale, 900×620 native PDF Reader regression harness after identifying offscreen extracted text in the pre-fix Linux build; layout correction and final native acceptance remain under verification.
- Added explicit Quick Notes conflict recovery: inspect exact retained UTF-8 draft and source revision, navigate recovery candidates, and recover as a separate new note through an idempotent SQLite transaction that preserves the newer original and refuses stale changes. Clear prior-project recovery data if loading a different project fails.
- Reorganized PDF Reader search controls for narrow, high-scale windows; reduced canvas growth and placed selectable read-only extracted text ahead of the canvas. The strict private 200% GUI suite currently fails on a clipped Find Next control and remains a release gate until fully verified.
- Verified the corrected Reader search button hit-point at genuine 200% scale in a 900×620 native Linux GUI, with complete two-page extraction, clipboard selection/copy, read-only behavior and stale-path invalidation passing. Retained the older failing screenshots and exact-source receipts for regression tracking.

## 0.2.0 - 2026-10-28

- Replaced the shipped Python/PyQt6 desktop runtime with a native Rust workspace and Slint desktop application while preserving the Python release in Git history/recovery artifacts.
- Added native project, evidence, library, analysis, AI and encrypted local archive crates behind a shared typed command/approval boundary.
- Added native Windows, macOS arm64/x64, AppImage and Debian packaging with installed/mounted package smoke, real GUI/accessibility acceptance and platform credential-store verification gates.
- Kept project archives and encrypted local recovery while removing the cloud storage and synchronization subsystems and their provider-specific release gates.
- Expanded deterministic scientific-analysis coverage, native document/PDF flows, structured writing/publishing workflows, local-first AI/provider controls and durable approval/audit behavior.
- Hardened release publication with security/supply-chain checks, SBOM/checksum verification, draft-first publication, native artifact completeness checks and post-publication download/hash verification.

## 0.1.2 - 2026-10-25

- Added schema-driven statistical forms for common analysis workflows and structured Analysis
  Results tables with diagnostics, provenance and reproducibility details instead of raw JSON-first
  interaction.
- Expanded the controlled assistant application-tool bridge across typed ResearchWeave read, write,
  code-execution, export, network and irreversible effects while preserving project scope, exact
  human approval and the CommandBus audit boundary.
- Added cooperative assistant cancellation through provider calls and tool/approval boundaries so a
  cancelled turn cannot begin another side effect.
- Added first-class native local Ollama profiles with safe local-only defaults alongside existing
  OpenAI-compatible, Anthropic and Gemini provider paths.
- Hardened interactive AI tool execution: sequential native tool-call enforcement, protocol-correct
  tool responses, untrusted tool/evidence boundaries, retry-safe failed prompts, and durable
  write-execution journaling that blocks ambiguous replay after interruption.
- Fixed the cross-platform release publication checksum path after the `v0.1.1` tag successfully
  built all six native packages but stopped before GitHub Release publication.
- Stabilized Qt background-job regression tests and normalized repository formatting so the hosted
  Windows, Linux and macOS quality gates exercise the same deterministic checks as local validation.

## 0.1.1 - 2026-10-25

- Added a per-user Windows setup executable with Start Menu integration, uninstall support, a portable ZIP, and install/launch/uninstall smoke verification.
- Added native macOS Apple Silicon and Intel application bundles distributed as DMGs, with bundle metadata, architecture, mount, and startup verification.
- Added Linux x86_64 AppImage and Debian/Ubuntu amd64 packages with desktop integration, install/startup/uninstall checks, and pinned AppImage tooling.
- Added a tag-gated GitHub Actions release pipeline that verifies native artifacts, generates SHA-256 checksums, and publishes only complete releases.
- Fixed cross-platform typing for Windows process-creation flags and upgraded CI actions to current pinned revisions.

## 0.1.0 - 2026-10-24

- Integrated V2 evidence, scientific-analysis, AI and PyQt6 desktop workstreams behind a shared typed command bus.
- Added exact one-use host approvals, hashed integration audit metadata and offline-safe application composition.
- Added production desktop-to-analysis bridging, durable AI retrieval/agent integration tests and a headless CLI.
- Added canonical scientific/document dependencies and optional rich-format readers under the `formats` extra.
- Added Windows PyInstaller portable packaging with clean extraction/startup/data-retention smoke verification.
- Added Linux/macOS portable build scripts and cross-platform GitHub Actions definitions (runner verification pending).
- Added reproducible source metrics, screenshot capture, SBOM/license/secret-scan evidence and actual light/dark app screenshots.
