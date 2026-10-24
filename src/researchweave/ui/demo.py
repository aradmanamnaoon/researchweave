"""Offline deterministic desktop demo and labeled screenshot capture.

Run python -m researchweave.ui.demo --output ./demo-capture.
All screenshot data is locally generated and explicitly synthetic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Literal, cast

from PyQt6.QtWidgets import QApplication

from . import build_ui_facade, build_ui_shell
from .contracts import Preferences
from .design import apply_theme
from .shell import SCREENS


def seed_demo(root: Path) -> tuple[str, dict[str, object]]:
    """Create a tiny reproducible synthetic research project without remote calls."""
    facade = build_ui_facade(root)
    existing = facade.execute("ui.project.list", {})["data"]["projects"]
    matching = [project for project in existing if project["title"] == "Synthetic attention demo"]
    if matching:
        project_id = str(matching[0]["id"])
        opened = facade.execute("ui.project.open", {"project_id": project_id})["data"]
        return project_id, opened["project"]
    created = facade.execute(
        "ui.project.create",
        {
            "title": "Synthetic attention demo",
            "question": "How are short reading sessions represented in an invented example?",
            "study_type": "mixed",
        },
    )
    if created["status"] != "ok":
        raise RuntimeError("Could not create synthetic project")
    project_id = str(created["data"]["project_id"])
    revision = int(created["data"]["revision"])
    source = facade.execute(
        "ui.source.add",
        {
            "project_id": project_id,
            "expected_revision": revision,
            "title": "Fictional lab note · Example A",
            "source_label": "Synthetic demonstration, not a research citation",
            "text": (
                "These are invented observations for a software demo.\n"
                "An example researcher wrote: A brief reading session felt easier to finish.\n"
                "No participant, experiment or source publication is represented."
            ),
        },
    )
    if source["status"] != "ok":
        raise RuntimeError("Could not create synthetic source")
    revision = int(source["data"]["revision"])
    dataset = facade.execute(
        "ui.dataset.import",
        {
            "project_id": project_id,
            "expected_revision": revision,
            "name": "Invented reading-duration data",
            "csv_text": "minutes,session\n12,1\n18,2\n15,3\n21,4\n",
        },
    )
    if dataset["status"] != "ok":
        raise RuntimeError("Could not create synthetic dataset")
    revision = int(dataset["data"]["revision"])
    saved = facade.execute(
        "ui.notebook.save",
        {
            "project_id": project_id,
            "expected_revision": revision,
            "notebook": (
                "Demo only: inspect each synthetic record before interpreting results.\n"
                "These numbers are invented and are not a scientific finding."
            ),
        },
    )
    if saved["status"] != "ok":
        raise RuntimeError("Could not persist synthetic notes")
    opened = facade.execute("ui.project.open", {"project_id": project_id})["data"]
    return project_id, opened["project"]


def _capture_name(screen: str, theme: str, width: int, height: int, scale: float) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", screen.casefold()).strip("-")
    scale_label = str(round(scale * 100))
    return f"researchweave-prototype-{slug}-{theme}-{width}x{height}-{scale_label}.png"


def capture(
    output: Path,
    *,
    theme: str,
    width: int,
    height: int,
    screen: str = "Dashboard",
    scale: float = 1.0,
) -> dict[str, object]:
    """Capture an actual offscreen-rendered prototype, including a trace receipt."""
    if theme not in ("light", "dark", "contrast"):
        raise ValueError("Unsupported theme")
    if width < 760 or height < 490 or width > 4096 or height > 2160:
        raise ValueError("Screenshot dimensions exceed supported bounds")
    if scale not in (1.0, 1.5, 2.0):
        raise ValueError("Unsupported screenshot scale")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data_root = output / "synthetic-workspace"
    project_id, project = seed_demo(data_root)
    facade = build_ui_facade(data_root)
    facade.settings.save(
        Preferences(
            theme=cast(Literal["light", "dark", "contrast"], theme),
            scale=scale,
            last_project_id=project_id,
            onboarding_complete=True,
        )
    )
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    window = build_ui_shell(fake_services=facade)
    window.resize(width, height)
    apply_theme(app, facade.settings.load())
    if screen not in SCREENS:
        raise ValueError("Unsupported screenshot screen")
    window.navigate(screen)
    window.show()
    app.processEvents()
    screenshot = output / _capture_name(screen, theme, width, height, scale)
    if not window.grab().save(str(screenshot), "PNG"):
        raise RuntimeError("Qt could not save screenshot")
    pixel_hash = hashlib.sha256(screenshot.read_bytes()).hexdigest()
    trace: dict[str, object] = {
        "status": "prototype",
        "label": "Offline PyQt UI prototype with synthetic fixtures; not the released application",
        "project_id": project_id,
        "project_revision": project["revision"],
        "source_count": len(cast(list[object], project["sources"])),
        "dataset_count": len(cast(list[object], project["datasets"])),
        "screen": screen,
        "theme": theme,
        "scale": scale,
        "width": width,
        "height": height,
        "qt_platform": os.getenv("QT_QPA_PLATFORM", "native"),
        "python": sys.version.split()[0],
        "os": platform.platform(),
        "file": screenshot.name,
        "sha256": pixel_hash,
        "alt_text": (
            f"ResearchWeave offline desktop prototype showing the {screen} screen "
            f"with a synthetic local project in {theme} theme at {round(scale * 100)}% scale."
        ),
        "network_calls_observed": 0,
    }
    (output / "capture-manifest.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    window.close()
    return trace


def capture_suite(
    output: Path,
    *,
    screens: tuple[str, ...] = (
        "Dashboard",
        "Library",
        "Review",
        "Statistics",
        "Manuscript",
        "Privacy",
    ),
    themes: tuple[str, ...] = ("light", "dark", "contrast"),
    sizes: tuple[tuple[str, int, int], ...] = (
        ("narrow", 900, 620),
        ("desktop", 1280, 720),
    ),
    scales: tuple[float, ...] = (1.0, 1.5, 2.0),
) -> dict[str, object]:
    """Capture a deterministic matrix of major screens and accessibility variants."""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    captures: list[dict[str, object]] = []
    for screen in screens:
        for theme in themes:
            for size_name, width, height in sizes:
                for scale in scales:
                    trace = capture(
                        output,
                        theme=theme,
                        width=width,
                        height=height,
                        screen=screen,
                        scale=scale,
                    )
                    trace["size_class"] = size_name
                    captures.append(trace)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": "prototype",
        "label": ("Deterministic offscreen screenshot suite using synthetic local-only fixtures."),
        "captures": captures,
        "capture_count": len(captures),
        "screens": list(screens),
        "themes": list(themes),
        "sizes": [
            {"name": name, "width": width, "height": height} for name, width, height in sizes
        ],
        "scales": list(scales),
        "network_calls_observed": 0,
        "limitations": [
            "Offscreen Qt rendering is not a substitute for native display QA.",
            "No NVDA, VoiceOver or Orca success is claimed by this capture suite.",
        ],
    }
    (output / "capture-matrix.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.rmtree(output / "synthetic-workspace", ignore_errors=True)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--theme", choices=["light", "dark", "contrast"], default="light")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    options = parser.parse_args(argv)
    print(
        json.dumps(
            capture(
                options.output, theme=options.theme, width=options.width, height=options.height
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
