# Building ResearchWeave

ResearchWeave is a Python 3.12 / PyQt6 desktop application packaged with PyInstaller. Release artifacts are built on the operating system they target; cross-compiling the final installers is not supported.

## Prerequisites

- Git
- uv
- Python 3.12 managed by uv
- Windows: Inno Setup 6
- macOS: Xcode command-line tools supplied by the GitHub-hosted runner
- Linux: curl, dpkg-deb, file, and standard GNU utilities

The Python dependency graph is locked in uv.lock. Build scripts install the locked dev, formats, and release extras before packaging.

## Windows

Run from the repository root:

    powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
    powershell -ExecutionPolicy Bypass -File packaging\windows\smoke-portable.ps1
    powershell -ExecutionPolicy Bypass -File packaging\windows\smoke-installer.ps1

The build emits a per-user setup executable, a portable ZIP, and a Windows checksum manifest under dist/.

## macOS

Run on the target macOS architecture:

    bash packaging/macos/build.sh
    bash packaging/macos/smoke.sh

The build emits a DMG containing ResearchWeave.app. Apple Silicon and Intel are built on separate GitHub-hosted runners so the architecture is observed rather than inferred.

## Linux

Run on x86_64 Linux:

    bash packaging/linux/build.sh
    bash packaging/linux/smoke.sh

The build emits an x86_64 AppImage and an amd64 Debian package. The AppImage builder and type-2 runtime are downloaded from pinned upstream releases and verified against pinned SHA-256 digests before use.

## Verification levels

The packaging scripts distinguish three checks:

1. Build verification: the expected installer exists, is non-empty, and carries the expected version/architecture metadata.
2. Runtime smoke verification: the packaged application starts and remains alive long enough to detect immediate loader/runtime failures.
3. Installer verification: where supported, CI installs and removes the package and confirms simulated user-profile data survives uninstall.

GUI smoke tests use Qt's offscreen platform because GitHub-hosted runners do not provide an interactive desktop session suitable for human UI validation.

Generated installers, build directories, caches, and temporary package roots stay outside Git. Release binaries belong on GitHub Releases.
