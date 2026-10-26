"""Probe the packaged Linux GUI through the native AT-SPI accessibility tree."""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from typing import Any

import pyatspi


def walk(node: Any, depth: int = 0) -> Iterator[tuple[Any, int]]:
    yield node, depth
    if depth >= 8:
        return
    try:
        count = node.childCount
    except Exception:
        return
    for index in range(min(count, 200)):
        try:
            child = node.getChildAtIndex(index)
        except Exception:
            continue
        if child is not None:
            yield from walk(child, depth + 1)


def find_app(timeout_seconds: float = 15.0) -> Any | None:
    deadline = time.monotonic() + timeout_seconds
    app = None
    while time.monotonic() < deadline:
        desktop = pyatspi.Registry.getDesktop(0)
        for index in range(desktop.childCount):
            candidate = desktop.getChildAtIndex(index)
            name = (candidate.name or "").strip()
            if "researchweave" in name.casefold():
                app = candidate
                break
        if app is not None:
            try:
                if app.childCount > 0:
                    return app
            except Exception:
                pass
        time.sleep(0.25)
    return app


def main() -> int:
    app = find_app()
    if app is None:
        print("AT_SPI_APP_NOT_FOUND", file=sys.stderr)
        return 2

    rows: list[tuple[str, str, int]] = []
    for node, depth in walk(app):
        try:
            role = node.getRoleName()
        except Exception:
            role = "unknown"
        try:
            name = (node.name or "").strip().replace("\n", " ")
        except Exception:
            name = ""
        rows.append((role, name[:160], depth))

    named = [(role, name, depth) for role, name, depth in rows if name]
    print(f"AT_SPI_APP={app.name}")
    print(f"AT_SPI_NODE_COUNT={len(rows)}")
    print(f"AT_SPI_NAMED_COUNT={len(named)}")

    roles = {role.casefold() for role, _, _ in rows}
    names = {name.casefold() for _, name, _ in named}
    if len(rows) < 10:
        print("AT_SPI_TREE_TOO_SMALL", file=sys.stderr)
        return 3
    if not any("window" in role or "frame" in role for role in roles):
        print("AT_SPI_WINDOW_ROLE_MISSING", file=sys.stderr)
        return 4
    required_names = ("project", "command palette", "analyze activity", "synthesize activity")
    for required in required_names:
        if not any(required in name for name in names):
            print("AT_SPI_REQUIRED_CONTROL_MISSING", file=sys.stderr)
            return 5

    print("LINUX_AT_SPI_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
