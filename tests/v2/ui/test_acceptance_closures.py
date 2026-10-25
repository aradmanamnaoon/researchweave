"""Acceptance depth for the final locally feasible Worker 4 UX gaps."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFileDialog

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.shell import display_local_path


def ok(facade, operation: str, **args):
    response = facade.execute(operation, args)
    assert response["status"] == "ok", response
    return response["data"]


def create_project(facade) -> tuple[str, int]:
    record = ok(
        facade,
        "ui.project.create",
        title="Acceptance closure",
        question="How should local acceptance evidence be represented?",
        study_type="mixed",
    )
    return str(record["project_id"]), int(record["revision"])


def test_structured_exports_annotation_sections_and_activity(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = create_project(facade)

    protocol = ok(
        facade,
        "ui.protocol.start",
        project_id=pid,
        expected_revision=revision,
        template_id="literature-map",
    )
    revision = int(protocol["revision"])
    protocol_export = ok(facade, "ui.protocol.export", project_id=pid)
    protocol_payload = json.loads(protocol_export["content"])
    assert protocol_payload["project_id"] == pid
    assert len(protocol_payload["history"]) == 1
    assert (
        hashlib.sha256(protocol_export["content"].encode()).hexdigest()
        == (protocol_export["sha256"])
    )

    prisma = ok(
        facade,
        "ui.prisma.update",
        project_id=pid,
        expected_revision=revision,
        flow={
            "records_identified": 4,
            "duplicates_removed": 1,
            "records_screened": 3,
            "records_excluded": 1,
            "reports_sought": None,
            "reports_not_retrieved": None,
            "reports_assessed": None,
            "reports_excluded": None,
            "studies_included": None,
            "exclusion_reasons": {"Synthetic mismatch": 1},
        },
    )
    revision = int(prisma["revision"])
    prisma_export = ok(facade, "ui.prisma.export", project_id=pid)
    assert "reports_sought" in prisma_export["unknown_fields"]
    assert json.loads(prisma_export["content"])["flow"]["studies_included"] is None

    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Synthetic source",
        text="alpha βeta gamma",
        source_label="Synthetic fixture",
    )
    revision = int(source["revision"])
    annotation = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=6,
        end=10,
        code="initial",
        memo="first memo",
    )
    revision = int(annotation["revision"])
    updated = ok(
        facade,
        "ui.qual.annotation.update",
        project_id=pid,
        expected_revision=revision,
        annotation_id=annotation["annotation"]["id"],
        code="revised",
        memo="reviewed memo",
    )
    revision = int(updated["revision"])
    assert updated["annotation"]["quote"] == "βeta"
    assert updated["annotation"]["code"] == "revised"

    sections = ok(
        facade,
        "ui.manuscript.sections.update",
        project_id=pid,
        expected_revision=revision,
        sections=[
            {"title": "Introduction", "body": "Synthetic introduction."},
            {"title": "Limitations", "body": "No real finding is claimed."},
        ],
    )
    assert sections["sections"][0]["order"] == 0
    reopened = build_ui_facade(tmp_path)
    section_state = ok(reopened, "ui.manuscript.sections.read", project_id=pid)
    assert [item["title"] for item in section_state["sections"]] == [
        "Introduction",
        "Limitations",
    ]
    project = ok(reopened, "ui.project.open", project_id=pid)["project"]
    assert project["manuscript"].startswith("## Introduction")
    assert "## Limitations" in project["manuscript"]
    annotations = ok(reopened, "ui.qual.list", project_id=pid)["annotations"]
    assert annotations[0]["memo"] == "reviewed memo"

    activity = ok(reopened, "ui.activity.list", project_id=pid)
    section_event = next(
        item for item in activity["events"] if item["operation"] == "ui.manuscript.sections.update"
    )
    assert section_event["target_kind"] == "manuscript"
    assert "sections" in section_event["changed_fields"]
    annotation_event = next(
        item for item in activity["events"] if item["operation"] == "ui.qual.annotation.update"
    )
    assert annotation_event["target_id"] == annotation["annotation"]["id"]


def test_saved_plot_config_and_approved_svg_png_files(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path, export_authorizer=lambda _name: True)
    pid, revision = create_project(facade)
    dataset = ok(
        facade,
        "ui.dataset.import",
        project_id=pid,
        expected_revision=revision,
        name="Synthetic values",
        csv_text="score,group\n1,A\n2,A\n3,B\n4,B\n",
    )
    revision = int(dataset["revision"])
    config = ok(
        facade,
        "ui.chart.config.save",
        project_id=pid,
        expected_revision=revision,
        name="Score distribution",
        dataset_id=dataset["dataset_id"],
        column="score",
        plot_type="histogram",
        unit="synthetic points",
        title="Synthetic score distribution",
        x_label="Score",
        y_label="Count",
        bins=4,
    )
    assert config["config"]["name"] == "Score distribution"
    saved = ok(
        build_ui_facade(tmp_path),
        "ui.chart.config.list",
        project_id=pid,
    )
    assert saved["configs"][0]["dataset_id"] == dataset["dataset_id"]

    common = {
        "project_id": pid,
        "dataset_id": dataset["dataset_id"],
        "column": "score",
        "plot_type": "histogram",
        "unit": "synthetic points",
        "title": "Synthetic score distribution",
        "x_label": "Score",
        "y_label": "Count",
        "bins": 4,
        "width": 900,
        "height": 500,
    }
    svg = ok(
        facade,
        "ui.chart.export.write",
        filename="score.svg",
        format="svg",
        **common,
    )
    png = ok(
        facade,
        "ui.chart.export.write",
        filename="score.png",
        format="png",
        **common,
    )
    assert Path(svg["path"]).read_text(encoding="utf-8").lstrip().startswith("<svg")
    assert Path(png["path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert svg["atomic_write"] is True
    assert png["source_metadata"]["descriptive_only"] is True
    collision = facade.execute(
        "ui.chart.export.write",
        {"filename": "score.svg", "format": "svg", **common},
    )
    assert collision["error"]["code"] == "CONFLICT"
    assert not list((tmp_path / "exports").glob("*.tmp"))


def test_visible_acceptance_closure_surfaces(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    pid, revision = create_project(facade)
    protocol = ok(
        facade,
        "ui.protocol.start",
        project_id=pid,
        expected_revision=revision,
        template_id="literature-map",
    )
    revision = int(protocol["revision"])
    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Visible fixture",
        text="visible annotation passage",
    )
    revision = int(source["revision"])
    annotation = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=0,
        end=7,
        code="visible",
        memo="before",
    )
    revision = int(annotation["revision"])
    evidence = ok(
        facade,
        "ui.evidence.capture",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=0,
        end=7,
        note="Visible evidence anchor.",
    )
    revision = int(evidence["revision"])
    dataset = ok(
        facade,
        "ui.dataset.import",
        project_id=pid,
        expected_revision=revision,
        name="Visible dataset",
        csv_text="score\n1\n2\n3\n",
    )

    shell = build_ui_shell(fake_services=facade)
    shell.open_project(pid)
    shell.navigate("Protocol")
    assert shell.protocol_history.count() == 1
    shell.preview_protocol_export()
    assert "SHA-256" in shell.protocol_summary.text()

    shell.navigate("PRISMA")
    shell.preview_prisma_export()
    assert "Structured export preview" in shell.prisma_summary.toPlainText()

    shell.navigate("Qualitative")
    assert shell.annotation_list.count() == 1
    shell.annotation_list.setCurrentRow(0)
    shell.annotation_code.setText("edited-visible")
    shell.annotation_memo.setText("after")
    shell.update_annotation()
    assert shell.annotation_list.item(0).text().startswith("edited-visible:")
    shell.open_selected_annotation_source()
    assert shell.page_heading.text() == "Reader"
    assert shell.reader_text.textCursor().selectedText() == "visible"

    shell.navigate("Evidence")
    assert shell.evidence_list.count() == 1
    shell.evidence_list.setCurrentRow(0)
    shell.open_selected_evidence_source()
    assert shell.page_heading.text() == "Reader"
    assert shell.reader_text.textCursor().selectedText() == "visible"

    shell.navigate("Statistics")
    dataset_index = shell.dataset_picker.findData(dataset["dataset_id"])
    shell.dataset_picker.setCurrentIndex(dataset_index)
    shell.variable_picker.setCurrentText("score")
    shell.plot_config_name.setText("Visible config")
    shell.save_plot_config()
    assert shell.plot_configs.count() == 1

    shell.navigate("Manuscript")
    shell.manuscript_section_title.setText("Methods")
    shell.manuscript_section_body.setPlainText("Synthetic methods only.")
    shell.upsert_manuscript_section()
    shell.save_manuscript_sections()
    assert "## Methods" in shell.manuscript_editor.toPlainText()

    shell.navigate("Activity")
    assert shell.activity_list.count() >= 5
    manuscript_item = next(
        shell.activity_list.item(index)
        for index in range(shell.activity_list.count())
        if "ui.manuscript.sections.update" in shell.activity_list.item(index).text()
    )
    assert "manuscript" in manuscript_item.text()
    shell.close()


def test_recovery_survives_abrupt_child_process_exit(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = create_project(facade)
    script = (
        "import os,sys;"
        "from pathlib import Path;"
        "from researchweave.ui.recovery import RecoveryJournal;"
        "from researchweave.ui.store import ProjectStore;"
        "j=RecoveryJournal(ProjectStore(Path(sys.argv[1])));"
        "j.save(sys.argv[2],'manuscript','abrupt Ω draft',int(sys.argv[3]));"
        "os._exit(17)"
    )
    result = subprocess.run(  # noqa: S603 - trusted current Python interpreter
        [sys.executable, "-c", script, str(tmp_path), pid, str(revision)],
        cwd=Path(__file__).parents[3],
        check=False,
        timeout=20,
    )
    assert result.returncode == 17
    reopened = build_ui_facade(tmp_path)
    recovery = ok(
        reopened,
        "ui.recovery.inspect",
        project_id=pid,
        field="manuscript",
    )
    assert recovery["text"] == "abrupt Ω draft"
    assert recovery["conflict"] is False
    assert recovery["note"].startswith("Preview only")


def test_protocol_deviation_overlap_and_safe_notification_retry(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    pid, revision = create_project(facade)
    started = ok(
        facade,
        "ui.protocol.start",
        project_id=pid,
        expected_revision=revision,
        template_id="literature-map",
    )
    revision = int(started["revision"])
    deviation = ok(
        facade,
        "ui.protocol.deviation.add",
        project_id=pid,
        expected_revision=revision,
        description="Synthetic search source became unavailable.",
        reason="Fixture-only deviation test.",
        impact="No scientific conclusion is drawn.",
    )
    revision = int(deviation["revision"])
    exported = ok(facade, "ui.protocol.export", project_id=pid)
    assert exported["deviations"] == 1
    payload = json.loads(exported["content"])
    assert payload["deviations"][0]["protocol_revision_sha256"]

    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Overlap fixture",
        text="abcdefghij",
    )
    revision = int(source["revision"])
    first = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=1,
        end=6,
        code="first",
    )
    revision = int(first["revision"])
    second = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=4,
        end=8,
        code="second",
    )
    revision = int(second["revision"])
    annotations = ok(facade, "ui.qual.list", project_id=pid)["annotations"]
    assert annotations[0]["overlap_count"] == 1
    assert annotations[1]["overlap_ids"] == [annotations[0]["id"]]

    notification = ok(
        facade,
        "ui.notification.add",
        project_id=pid,
        expected_revision=revision,
        code="SOURCE_SEARCH_RETRY",
        severity="warning",
        message="A local source search can be retried.",
        recovery="Retry the same bounded local source search.",
        linkage={
            "retry_operation": "ui.source.search",
            "retry_arguments": {"query": "Overlap", "limit": 10},
        },
    )
    revision = int(notification["revision"])
    retried = ok(
        facade,
        "ui.notification.retry",
        project_id=pid,
        notification_id=notification["notification"]["id"],
    )
    assert retried["retried_operation"] == "ui.source.search"
    assert retried["result"]["total"] == 1
    assert retried["local_writes"] == []
    assert retried["network_hosts"] == []

    unsafe = ok(
        facade,
        "ui.notification.add",
        project_id=pid,
        expected_revision=revision,
        code="UNSAFE_RETRY",
        severity="warning",
        message="Unsafe write retry is intentionally rejected.",
        recovery="Repeat manually after review.",
        linkage={
            "retry_operation": "ui.source.add",
            "retry_arguments": {"title": "No", "text": "No"},
        },
    )
    denied = facade.execute(
        "ui.notification.retry",
        {
            "project_id": pid,
            "notification_id": unsafe["notification"]["id"],
        },
    )
    assert denied["error"]["code"] == "PERMISSION_DENIED"


def test_visible_deviation_retry_overlap_and_export_folder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    pid, revision = create_project(facade)
    started = ok(
        facade,
        "ui.protocol.start",
        project_id=pid,
        expected_revision=revision,
        template_id="literature-map",
    )
    revision = int(started["revision"])
    source = ok(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Overlap UI fixture",
        text="abcdefghij",
    )
    revision = int(source["revision"])
    first = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=1,
        end=6,
        code="first",
    )
    revision = int(first["revision"])
    second = ok(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source["source_id"],
        start=4,
        end=8,
        code="second",
    )
    revision = int(second["revision"])
    notification = ok(
        facade,
        "ui.notification.add",
        project_id=pid,
        expected_revision=revision,
        code="VISIBLE_RETRY",
        severity="info",
        message="Safe local retry.",
        recovery="Retry source search.",
        linkage={
            "retry_operation": "ui.source.search",
            "retry_arguments": {"query": "Overlap", "limit": 10},
        },
    )

    shell = build_ui_shell(fake_services=facade)
    shell.open_project(pid)
    shell.navigate("Protocol")
    shell.protocol_deviation.setText("Visible synthetic deviation")
    shell.protocol_deviation_reason.setText("Acceptance fixture")
    shell.protocol_deviation_impact.setText("No scientific impact")
    shell.add_protocol_deviation()
    assert any(
        "DEVIATION" in shell.protocol_history.item(row).text()
        for row in range(shell.protocol_history.count())
    )

    shell.navigate("Qualitative")
    assert "overlaps 1" in shell.annotation_list.item(0).text()

    shell.navigate("Notifications")
    shell.refresh_notifications()
    assert shell.notification_list.count() == 1
    shell.notification_list.setCurrentRow(0)
    shell.retry_notification()
    assert "Retried ui.source.search" in shell.statusBar().currentMessage()

    destination = tmp_path / "chosen-exports"
    destination.mkdir()
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(destination),
    )
    shell.navigate("Exports")
    shell.choose_export_folder()
    assert facade.export_root == destination.resolve()
    assert shell.export_directory.text() == display_local_path(destination.resolve())
    assert shell.export_directory.toolTip() == str(destination.resolve())
    assert notification["notification"]["id"]
    shell.close()


def test_dashboard_surfaces_retained_job_state(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    pid, _revision = create_project(facade)
    shell = build_ui_shell(fake_services=facade)
    shell.open_project(pid)
    shell.show()
    app.processEvents()

    assert shell.jobs.submit("dashboard-job", lambda _stop: "done")
    assert shell.jobs.pool.waitForDone(2_000)
    app.processEvents()
    shell.navigate("Dashboard")
    shell.refresh_dashboard()
    assert "dashboard-job: completed (100%)" in shell.dashboard.text()
    assert "Loading local project state" not in shell.dashboard.text()
    shell.close()
