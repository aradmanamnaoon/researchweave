#!/usr/bin/env python3
"""Real AT-SPI interaction helpers for a private ResearchWeave GUI session.

Named actions are resolved dynamically from the running native application's
accessibility tree. No screenshots are mocked and no coordinates are assumed
for platform-dependent widget locations.
"""
from __future__ import annotations

import subprocess
import sys
import time
from typing import Any, Iterator

import pyatspi


def children(node: Any, depth: int = 0) -> Iterator[Any]:
    yield node
    if depth >= 15:
        return
    try:
        count = min(node.childCount, 300)
    except Exception:
        return
    for index in range(count):
        try:
            child = node.getChildAtIndex(index)
        except Exception:
            continue
        if child is not None:
            yield from children(child, depth + 1)


def locate(name: str, *, actionable: bool = False) -> Any:
    end = time.monotonic() + 5.0
    while time.monotonic() < end:
        desktop = pyatspi.Registry.getDesktop(0)
        for index in range(desktop.childCount):
            app = desktop.getChildAtIndex(index)
            if "researchweave" not in str(app.name).lower():
                continue
            for child in children(app):
                try:
                    if child.name == name:
                        if actionable:
                            try:
                                if child.queryAction().nActions < 1:
                                    continue
                            except Exception:
                                continue
                        return child
                except Exception:
                    pass
        time.sleep(0.15)
    raise RuntimeError(f"accessible element not found: {name}")


def center(node: Any) -> tuple[int, int]:
    extents = node.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
    if extents.width <= 0 or extents.height <= 0:
        raise RuntimeError(f"element has no visible hit area: {node.name}")
    return extents.x + extents.width // 2, extents.y + extents.height // 2


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"click", "center"}:
        print("Usage: atspi_control.py click|center <exact accessible name>", file=sys.stderr)
        return 2
    operation, name = sys.argv[1:]
    node = locate(name, actionable=(operation == "click"))
    if operation == "center":
        x, y = center(node)
        print(f"{x} {y}")
        return 0
    try:
        action = node.queryAction()
        for index in range(action.nActions):
            if action.doAction(index):
                return 0
    except Exception:
        pass
    x, y = center(node)
    subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y), "click", "1"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
