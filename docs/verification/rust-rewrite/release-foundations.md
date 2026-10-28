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

After collecting all five packages and generating a canonical SHA256SUMS.txt, run `packaging/rust/verify_release_assets.py DIST VERSION` to fail closed on incomplete or corrupted packages. Publishing requires exact source/tag verification against current `main`, cargo audit, cargo deny with reviewed `deny.toml`, SBOM, license review, secret scanning, installed native GUI and data-retention checks, asset hashes, and final anonymous download/latest verification. Rust v0.2.0 is local-first; remote storage and encrypted project sync are outside its supported scope. Preserve the Python recovery tag and historical releases.
