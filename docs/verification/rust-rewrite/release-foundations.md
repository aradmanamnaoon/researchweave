# Rust packaging and release candidate gates

The new Rust quality workflow is intentionally independent of the existing Python release workflow. It runs formatting, compile, Clippy, and tests on Windows x64, macOS arm64, macOS Intel, and Linux x64. Green builds do not establish GUI feature parity.

Native release artifact requirements:

| OS | Native artifact filename suffix |
| --- | --- |
| Windows x64 installer | windows-x64-setup.exe |
| macOS arm64 DMG | macos-arm64.dmg |
| macOS x64 DMG | macos-x64.dmg |
| Linux x64 AppImage | linux-x86_64.AppImage |
| Debian/Ubuntu amd64 DEB | linux-amd64.deb |

Each filename starts with ResearchWeave-vVERSION-. Use native runners and a reviewed cargo-packager, Inno Setup, or AppImage/DEB packaging definition once the actual desktop executable and its runtime assets are finalized. A compiled binary alone is not an installer. Each package needs native install, GUI launch, project roundtrip, and uninstall evidence. Signing/notarization status must be accurate.

After collecting all five packages and generating a canonical SHA256SUMS.txt, run packaging/rust/verify_release_assets.py DIST VERSION to fail closed on incomplete or corrupted packages. Add cargo audit, cargo deny with reviewed deny.toml, SBOM, license review, secret scans and release URL verification before enabling a Rust publishing workflow. Do not publish or remove old Python releases until platform, migration, encrypted sync, security and GUI acceptance gates pass.
