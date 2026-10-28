# Rust release readiness

ResearchWeave v0.2 is publishable only when every mandatory gate is tied to the exact source commit being released. A locally passing build or a committed evidence file alone is not sufficient.

## Required source and security gates

- `cargo fmt --all -- --check`
- strict workspace Clippy with warnings denied and all features/targets
- locked all-features workspace tests, including migration and project archive/recovery regressions
- RustSec/yanked checks and `cargo deny check`
- Gitleaks/history scan
- CycloneDX SBOM and dependency/license review
- release-asset/checksum verifier

## Required native package gates

The candidate workflow builds and exercises Windows x64, macOS arm64, macOS Intel and Ubuntu x86_64 packages on native hosted runners. Platform evidence must come from the actual package: Windows installed UIA flows, macOS mounted-app launch/relaunch, Linux DEB/AppImage launch/relaunch plus AT-SPI. Runner limitations such as macOS AX/TCC are documented rather than converted into a pass.

## Publication sequence

1. Preserve `archive/python-final-c84cdf1` and normal Git history.
2. Push the validated Rust-only source to the existing `origin/main` without force.
3. Require quality CI success and native candidate acceptance at the final source SHA.
4. Create/push the annotated semver tag only after those gates.
5. Build all native release artifacts, verify hashes, and create a draft release.
6. Re-download/verify the draft, publish it without changing `latest`, and anonymously download/hash every public asset.
7. Promote to `latest` only after public verification, then anonymously verify `/releases/latest` and README asset URLs.
8. Preserve old Python Release objects until the Rust release is publicly verified.

If signing credentials are configured, verify Authenticode and Developer ID/notarization/stapling. If they are absent, publish checksums and report unsigned/unnotarized status explicitly.

Current run-specific evidence belongs in `docs/verification/rust-rewrite/release-candidate-gates.md` and `acceptance-ledger-status.md`; do not copy historical hashes to newer artifacts.
