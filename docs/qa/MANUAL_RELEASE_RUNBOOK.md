# ResearchWeave — guarded release operator runbook

This is a **release checklist and executable commands**, not a claim that
ResearchWeave is complete, that unbuilt installers exist, or that all F01–F45
features have been accepted. The latest published release was **v0.2.0**
when this guide was authored on 2026-11-01. Review
`docs/verification/FEATURE_EXPANSION.md` before promising feature parity.

**Never release directly from `mission/completion-20261031`**. Preserve its
recovery branch, historical Python tags, local projects and old release assets.
Do not use force-push, hard reset or destructive workspace cleanup. You do not
need GitHub Pro for the commands; GitHub Actions *runner access and billing*
can independently prevent successful hosted packages. No command below evades
those requirements.

## Prerequisites

- A fully reviewed, feature-accepted integration into `main`. **PR #18 currently targets `mission/prime-20261031`, not `main`**; merging it alone does not update `main`. Verify the exact base and head immediately before any merge; integrate reviewed accepted changes safely into `main` via an appropriate additional PR without force pushing or discarding history.
- All **45** rows in `docs/verification/FEATURE_EXPANSION.md` independently `RELEASE_VERIFIED`, with defensible supporting evidence; the pre-tag script now rejects `VERIFIED_LOCAL`, `IMPLEMENTED_TESTED`, `PARTIAL` and `MISSING_TARGET` equally. This gate is necessary, not a substitute for real installed GUI acceptance.
- Rust 1.94.1+ and the documented native desktop dependencies to run local
  tests; authenticated `gh` and `git`; Python **3.11+**.
- A release version newer than the actual public latest (example: `0.2.1`,
  **not a promise that this is already ready**).
- Scientific and accessibility feature limitations correctly disclosed in
  README and release notes. Real native installed acceptance must pass.

## 1. Confirm the existing PR and install the current source

On Windows PowerShell, from your own ResearchWeave checkout:

```powershell
$ErrorActionPreference = 'Stop'
gh auth status
gh pr view 18 --repo aradmanamnaoon/researchweave --json baseRefName,headRefName,mergeable,mergeStateStatus
gh pr checks 18 --repo aradmanamnaoon/researchweave
# PR #18 targets mission/prime-20261031. DO NOT mistake that branch for main.
# Review/merge into its actual base only when ALL original scope and CI gates pass.
# Create and review a separate main-targeted integration PR as appropriate;
# never assume merging PR #18 by itself updates main.
git switch main
git pull --ff-only origin main
git status --short --branch
```

A merge commit **changes the main SHA**. PR-side native tests do not count as
exact-main acceptance. Run the workflows again against the actual final
versioned main commit.

## 2. Version all source manifests together

Use the bundled version-preparation helper. Its default is a **dry run**.
With `--apply` it changes only the `[workspace.package] version` in
`Cargo.toml`, existing current-release `v0.2.0` references in `README.md`,
and the local workspace package versions in `Cargo.lock`. On failure it
restores those three originals; it never commits or tags. It preserves
historical v0.1.2 references. Review **all** edits and run strict tests.

```powershell
# Example only; choose a version newer than the actual latest:
$version = '0.2.1'
python scripts/release/bump_version.py --version $version
python scripts/release/bump_version.py --version $version --apply
git diff -- Cargo.toml Cargo.lock README.md
cargo fmt --all -- --check
cargo clippy --workspace --locked --all-targets --all-features -- -D warnings
cargo test --workspace --locked --all-features
python -m unittest discover -s scripts/release -p 'test_*.py' -v
git diff --check
git add Cargo.toml Cargo.lock README.md
git commit -m "chore(release): prepare v$version metadata"
git push origin main
```

The commands are strict: if any test fails, fix the underlying defect and
repeat. Never use `--no-verify`, `|| true`, skip tests, or invent a
signing/notarization status to make a release pass.

## 3. Launch exact-main source checks

