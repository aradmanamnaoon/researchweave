# Install and run

## Development

ResearchWeave requires a Rust toolchain; the shipped desktop does not require Python.

```powershell
rustup toolchain install 1.94.1 --profile minimal
cargo run --locked -p researchweave-desktop
```

For the native PDF reader on Windows, fetch the pinned PDFium runtime first:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/rust/fetch-pdfium-win-x64.ps1
```

Linux and macOS require the native libraries/toolchains documented in `docs/BUILDING.md` and the candidate workflow.

## Release packages

The v0.2.0 Rust packages are published only after source-matched security, native installed-package/GUI and release artifact verification pass. Expected artifacts are:

- `ResearchWeave-v0.2.0-windows-x64-setup.exe`
- `ResearchWeave-v0.2.0-macos-arm64.dmg`
- `ResearchWeave-v0.2.0-macos-x64.dmg`
- `ResearchWeave-v0.2.0-linux-x86_64.AppImage`
- `ResearchWeave-v0.2.0-linux-amd64.deb`
- `SHA256SUMS.txt`

See the [latest published release](https://github.com/aradmanamnaoon/researchweave/releases/latest) for verified downloads. If the v0.2.0 assets are unavailable, use a source build or the archived Python v0.1.2 release as documented in the README.

## Data and uninstall

User projects/data live outside application package directories. Native package acceptance verifies that package removal does not delete the test user-data root. ResearchWeave does not provide a destructive "remove all research data" uninstall action; back up projects before manually deleting application data.
