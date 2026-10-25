# PyInstaller specification for self-contained ResearchWeave desktop bundles.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

repo = Path(SPECPATH).resolve().parent
version = os.environ.get("RESEARCHWEAVE_VERSION", "0.0.0")
hiddenimports = collect_submodules("researchweave")
if sys.platform == "win32":
    icon = str(repo / "assets" / "branding" / "researchweave.ico")
elif sys.platform == "darwin":
    icon = os.environ.get(
        "RESEARCHWEAVE_ICON",
        str(repo / "assets" / "branding" / "researchweave-icon.png"),
    )
else:
    icon = None

a = Analysis(
    [str(repo / "src" / "researchweave" / "__main__.py")],
    pathex=[str(repo / "src")],
    binaries=[],
    datas=[(str(repo / "src" / "researchweave" / "assets"), "researchweave/assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ResearchWeave",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ResearchWeave",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ResearchWeave.app",
        icon=icon,
        bundle_identifier="io.github.aradmanamnaoon.researchweave",
        version=version,
        info_plist={
            "CFBundleDisplayName": "ResearchWeave",
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "NSHighResolutionCapable": True,
        },
    )
