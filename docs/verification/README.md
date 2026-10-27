# Verification evidence

Verification artifacts in this directory intentionally mix the current Rust rewrite evidence with retained historical evidence from the superseded Python/PyQt release. Do not transfer a result from one source commit/runtime to another.

## Current Rust evidence

The authoritative Rust rewrite/release evidence is under [`rust-rewrite/`](rust-rewrite/), together with the current top-level capability, interaction, performance, regression, DOCX, feature-expansion, and UI/UX reports added during the Rust completion pass. Run-specific documents state the exact commit/artifact scope and any native-runner limitation.

## Historical Python evidence

`INTEGRATION_LEDGER.md`, `CODE_METRICS.json`, `DEPENDENCY_LICENSES.json`, `PIP_AUDIT.json`, `SBOM.cdx.json`, `SECRETS_REVIEW.md`, `SECRETS_REVIEW_FOCUSED.json`, `SECRETS_SCAN.json`, and the legacy `e2e/` records describe the former Python/PyQt implementation. They are retained for migration/recovery provenance and are **not** the v0.2 Rust dependency, security, package, or GUI evidence.

The old internal `workstreams/v2/` development tree is no longer carried in the active Rust branch. Its full contents remain recoverable from Git history and the preserved `archive/python-final-c84cdf1` reference.

## Release interpretation

A public Rust release is accepted only from the exact-SHA native/security candidate evidence plus the protected real-Liara acceptance and final anonymous public-release checks. A committed report, screenshot, historical hash, or provider profile by itself is never sufficient release proof.
