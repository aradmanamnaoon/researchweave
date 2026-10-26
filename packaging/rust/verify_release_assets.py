"""Verify all five native Rust release files and their checksums."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import sys

def verify(directory: Path, version: str) -> None:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid semantic version")
    names = [f"ResearchWeave-v{version}-{suffix}" for suffix in (
        "windows-x64-setup.exe", "macos-arm64.dmg", "macos-x64.dmg",
        "linux-x86_64.AppImage", "linux-amd64.deb")]
    checksums = {}
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match or match[2] in checksums:
            raise ValueError("Malformed or duplicated checksum entry")
        checksums[match[2]] = match[1].lower()
    if set(checksums) != set(names):
        raise ValueError("Incomplete or unexpected release asset set")
    for name in names:
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise ValueError(f"Missing/empty/symlinked asset: {name}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                digest.update(chunk)
        if digest.hexdigest() != checksums[name]:
            raise ValueError(f"Checksum mismatch: {name}")

if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: verify_release_assets.py DIST VERSION")
        verify(Path(sys.argv[1]), sys.argv[2])
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Release candidate rejected: {exc}") from exc
    print("Verified all five native release packages and their checksums")
