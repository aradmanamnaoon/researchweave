"""Fetch a pinned PDFium native archive, verifying its caller-supplied SHA-256.

Never extracts archive paths outside destination, and never accepts symlinks.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

VERSION = "native-v7988"
ASSETS = {
    "windows-x64": "firecrawl-pdfium-win-x64.tgz",
    "macos-arm64": "firecrawl-pdfium-mac-arm64.tgz",
    "macos-x64": "firecrawl-pdfium-mac-x64.tgz",
    "linux-x64": "firecrawl-pdfium-linux-x64.tgz",
}
MAX_ARCHIVE_BYTES = 150_000_000
MAX_EXPANDED_BYTES = 500_000_000
MAX_MEMBER_BYTES = 250_000_000
MAX_MEMBERS = 10_000


def _safe_extract(contents: tarfile.TarFile, destination: Path) -> None:
    members = contents.getmembers()
    if len(members) > MAX_MEMBERS:
        raise ValueError("PDFium archive contains too many members")
    expanded = 0
    validated: list[tuple[tarfile.TarInfo, PurePosixPath]] = []
    for member in members:
        path = PurePosixPath(member.name)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in ("", ".", "..") for part in path.parts)
            or any("\\" in part or ":" in part or any(ord(c) < 32 for c in part) for part in path.parts)
            or not (member.isfile() or member.isdir())
        ):
            raise ValueError("PDFium archive contains unsafe member")
        if member.size < 0 or member.size > MAX_MEMBER_BYTES:
            raise ValueError("PDFium archive member exceeds size budget")
        expanded += member.size
        if expanded > MAX_EXPANDED_BYTES:
            raise ValueError("PDFium archive expanded size exceeds budget")
        validated.append((member, path))

    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    for member, path in validated:
        target = destination.joinpath(*path.parts)
        target_parent = target.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_symlink():
            raise ValueError("Refusing to replace symlink during PDFium extraction")
        resolved_parent = target_parent.resolve()
        if destination_root != resolved_parent and destination_root not in resolved_parent.parents:
            raise ValueError("PDFium archive member escapes destination")
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        source = contents.extractfile(member)
        if source is None:
            raise ValueError("PDFium archive file is unreadable")
        with source, target.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        if target.stat().st_size != member.size:
            raise ValueError("PDFium archive member size mismatch")
        os.chmod(target, member.mode & 0o777)


def fetch(platform: str, expected: str, destination: Path) -> None:
    if len(expected) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected):
        raise ValueError("A pinned 64-character SHA-256 digest is required")
    name = ASSETS[platform]
    url = f"https://github.com/firecrawl/pdfium-rs/releases/download/{VERSION}/{name}"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / name
        digest = hashlib.sha256()
        with urlopen(url, timeout=45) as response, archive.open("wb") as output:
            if response.geturl() != url and not response.geturl().startswith("https://release-assets.githubusercontent.com/"):
                raise ValueError("Unexpected PDFium download redirect")
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                if output.tell() + len(chunk) > MAX_ARCHIVE_BYTES:
                    raise ValueError("PDFium archive exceeds size budget")
                output.write(chunk)
        if digest.hexdigest() != expected.lower():
            raise ValueError("PDFium archive SHA-256 mismatch")
        with tarfile.open(archive, "r:gz") as contents:
            _safe_extract(contents, destination)
    library = "pdfium.dll" if platform == "windows-x64" else "libpdfium.dylib" if platform.startswith("macos") else "libpdfium.so"
    matches = list(destination.rglob(library))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one PDFium shared library: {library}")
    print(matches[0].resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=ASSETS)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    fetch(args.platform, args.sha256, args.destination)
