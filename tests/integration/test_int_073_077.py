"""Windows-local acceptance checks for release documentation and real UI journeys.

These checks do not substitute for clean-machine installation, native uninstall,
Linux/macOS validation, or promotion of the source checkout.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway

ROOT = Path(__file__).resolve().parents[2]


def test_int_076_documented_first_run_persists_project_and_refuses_bad_input(
    tmp_path: Path,
) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uv run researchweave" in readme
    assert "uv run researchweave-cli health" in readme
    assert "Data View" in readme and "Statistics" in readme
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        result = gateway.execute(
            "ui.project.create",
            {
                "title": "README synthetic beginner",
                "question": "Is documented onboarding persistent?",
                "study_type": "quantitative",
            },
        )
        assert result["status"] == "ok", result
        project_id = result["data"]["project_id"]
        refused = gateway.execute(
            "ui.project.create",
            {"title": "", "question": "", "study_type": "invalid"},
        )
        assert refused["status"] == "failed"
        assert services.audit.events()[-2]["operation"] == "ui.project.create"
        assert services.audit.events()[-1]["status"] == "failed"
    finally:
        services.close()
    reopened = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(reopened.ui, reopened.bus)
        opened = gateway.execute("ui.project.open", {"project_id": project_id})
        assert opened["status"] == "ok", opened
        assert "README synthetic beginner" in repr(opened["data"])
    finally:
        reopened.close()


def test_int_075_076_readme_screenshots_exist_and_match_native_manifest() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (ROOT / "assets" / "screenshots" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["capture_mode"] == "native"
    assert len(manifest["records"]) >= 6
    for record in manifest["records"]:
        image = ROOT / record["path"]
        assert image.is_file()
        assert image.stat().st_size == record["bytes"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == record["sha256"]
        assert record["actual_integrated_app"] is True
    assert sum(f"({record['path']})" in readme for record in manifest["records"]) >= 3
    for broken in ("assets/screenshots/missing.png", "docs/does-not-exist.md"):
        assert not (ROOT / broken).exists()
