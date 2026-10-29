#!/usr/bin/env python3
"""Exercise every routed ResearchWeave view through REAL Linux AT-SPI actions.

Run inside a private Xvfb display and private dbus-run-session. This script does
not synthesize an accessibility tree, manipulate the user's physical desktop,
or claim that functional workflows were completed by navigating to a view.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import pyatspi


# 40 pages from the actual Slint v0.2 GUI; include placeholder destinations so
# they remain auditable even when tucked under "More sections".
GROUPS: tuple[tuple[str, tuple[tuple[int, str, str], ...]], ...] = (
    ("Home", (
        (0, "Welcome workspace screen", "Welcome"),
        (1, "Dashboard workspace screen", "Dashboard"),
        (2, "Question workspace screen", "Question"),
        (4, "Protocol workspace screen", "Protocol"),
    )),
    ("Sources", (
        (3, "Search workspace screen", "Search"),
        (5, "Library workspace screen", "Library"),
        (6, "Reader workspace screen", "Reader"),
        (7, "PDF Reader workspace screen", "PDF Reader"),
        (8, "Evidence workspace screen", "Evidence"),
        (9, "Review workspace screen", "Review"),
        (10, "PRISMA workspace screen", "PRISMA"),
        (11, "Extraction workspace screen", "Extraction"),
        (20, "References workspace screen", "References"),
    )),
    ("Analyze", (
        (12, "Data View workspace screen", "Data View"),
        (13, "Variable View workspace screen", "Variable View"),
        (14, "Statistics workspace screen", "Statistics"),
        (15, "Analysis Results workspace screen", "Analysis Results"),
        (16, "Qualitative workspace screen", "Qualitative"),
        (17, "Codebook workspace screen", "Codebook"),
        (18, "Mixed Methods workspace screen", "Mixed Methods"),
    )),
    ("Synthesize", (
        (19, "Manuscript workspace screen", "Manuscript"),
        (21, "Notebook workspace screen", "Notebook"),
        (22, "Publishing workspace screen", "Publishing"),
        (27, "Exports workspace screen", "Exports"),
    )),
    ("Automate", (
        (23, "Agent workspace screen", "Agent"),
        (31, "Jobs workspace screen", "Jobs"),
        (32, "Notifications workspace screen", "Notifications"),
    )),
    ("Manage", (
        (24, "Providers workspace screen", "Providers"),
        (25, "Privacy workspace screen", "Privacy"),
        (26, "Integrations workspace screen", "Integrations"),
        (28, "Backups workspace screen", "Backups"),
        (29, "Recovery workspace screen", "Recovery"),
        (30, "Diagnostics workspace screen", "Diagnostics"),
        (33, "Tutorials workspace screen", "Tutorials"),
        (34, "Guidance workspace screen", "Guidance"),
        (35, "Shortcuts workspace screen", "Shortcuts"),
        (36, "Preferences workspace screen", "Preferences"),
        (37, "Activity workspace screen", "Activity"),
        (38, "About workspace screen", "About"),
    )),
)


def nodes(root: Any, depth: int = 0) -> Iterator[Any]:
    yield root
    if depth >= 15:
        return
    try:
        count = min(root.childCount, 300)
    except Exception:
        return
    for i in range(count):
        try:
            child = root.getChildAtIndex(i)
        except Exception:
            continue
        if child is not None:
            yield from nodes(child, depth + 1)


def application() -> Any:
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        desktop = pyatspi.Registry.getDesktop(0)
        for i in range(desktop.childCount):
            app = desktop.getChildAtIndex(i)
            if "researchweave" in str(app.name).lower() and app.childCount:
                return app
        time.sleep(0.2)
    raise RuntimeError("ResearchWeave AT-SPI app missing")


def find(app: Any, name: str) -> Any | None:
    for node in nodes(app):
        try:
            if node.name == name:
                return node
        except Exception:
            continue
    return None


def activate(app: Any, name: str) -> tuple[bool, str]:
    node = find(app, name)
    if node is None:
        return False, "not in accessibility tree"
    try:
        action = node.queryAction()
        for index in range(action.nActions):
            if action.doAction(index):
                return True, action.getName(index)
        return False, "no action accepted"
    except Exception as exc:
        return False, f"AT-SPI invocation failed: {exc}"


def wait_for_page(app: Any, title: str, seconds: float = 2.5) -> bool:
    expected = f"{title} work area"
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if find(app, expected) is not None:
            return True
        time.sleep(0.15)
    return False


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: atspi_screen_walk.py <screenshot-directory>")
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = application()
    results: list[dict[str, object]] = []

    for activity, pages in GROUPS:
        ok, why = activate(app, f"{activity} activity")
        if not ok:
            for page_id, accessible_name, title in pages:
                results.append({
                    "page": page_id,
                    "title": title,
                    "activity": activity,
                    "passed": False,
                    "reason": f"activity navigation: {why}",
                })
            continue
        time.sleep(0.15)
        for page_id, accessible_name, title in pages:
            ok, why = activate(app, accessible_name)
            if not ok and find(app, "Reveal all destinations including planned features") is not None:
                # Accessible label on the progressive disclosure control.
                activate(app, "Reveal all destinations including planned features")
                time.sleep(0.15)
                ok, why = activate(app, accessible_name)
            if not ok and find(app, "More sections") is not None:
                activate(app, "More sections")
                time.sleep(0.15)
                ok, why = activate(app, accessible_name)
            verified = ok and wait_for_page(app, title)
            record = {
                "page": page_id,
                "title": title,
                "activity": activity,
                "passed": verified,
                "reason": why if not verified else "AT-SPI action changed the main work-area label",
            }
            if verified:
                output = out / f"page-{page_id:02d}-{title.lower().replace(' ', '-')}.png"
                subprocess.run(["import", "-window", "root", str(output)], check=True)
                record["screenshot"] = output.name
            results.append(record)
            print(f"AT_SPI_PAGE {page_id:02d} {title}: {'PASS' if verified else 'FAIL'} {record['reason']}", flush=True)

    # The project-metadata view is intentionally a contextual destination.
    ok, why = activate(app, "Home activity")
    if ok:
        ok, why = activate(app, "Dashboard workspace screen")
    if ok:
        ok, why = activate(app, "Open project metadata editor")
    verified = ok and wait_for_page(app, "Project Metadata")
    special = {
        "page": 39,
        "title": "Project Metadata",
        "activity": "Home",
        "passed": verified,
        "reason": why if not verified else "Contextual edit button changed main work-area label",
    }
    if verified:
        path = out / "page-39-project-metadata.png"
        subprocess.run(["import", "-window", "root", str(path)], check=True)
        special["screenshot"] = path.name
    results.append(special)
    results.sort(key=lambda result: int(result["page"]))

    path = out / "navigation-results.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    passed = sum(result["passed"] for result in results)
    print(f"AT_SPI_SCREEN_COVERAGE verified={passed}/{len(results)} details={path}", flush=True)
    return 0 if passed == len(results) == 40 else 1


if __name__ == "__main__":
    raise SystemExit(main())
