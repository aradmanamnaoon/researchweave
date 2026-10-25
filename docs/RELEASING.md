# Releasing ResearchWeave

The canonical release workflow is .github/workflows/release.yml. Pull requests that change source, tests, packaging, the lockfile, or the workflow build all supported native artifacts without publishing a release. A semantic-version tag starts the same builds and publishes only after every platform job succeeds.

## Release checklist

1. Update the project version consistently in pyproject.toml, src/researchweave/__init__.py, uv.lock, CITATION.cff, and CHANGELOG.md.
2. Open or update a pull request and wait for Quality plus all Release build jobs to pass.
3. Merge the verified commit to main.
4. Create an annotated tag matching the project version, for example v0.1.1, and push it.
5. Inspect the tag-triggered Release workflow. Do not create a manual release while it is running.
6. Confirm the GitHub Release contains the Windows setup and portable ZIP, Apple Silicon and Intel DMGs, Linux AppImage and DEB, and SHA256SUMS.txt.
7. Download or query every published asset and verify its URL resolves.
8. Update README.md with the verified versioned asset URLs and push that documentation change.

## Publication safeguards

The publishing job has contents: write permission; build jobs remain read-only. It validates that the tag version matches pyproject.toml, checks every required artifact is non-empty, recomputes a global SHA-256 manifest, verifies that manifest, and refuses to overwrite an existing release.

Release artifacts are currently unsigned. No Windows Authenticode certificate, Apple Developer ID certificate, or Apple notarization credentials are configured. The workflow therefore makes no signing or notarization claim.

## Failed release builds

Fix failures on a normal branch and repeat pull-request validation before tagging another version. Do not move or force-update a published tag and do not replace an existing release with unverified artifacts.

## Artifact naming

Release file names include the semantic version and platform:

- ResearchWeave-vX.Y.Z-windows-x64-setup.exe
- ResearchWeave-vX.Y.Z-windows-x64-portable.zip
- ResearchWeave-vX.Y.Z-macos-arm64.dmg
- ResearchWeave-vX.Y.Z-macos-x64.dmg
- ResearchWeave-vX.Y.Z-linux-x86_64.AppImage
- ResearchWeave-vX.Y.Z-linux-amd64.deb
- SHA256SUMS.txt
