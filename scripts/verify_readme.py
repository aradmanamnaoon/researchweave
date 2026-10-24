"""Verify local README links and image references used by the release surface."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    missing: list[str] = []
    local_images = 0
    for raw in MARKDOWN_LINK.findall(text):
        target = raw.strip().split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        path = (root / unquote(target)).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            missing.append(raw)
            continue
        if not path.exists():
            missing.append(raw)
        if raw.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".webp")):
            local_images += 1
    if missing:
        print("Broken local README references:")
        for item in missing:
            print(f"- {item}")
        return 1
    print(f"README local references valid; local image references: {local_images}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
