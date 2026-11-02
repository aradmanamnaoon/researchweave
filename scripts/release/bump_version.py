#!/usr/bin/env python3
"""Safely prepare the next Rust workspace version and README links.

Changes nothing without --apply. Requires clean main; never commits, tags,
publishes, or bypasses quality/native validation.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable

from check_ready import ReleaseBlocked, check_readme, check_workspace_lock, version_parts


def next_contents(
    cargo: str, readme: str, *, current: str, requested: str,
) -> tuple[str, str]:
    if version_parts(requested) <= version_parts(current):
        raise ReleaseBlocked("New version must be strictly greater than current workspace version")
    # Change only [workspace.package] version, never dependency version strings.
    pattern = (
        r"(?m)(^\[workspace\.package\]\s*\n)"
        r"((?:(?!^\[)[\s\S])*?)"
        r"(^version\s*=\s*\")" + re.escape(current) + r"(\"\s*$)"
    )
    replacement = lambda match: (
        match.group(1) + match.group(2) + match.group(3) + requested + match.group(4)
    )
    updated_cargo, count = re.subn(pattern, replacement, cargo, count=1)
    if count != 1:
        raise ReleaseBlocked("Could not uniquely locate the workspace package version")
    if f"v{current}" not in readme:
        raise ReleaseBlocked("README lacks expected old current-release links")
    updated_readme = readme.replace(f"v{current}", f"v{requested}")
    if updated_readme == readme:
        raise ReleaseBlocked("README current-release links did not change")
    return updated_cargo, updated_readme


def ensure_clean_main(root: Path, cmd: Callable[..., str]) -> None:
    if cmd("git", "branch", "--show-current") != "main":
        raise ReleaseBlocked("Version bump requires the main branch")
    if cmd("git", "status", "--porcelain"):
        raise ReleaseBlocked("Version bump requires a clean working tree")


def run(*argv: str, root: Path) -> str:
    result = subprocess.run(
        argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", text=True, timeout=120, check=False,
    )
    if result.returncode:
        raise ReleaseBlocked(f"{' '.join(argv)} failed: {result.stderr.strip()[:500]}")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--apply", action="store_true", help="Make the version changes")
    options = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    files = [root / name for name in ("Cargo.toml", "README.md", "Cargo.lock")]
    original = [file.read_bytes() for file in files]
    try:
        ensure_clean_main(root, lambda *cmd: run(*cmd, root=root))
        from check_ready import read_workspace_version

        current = read_workspace_version(root)
        replacement = next_contents(
            original[0].decode("utf-8"), original[1].decode("utf-8"),
            current=current, requested=options.version,
        )
        print(f"Version plan: {current} -> {options.version}")
        print(f"README current-release references: {original[1].decode('utf-8').count(f'v{current}')}")
        if not options.apply:
            print("DRY RUN only. Repeat with --apply, review the diff, then run tests.")
            return 0
        try:
            files[0].write_text(replacement[0], encoding="utf-8", newline="")
            files[1].write_text(replacement[1], encoding="utf-8", newline="")
            run("cargo", "update", "--workspace", "--offline", root=root)
            check_workspace_lock(root, options.version)
            check_readme(root, options.version)
            run("git", "diff", "--check", root=root)
        except Exception:
            for file, previous in zip(files, original):
                file.write_bytes(previous)
            raise
    except (ReleaseBlocked, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(f"VERSION PREPARATION BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("Workspace, Cargo.lock and README prepared. Review diff, run tests, commit and push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
