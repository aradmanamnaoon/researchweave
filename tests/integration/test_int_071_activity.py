"""INT-071: clickable recent-history navigation with hash evidence."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway
from researchweave.ui import build_ui_shell


def test_activity_click_opens_hashed_source_and_bus_audit(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    services = build_services(tmp_path)
    shell = None
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        created = gateway.execute(
            "ui.project.create",
            {
                "title": "Activity fixture",
                "question": "Can a history event reopen its result?",
                "study_type": "mixed",
            },
        )
        assert created["status"] == "ok", created
        project = created["data"]
        added = gateway.execute(
            "ui.source.add",
            {
                "project_id": project["project_id"],
                "expected_revision": project["revision"],
                "title": "Traceable source",
                "text": "synthetic source text",
                "source_label": "INT-071 fixture",
            },
        )
        assert added["status"] == "ok", added
        source_id = added["data"]["source_id"]
        content_hash = added["data"]["content_sha256"]

        shell = build_ui_shell(fake_services=services.ui)
        shell.open_project(project["project_id"])
        shell.navigate("Activity")
        shell.refresh_activity()
        item = next(
            shell.activity_list.item(index)
            for index in range(shell.activity_list.count())
            if "ui.source.add" in shell.activity_list.item(index).text()
        )
        shell.open_activity_event(item)
        assert shell.current_source_id == source_id
        assert shell.page_heading.text() == "Reader"
        assert content_hash in shell.reader_meta.text()
        assert shell.reader_text.toPlainText() == "synthetic source text"

        bus_event = next(
            event for event in services.audit.events() if event["operation"] == "ui.source.add"
        )
        assert len(bus_event["input_sha256"]) == 64
        assert len(bus_event["output_sha256"]) == 64
        assert "synthetic source text" not in repr(bus_event)
    finally:
        if shell is not None:
            shell.close()
        services.close()
