#!/usr/bin/env python3
"""Write a deterministic license inventory for the locked Rust dependency graph."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("target/security/CARGO_LICENSES.json")
    root = Path(__file__).resolve().parents[2]
    lockfile = root / "Cargo.lock"
    if not lockfile.is_file():
        raise SystemExit("Cargo.lock is required")

    completed = subprocess.run(
        ["cargo", "metadata", "--locked", "--format-version", "1"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    metadata = json.loads(completed.stdout)
    packages = metadata.get("packages")
    if not isinstance(packages, list) or not packages:
        raise SystemExit("cargo metadata returned no packages")

    records = []
    for package in packages:
        records.append(
            {
                "name": package["name"],
                "version": package["version"],
                "license": package.get("license"),
                "source": package.get("source"),
                "repository": package.get("repository"),
            }
        )
    records.sort(
        key=lambda item: (
            item["name"],
            item["version"],
            item["source"] or "",
        )
    )

    report = {
        "schema": 1,
        "producer": "researchweave-cargo-license-report-v1",
        "cargo_lock_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
        "package_count": len(records),
        "packages": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
