# PyInstaller specification for a self-contained ResearchWeave desktop bundle.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

repo = Path(SPECPATH).resolve().parent
hiddenimports = collect_submodules("researchweave")

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
    icon=str(repo / "assets" / "branding" / "researchweave.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ResearchWeave",
)