```powershell
$version = '0.2.1'  # change to the committed workspace version
gh workflow run quality.yml --repo aradmanamnaoon/researchweave --ref main
gh workflow run rust-release-candidate.yml --repo aradmanamnaoon/researchweave --ref main -f "version=$version"
gh run list --repo aradmanamnaoon/researchweave --branch main --limit 12
```

Inspect the *two workflow_dispatch runs on the same exact SHA* and their
individual job reports. The native candidate must have `security`,
`verify-complete`, Windows installed UIA, Ubuntu installed Xvfb/AT-SPI,
macOS arm64 and macOS Intel passes. Failed or never-scheduled jobs do not
count. Quality needs all four operating systems.

## 4. Safe pre-tag readiness check

```powershell
$version = '0.2.1'
python scripts/release/check_ready.py --version $version
```

This script is **read-only** and fails closed if any F01–F45 scope item is not independently `RELEASE_VERIFIED`, or if the exact main SHA, GitHub
release version, manifest/lock versions, README URLs, clean checkout, native
matrix, or quality matrix cannot be proved. On PASS it prints the two tag
commands; inspect product acceptance and release notes **before executing**:

```powershell
git tag -a v0.2.1 -m "ResearchWeave v0.2.1"
git push origin refs/tags/v0.2.1
```

The tag starts the existing `release.yml` five-platform native builder,
package smoke tests, signing-status capture, SBOM and checksums, draft release,
independent download verification and publication workflow. **Do not manually
create another release with the same tag while that workflow is running.**
Do not push the tag if hosted GitHub Actions cannot schedule the workers.

## 5. Independent public verification after GitHub reports success

```powershell
$version = '0.2.1'
$tag = "v$version"
gh run list --repo aradmanamnaoon/researchweave --workflow release.yml --limit 5
gh release view $tag --repo aradmanamnaoon/researchweave
gh release view $tag --repo aradmanamnaoon/researchweave --json isDraft,isPrerelease,tagName,assets
gh api repos/aradmanamnaoon/researchweave/releases/latest --jq .tag_name
```

Expected exactly six public files:

```text
ResearchWeave-v0.2.1-windows-x64-setup.exe
ResearchWeave-v0.2.1-macos-arm64.dmg
ResearchWeave-v0.2.1-macos-x64.dmg
ResearchWeave-v0.2.1-linux-x86_64.AppImage
ResearchWeave-v0.2.1-linux-amd64.deb
SHA256SUMS.txt
```

Download to a new empty folder and verify every byte with the repository's
strict checker:

```powershell
$tag = 'v0.2.1'
$version = '0.2.1'
$folder = Join-Path $env:TEMP "researchweave-public-$tag"
if (Test-Path -LiteralPath $folder) { throw "Refusing to overwrite $folder" }
New-Item -ItemType Directory -Path $folder | Out-Null
gh release download $tag --repo aradmanamnaoon/researchweave --dir $folder
python packaging/rust/verify_release_assets.py $folder $version
```

Published GitHub assets are **not** the same as the unverified draft, local
build folder or CI artifacts. Verify the public release tag is the intended
main SHA, not only that the filenames exist.

## If GitHub Actions is blocked by billing or runner limits

The native packaging scripts already exist in `packaging/rust/`. A complete
manual alternative would require building and testing the **same commit** on
actual Windows, macOS Apple Silicon, macOS Intel, and Linux hosts, assembling
all five nonempty installers into one `dist/` directory, creating
`SHA256SUMS.txt` from the real bytes, running
`python packaging/rust/verify_release_assets.py dist <version>`, and
independently verifying installed GUI tests and public downloads. An Ubuntu
WSL-only build **cannot create or validate both macOS installers**. Do not
publish placeholder files or claim skipped native QA. If GitHub cannot run,
keep the release in draft until external native evidence is available.

## Current known limitations

Review the live ledger before changing this statement. As of the initial
2026-11-01 snapshot, **27 feature targets were partial and 9 missing**; F01
full rich Word parity, dedicated F44 real evaluation GUI, optional encrypted
Iranian S3 sync, and other large feature targets are unfinished. This runbook
does not silently convert these into shipped features.
