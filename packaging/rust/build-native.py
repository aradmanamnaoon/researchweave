"""Prepare native installer inputs; native packagers perform final conversion."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=("windows-x64", "macos-arm64", "macos-x64", "linux-x64"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if not __import__("re").fullmatch(r"\d+\.\d+\.\d+", args.version):
        raise ValueError("Expected three-component semantic version")
    root = Path(__file__).resolve().parents[2]
    exe = "researchweave-desktop.exe" if args.platform.startswith("windows") else "researchweave-desktop"
    source = root / "target" / "release" / exe
    if not source.is_file() or source.stat().st_size == 0:
        raise FileNotFoundError(f"Release desktop binary missing: {source}")
    stage = root / "target" / "native-package" / args.platform
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, stage / exe)
    native = root / "target" / "pdfium" / args.platform
    pdfium_name = "pdfium.dll" if args.platform.startswith("windows") else "libpdfium.dylib" if args.platform.startswith("macos") else "libpdfium.so"
    files = list(native.rglob(pdfium_name))
    if len(files) != 1:
        raise ValueError("Verified PDFium shared library unavailable")
    shutil.copy2(files[0], stage / pdfium_name)
    shutil.copy2(root / "packaging" / "rust" / "PDFIUM_RUNTIME_NOTICES.md", stage / "PDFIUM_RUNTIME_NOTICES.md")
    print(stage)


if __name__ == "__main__":
    main()
