"""Freeze the final Python capability manifest for Rust parity verification."""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from researchweave.app.composition import build_services


def main() -> None:
    destination = Path("docs/verification/rust-rewrite/python-capabilities.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rw-capabilities-") as temporary:
        services = build_services(Path(temporary))
        try:
            domains: dict[str, object] = {}
            total = 0
            for name in ("evidence", "analysis", "ai", "ui"):
                facade = getattr(services, name)
                manifest = [dict(item) for item in facade.capability_manifest()]
                manifest.sort(key=lambda item: str(item["operation"]))
                operations = [str(item["operation"]) for item in manifest]
                if len(operations) != len(set(operations)):
                    raise RuntimeError(f"duplicate capability in {name}")
                total += len(manifest)
                domains[name] = {
                    "count": len(manifest),
                    "effects": dict(sorted(Counter(str(item["effect"]) for item in manifest).items())),
                    "capabilities": manifest,
                }
            payload = {
                "format": "researchweave-python-capabilities-v1",
                "python_final_git": "c84cdf1442f45e0a73e5e6cdfe7b3716d9a1450b",
                "total": total,
                "domains": domains,
            }
            if total != 439:
                raise RuntimeError(f"expected 439 final Python operations, got {total}")
            destination.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        finally:
            services.close()
    print(f"wrote {destination} with {total} operations")


if __name__ == "__main__":
    main()
