# Releasing ResearchWeave

The canonical Rust release workflow is `.github/workflows/release.yml`. It is tag-triggered and fail-closed: it will not build release packages unless the exact tagged commit already has successful protected Liara acceptance from `.github/workflows/rust-live-iranian-s3-acceptance.yml`.

## Release checklist

1. Update the workspace/package version in `Cargo.toml` and all exact first-party dependency pins; regenerate `Cargo.lock`. Update `CHANGELOG.md`, `CITATION.cff`, README direct asset URLs, and current release documentation without rewriting historical evidence.
2. Run local non-GUI source/security checks and the nonpublishing hosted candidate workflow on the exact final source shape. Require security, Windows x64, Ubuntu 22.04, macOS arm64, macOS Intel, and `verify-complete` all green.
3. Preserve `archive/python-final-c84cdf1` and Git history, then fast-forward the existing `origin/main` normally to the verified Rust source. Do not force-push or create a replacement repository.
4. Require the normal Quality workflow to pass on that exact `main` SHA.
5. Configure the protected `live-iranian-s3-acceptance` environment with real Liara variables/secrets and manually run `Rust live Iranian S3 acceptance` on `main` with `head_sha` equal to the frozen final commit. Any source change after this requires a new live-provider run.
6. Only after exact-SHA live acceptance succeeds, create and push an annotated semantic-version tag matching the Cargo workspace version, for example `v0.2.0`.
7. Inspect the tag-triggered release workflow. It must re-verify the prior exact-SHA Liara evidence, build/test all native packages, generate checksums, create a draft release, re-download and verify the draft, publish it without changing `latest`, anonymously re-download/hash every public asset, and only then promote it to `latest`.
8. Confirm the anonymous `/releases/latest` endpoint, release notes, README direct URLs, and all six release downloads resolve and match `SHA256SUMS.txt`.
9. Keep legacy Python GitHub Release objects/assets until the Rust release is genuinely public and verified. Never remove the recovery tag/history.

## Publication safeguards

Build/security jobs are read-only. Only the final publication job receives `contents: write`. Release publication is globally serialized so different tags cannot race the `latest` pointer. The workflow refuses duplicate release objects, verifies tag/package version agreement, checks exact native asset names, validates the combined SHA-256 manifest, and re-verifies protected provider provenance before publication.

The workflow measures signing state rather than assuming it. If real signing credentials are configured and used, the produced artifacts must verify accordingly. If signing credentials are absent, checksums are still published and the release notes report the observed unsigned/ad-hoc/unnotarized state; no signing or notarization claim may be invented.

## Failed release builds

Fix failures on a normal branch, rerun the complete candidate matrix, fast-forward `main`, and rerun protected live-provider acceptance for the new exact SHA before tagging. Do not move or force-update a published tag and do not replace an existing release with unverified artifacts.

## Artifact naming

- `ResearchWeave-vX.Y.Z-windows-x64-setup.exe`
- `ResearchWeave-vX.Y.Z-macos-arm64.dmg`
- `ResearchWeave-vX.Y.Z-macos-x64.dmg`
- `ResearchWeave-vX.Y.Z-linux-x86_64.AppImage`
- `ResearchWeave-vX.Y.Z-linux-amd64.deb`
- `SHA256SUMS.txt`
