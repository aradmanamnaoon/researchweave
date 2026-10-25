# Changelog

## Unreleased

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
