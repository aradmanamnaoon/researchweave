"""Capture actual integrated Qt screens using a deterministic synthetic local project."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

if os.name != "nt":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from researchweave.app.composition import build_services  # noqa: E402
from researchweave.app.config import AppConfig  # noqa: E402
from researchweave.app.desktop_gateway import DesktopCommandGateway  # noqa: E402
from researchweave.app.main import create_window  # noqa: E402
from researchweave.ui.contracts import Preferences  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed(gateway: DesktopCommandGateway) -> tuple[str, int]:
    created = gateway.execute(
        "ui.project.create",
        {
            "title": "Synthetic memory study",
            "question": "How do synthetic recall scores vary in this demo?",
            "study_type": "quantitative",
        },
    )["data"]
    project_id = str(created["project_id"])
    source = gateway.execute(
        "ui.source.add",
        {
            "project_id": project_id,
            "expected_revision": created["revision"],
            "title": "Synthetic study note",
            "text": (
                "Synthetic participants completed a fictional recall task. No human data are used."
            ),
            "source_label": "Deterministic synthetic fixture",
        },
    )["data"]
    dataset = gateway.execute(
        "ui.dataset.import",
        {
            "project_id": project_id,
            "expected_revision": source["revision"],
            "name": "Synthetic recall scores",
            "csv_text": "score,group\n6,A\n7,A\n8,A\n9,B\n10,B\n11,B\n",
        },
    )["data"]
    metadata = gateway.execute(
        "ui.variable.metadata.update",
        {
            "project_id": project_id,
            "expected_revision": dataset["revision"],
            "dataset_id": dataset["dataset_id"],
            "variable": "score",
            "metadata": {
                "type": "numeric",
                "role": "outcome",
                "units": "synthetic points",
                "levels": [],
                "missing_codes": [],
                "description": "Synthetic recall score",
            },
        },
    )["data"]
    result = gateway.execute(
        "ui.analysis.run",
        {
            "project_id": project_id,
            "expected_revision": metadata["revision"],
            "method": "analysis.statistics.test",
            "inputs": {
                "dataset_id": dataset["dataset_id"],
                "outcome": "score",
                "options": {"group": "group", "groups": ["A", "B"]},
            },
        },
    )["data"]
    return project_id, int(result["revision"])


def capture(root: Path, output: Path, theme: str, screen: str) -> dict[str, object]:
    services = build_services(root)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        projects = services.ui.store.list_projects()
        if projects:
            project_id = projects[0].id
        else:
            project_id, _ = seed(gateway)
            services.ai.usage.record(
                project_id=project_id,
                provider_id="synthetic-local",
                model="fixture-model",
                status="ok",
                input_tokens=128,
                output_tokens=48,
                latency_ms=42,
            )
        preferences = Preferences(
            theme=theme,  # type: ignore[arg-type]
            last_project_id=project_id,
            selected_screen=screen,
            onboarding_complete=True,
            window_width=1280,
            window_height=800,
        )
        services.ui.settings.save(preferences)
        app = QApplication.instance() or QApplication([])
        window = create_window(AppConfig(data_directory=root), services=services)
        window.resize(1280, 800)
        window.show()
        app.processEvents()
        if hasattr(window, "navigate"):
            window.navigate(screen)  # type: ignore[attr-defined]
            app.processEvents()
        if screen == "Statistics" and hasattr(window, "analysis_method"):
            method_picker = window.analysis_method  # type: ignore[attr-defined]
            for index in range(method_picker.count()):
                method = method_picker.itemData(index)
                if isinstance(method, dict) and method.get("id") == "analysis.statistics.frequency":
                    method_picker.setCurrentIndex(index)
                    break
            page = window.pages.currentWidget()  # type: ignore[attr-defined]
            if isinstance(page, QScrollArea):
                page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
            app.processEvents()
        output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(output), "PNG"):
            raise RuntimeError(f"Qt failed to save screenshot {output}")
        window.close()
        app.processEvents()
        return {
            "path": f"assets/screenshots/{output.name}",
            "sha256": sha256(output),
            "bytes": output.stat().st_size,
            "theme": theme,
            "screen": screen,
            "fixture": "deterministic synthetic local project",
            "actual_integrated_app": True,
        }
    finally:
        services.close()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    output_root = repo / "assets" / "screenshots"
    capture_root = Path(tempfile.gettempdir()) / "researchweave-public-native-capture"
    if capture_root.exists():
        shutil.rmtree(capture_root)
    capture_root.mkdir(parents=True)
    try:
        data_root = capture_root / "workspace"
        records = []
        for theme in ("light", "dark"):
            for screen in (
                "Dashboard",
                "Library",
                "Data View",
                "Variable View",
                "Statistics",
                "Analysis Results",
                "Agent",
                "Providers",
                "Review",
                "Exports",
                "Preferences",
            ):
                filename = f"researchweave-{screen.lower().replace(' ', '-')}-{theme}.png"
                records.append(capture(data_root, output_root / filename, theme, screen))
    finally:
        shutil.rmtree(capture_root, ignore_errors=True)
    manifest = {
        "schema_version": 1,
        "capture_mode": os.environ.get("QT_QPA_PLATFORM", "native"),
        "source": "scripts/capture_screenshots.py",
        "records": records,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
