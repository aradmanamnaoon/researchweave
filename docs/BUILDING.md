# Building ResearchWeave

ResearchWeave's shipped desktop runtime is native Rust/Slint. Python is not embedded in the application; a small number of Python scripts remain only for packaging or verification.

## Prerequisites

- Git.
- Rust 1.94.1 with `rustfmt` and `clippy`.
- Native build tools for the target operating system.
- Platform packages required by Slint and the OS credential store.
- PDFium when exercising the native PDF reader.

## Build and test

```powershell
rustup toolchain install 1.94.1 --profile minimal
cargo build --workspace --locked
cargo fmt --all -- --check
cargo clippy --workspace --locked --all-targets --all-features -- -D warnings
cargo test --workspace --locked --all-features
```

Run the desktop during development with:

```powershell
cargo run --locked -p researchweave-desktop
```

On Windows, `packaging/rust/fetch-pdfium-win-x64.ps1` fetches the pinned PDFium runtime and verifies its SHA-256 before use. Unix packaging uses `packaging/rust/fetch-pdfium.py` through the native packaging workflow.

## Native packages

Release packages are built and exercised on native GitHub-hosted runners by `.github/workflows/rust-release-candidate.yml` and `.github/workflows/release.yml`:

- Windows x64: Inno Setup installer plus installed-package/UIA smoke.
- macOS arm64 and Intel: DMG containing `ResearchWeave.app`, native launch/relaunch checks and Keychain acceptance.
- Linux x86_64: Debian package and AppImage, native launch/relaunch, AT-SPI and Secret Service acceptance.

`packaging/rust/build-native.py`, `package-unix.sh`, `windows-installed-smoke.ps1`, `macos-native-acceptance.sh`, and `linux-native-acceptance.sh` are the canonical packaging/acceptance helpers. Generated packages belong in CI artifacts/GitHub Releases, not Git.

## Release integrity

A release must pass the security, native package, exact-SHA live Liara, checksum, public-download and release-link gates described in `docs/release/RELEASE_READINESS.md`. Signing is verified when credentials exist; otherwise release notes must state unsigned/unnotarized status.
