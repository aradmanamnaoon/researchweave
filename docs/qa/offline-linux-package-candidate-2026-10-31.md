# Native Linux offline package candidate — 2026-10-31

Status: **locally built and exercised; unpublished and not a release-ready cross-platform candidate.** The packages retain Cargo's current `0.2.0` metadata, but their binaries contain newer commits and must never be substituted for the public `v0.2.0` tag's official assets. Next public publication requires a new version, CI validation on the exact tagged SHA, and separate native Windows/macOS gates.

## Candidate

Built from the isolated `mission/completion-20261031` source checkout on WSL2 Ubuntu using cached dependencies:

```bash
cargo build --offline --locked --release -p researchweave-desktop
```

The same source passed **200 native Linux workspace unit tests** and strict all-target/all-feature workspace Clippy offline, in addition to the Windows desktop's 59 tests and strict desktop Clippy.

- Native optimized Linux executable SHA-256: `76775a694c61065763a16692210fe27df43a935b109f2ec6a3a1e433055214f2`
- `ResearchWeave-v0.2.0-linux-x86_64.AppImage` SHA-256: `42e2cfdd6478ae6c3f79be05ccf2cd7ac575ae898ad9a725fbf5e6c4f281950a`
- `ResearchWeave-v0.2.0-linux-amd64.deb` SHA-256: `5577a6591c510b7ced5458494c1c59a82e068c412ccec653291a9aad20f7c691`
- The original PDFium shared library (PDFium chromium/7988 native-v7988) SHA-256: `0c6b5e32e878b04784ced0995dc42c6f106ad02348b2fd3aa89d7886e075b66e`
- Pinned `appimagetool` SHA-256: `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`
- Pinned AppImage runtime SHA-256: `2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d`

Local copies: `target/offline-release-candidate-20261031/` (Git ignored). The WSL2 build also retains `/home/saba/researchweave-completion-20261031/dist/`. They are local review artifacts, not uploaded GitHub Release assets.

## Repeatable offline validation

`scripts/qa/offline-linux-package.sh` independently checks cached runtime/PDFium/tool hashes, stages the exact optimized executable, packages both formats, exercises executable/PDFium paths extracted from both packages and verifies its checksum manifest.

Observed output:

```text
NATIVE_PACKAGE_SMOKE_OK linux-x64 0.2.0
ResearchWeave-v0.2.0-linux-x86_64.AppImage: OK
ResearchWeave-v0.2.0-linux-amd64.deb: OK
OFFLINE_LINUX_PACKAGES_VERIFIED source=76775a694c61065763a16692210fe27df43a935b109f2ec6a3a1e433055214f2
```

`packaging/rust/linux-unprivileged-package-acceptance.sh 0.2.0` extracts both packages to an isolated temporary tree and executes their actual packaged binaries. For **each package** it verifies clean project and PDF startup, durable synthetic project/dataset/export/preferences initialization, verification before and after two real GUI launches via private Xvfb/AT-SPI, and recovery across process restarts. Observed output:

```text
UNPRIVILEGED_LINUX_GUI_OK package=deb
UNPRIVILEGED_LINUX_GUI_OK package=deb-relaunch
UNPRIVILEGED_LINUX_PACKAGE_RECOVERY_OK package=deb
UNPRIVILEGED_LINUX_GUI_OK package=appimage
UNPRIVILEGED_LINUX_GUI_OK package=appimage-relaunch
UNPRIVILEGED_LINUX_PACKAGE_RECOVERY_OK package=appimage
UNPRIVILEGED_LINUX_PACKAGES_OK version=0.2.0
```

The full **source-built** GUI workflow additionally passed `AT_SPI_NAVIGATION_PROBE_OK` with a real project, writing, evidence, analysis, save/reopen and small-window accessibility test. See `docs/qa/project-folder-picker-2026-10-31.md` for that separate evidence.

## Release gates still open

The privileged Debian system installation gate could not run locally because `sudo -n true` returned `sudo: interactive authentication is required`. The unprivileged test does not assert that dpkg post-install/uninstall cleanup and user-data retention were verified at the system level. The published Windows installer and both macOS native architectures also need newly built, exact-commit candidate packages and independent QA. Complete Rust security/SBOM and cross-platform GitHub release workflow evidence is still required; an internet outage prevents remote publication in this session.
