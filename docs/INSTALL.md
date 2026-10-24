# Install, build and uninstall

## Development install

Windows PowerShell:

```powershell
uv sync --locked --extra dev --extra formats
uv run researchweave
```

macOS/Linux shell:

```sh
uv sync --locked --extra dev --extra formats
uv run researchweave
```

The first dependency synchronization requires package availability unless the uv cache is already populated. Normal core desktop use does not require internet access, an AI account or an R installation.

## Windows portable build

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
powershell -ExecutionPolicy Bypass -File packaging\windows\smoke-portable.ps1
```

The build creates `dist\ResearchWeave\` and a ZIP. The observed package is unsigned, so Windows reputation/SmartScreen warnings are possible. Code signing is not claimed.

## Linux/macOS builds

```sh
sh packaging/linux/build.sh
sh packaging/macos/build.sh
```

These produce portable tarballs using PyInstaller. They must be built and smoke-tested on the target operating system; a Windows build does not validate Qt plugins, glibc compatibility or macOS signing/notarization.

## Uninstall / portable removal

The portable package is removed by deleting its application directory. User project/data directories live outside that package. The Windows release smoke test explicitly verifies that deleting the extracted package does not remove a simulated user-profile sentinel.

ResearchWeave does not currently provide a destructive “remove all user data” uninstall action. Users should back up projects before deleting their application data directory manually.
