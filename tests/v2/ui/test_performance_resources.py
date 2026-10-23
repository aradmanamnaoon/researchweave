"""Observed bounded-resource tests for representative V2 UI workloads."""

from __future__ import annotations

import io
import os
import time
import zipfile
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade
from researchweave.ui.contracts import Project, Source, UIError, new_id, utc_now
from researchweave.ui.recovery import RecoveryJournal
from researchweave.ui.release import inspect_submission
from researchweave.ui.search import search_project
from researchweave.ui.snapshots import SnapshotManager
from researchweave.ui.visualization import histogram


def project_fixture() -> Project:
    timestamp = utc_now()
    return Project(
        id=new_id(),
        title="Synthetic performance fixture",
        question="How do bounded UI operations behave?",
        study_type="mixed",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_ten_thousand_row_import_and_pagination(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {"title": "10k rows", "question": "Paging?", "study_type": "quantitative"},
    )["data"]
    csv_text = "x,group\n" + "".join(
        f"{index},{'A' if index % 2 == 0 else 'B'}\n" for index in range(10_000)
    )
    started = time.perf_counter()
    imported = facade.execute(
        "ui.dataset.import",
        {
            "project_id": created["project_id"],
            "expected_revision": created["revision"],
            "name": "10k synthetic rows",
            "csv_text": csv_text,
        },
    )
    elapsed = time.perf_counter() - started
    assert imported["status"] == "ok", imported
    page = facade.execute(
        "ui.dataset.page",
        {
            "project_id": created["project_id"],
            "dataset_id": imported["data"]["dataset_id"],
            "offset": 9750,
            "limit": 250,
        },
    )["data"]
    assert page["total"] == 10_000
    assert len(page["rows"]) == 250
    assert page["rows"][-1][0] == "9999"
    assert elapsed < 10.0


def test_large_source_library_literal_search() -> None:
    project = project_fixture()
    project.sources = [
        Source(
            id=new_id(),
            title=f"Synthetic source {index}",
            text=(
                f"Ordinary synthetic text {index}"
                if index != 1999
                else "Final synthetic source contains Ω-target evidence"
            ),
        )
        for index in range(2_000)
    ]
    started = time.perf_counter()
    result = search_project(project, "Ω-target", categories=("source",))
    elapsed = time.perf_counter() - started
    assert result["total"] == 1
    assert result["hits"][0]["title"] == "Synthetic source 1999"
    assert elapsed < 5.0


def test_long_manuscript_release_preview_is_bounded() -> None:
    project = project_fixture()
    project.manuscript = "# Methods\n\n" + ("Synthetic reviewed draft sentence. " * 6_000)
    started = time.perf_counter()
    report = inspect_submission(project)
    elapsed = time.perf_counter() - started
    assert report["manuscript_characters"] > 150_000
    assert report["submission_approved"] is False
    assert elapsed < 5.0


def test_fifty_thousand_chart_observations_and_limit() -> None:
    values = [float(index % 100) for index in range(50_000)]
    started = time.perf_counter()
    spec = histogram(values, column="synthetic", bins=60)
    elapsed = time.perf_counter() - started
    assert spec.n == 50_000
    assert len(spec.bins) == 60
    assert elapsed < 5.0
    with pytest.raises(UIError) as caught:
        histogram(values + [1.0], column="too-large", bins=10)
    assert caught.value.code == "RESOURCE_LIMIT"


def test_large_recovery_journal_roundtrip(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {"title": "Recovery perf", "question": "Recover?", "study_type": "literature"},
    )["data"]
    journal = RecoveryJournal(facade.store)
    text = "یادداشت synthetic 🧠\n" * 8_000
    assert len(text) < 250_000
    started = time.perf_counter()
    receipt = journal.save(created["project_id"], "notebook", text, created["revision"])
    inspected = journal.inspect(created["project_id"], "notebook")
    elapsed = time.perf_counter() - started
    assert inspected["sha256"] == receipt["sha256"]
    assert inspected["text"] == text
    assert elapsed < 5.0


def test_snapshot_rejects_zip_bomb_ratio(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    created = facade.execute(
        "ui.project.create",
        {"title": "ZIP ratio", "question": "Safe?", "study_type": "literature"},
    )["data"]
    manager = SnapshotManager(facade.store)
    filename = f"{created['project_id']}-1.rwbackup"
    path = manager._path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", b"A" * 2_000_000)
        archive.writestr("project.json", b"{}")
    path.write_bytes(buffer.getvalue())
    with pytest.raises(UIError) as caught:
        manager.inspect(filename)
    assert caught.value.code == "RESOURCE_LIMIT"


def test_job_cancellation_reaches_terminal_cancelled_state() -> None:
    from PyQt6.QtCore import QEventLoop, QTimer

    from researchweave.ui.jobs import JobManager

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    manager = JobManager(max_workers=1)
    started = Event()
    states: list[str] = []
    manager.changed.connect(lambda _key, state: states.append(state))

    def work(stop: Event) -> str:
        started.set()
        deadline = time.perf_counter() + 2
        while time.perf_counter() < deadline and not stop.is_set():
            time.sleep(0.002)
        return "cancel-aware"

    assert manager.submit("cancel-me", work)
    assert started.wait(0.5)
    manager.cancel("cancel-me")
    loop = QEventLoop()
    manager.changed.connect(
        lambda _key, state: loop.quit() if state == "cancelled" else None
    )
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    assert manager.jobs["cancel-me"].state == "cancelled"
    assert "cancelling" in states
    assert "cancelled" in states
