# Verification evidence

Verification documents are source- and artifact-specific. Historical Python/PyQt, superseded Rust cloud experiments and previous candidate measurements are retained only when needed for provenance. They do not establish acceptance of the final local-only Rust v0.2.0 revision.

The current Rust acceptance and release material lives under [`rust-rewrite/`](rust-rewrite/), with current capability, interaction, regression, DOCX, UI/UX and performance reports elsewhere in this directory. A `VERIFIED_LOCAL` historical label is never proof of cross-platform acceptance after a code change.

`INTEGRATION_LEDGER.md`, `CODE_METRICS.json`, `DEPENDENCY_LICENSES.json`, `PIP_AUDIT.json`, `SBOM.cdx.json`, `SECRETS_REVIEW.md`, `SECRETS_REVIEW_FOCUSED.json`, `SECRETS_SCAN.json` and legacy `e2e/` records describe the former Python edition. The old Python runtime and development workstreams are recoverable through Git history and `archive/python-final-c84cdf1`.

## Public release gate

Only a source-matched native/security candidate matrix, the exact tagged-main security/build checks and independent public release/download/hash/latest verification establish the Rust release. The earlier live Liara gate was retired with all online storage and sync features. Optional local encrypted project archives still require integrity and recovery verification.
