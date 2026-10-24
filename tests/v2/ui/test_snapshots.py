"""Verified archive creation/restoration, denial and malicious ZIP rejection."""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import UIError
from researchweave.ui.snapshots import MAX_ARCHIVE_BYTES, SnapshotManager


def good(facade, operation, **kwargs):
    result = facade.execute(operation, kwargs)
    assert result["status"] == "ok", result
    return result["data"]


def project_with_source(tmp_path: Path):
    facade = build_ui_facade(tmp_path)
    project = good(
        facade,
        "ui.project.create",
        title="Backup pilot",
        question="Could archived text be recovered?",
        study_type="qualitative",
    )
    pid = project["project_id"]
    source = good(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=1,
        title="Synthetic",
        text="🧠 reproducibility",
    )
    assert source["revision"] == 2
    return facade, pid


def test_backup_verification_and_non_destructive_restore(tmp_path: Path) -> None:
    facade, pid = project_with_source(tmp_path)
    plan = good(facade, "ui.backup.plan", project_id=pid)
    assert plan["revision"] == 2
    assert plan["passwords_included"] is False
    denied = facade.execute(
        "ui.backup.create",
        {
            "project_id": pid,
            "expected_revision": 2,
            "approved": True,
        },
    )
    assert denied["error"]["code"] == "NEEDS_APPROVAL"
    assert not (tmp_path / "backups").exists()
    facade.backup_authorizer = lambda action, value: action == "create" and value == pid
    receipt = good(facade, "ui.backup.create", project_id=pid, expected_revision=2)
    archive = tmp_path / "backups" / receipt["backup_id"]
    assert archive.is_file()
    assert zipfile.is_zipfile(archive)
    assert (
        facade.execute("ui.backup.create", {"project_id": pid, "expected_revision": 2})["error"][
            "code"
        ]
        == "CONFLICT"
    )
    listed = good(facade, "ui.backup.list")["backups"]
    assert len(listed) == 1
    assert listed[0]["integrity"] == "verified"
    inspection = good(facade, "ui.backup.inspect", backup_id=receipt["backup_id"])
    assert inspection["source_count"] == 1
    assert inspection["sha256"] == receipt["sha256"]
    denied = facade.execute(
        "ui.backup.restore",
        {
            "backup_id": receipt["backup_id"],
            "expected_sha256": receipt["sha256"],
            "approved": True,
        },
    )
    assert denied["error"]["code"] == "NEEDS_APPROVAL"
    facade.backup_authorizer = lambda action, value: (
        action == "restore" and value == receipt["backup_id"]
    )
    stale = facade.execute(
        "ui.backup.restore",
        {
            "backup_id": receipt["backup_id"],
            "expected_sha256": "0" * 64,
        },
    )
    assert stale["error"]["code"] == "STALE_REVISION"
    restored = good(
        facade,
        "ui.backup.restore",
        backup_id=receipt["backup_id"],
        expected_sha256=receipt["sha256"],
    )
    assert restored["restored_project_id"] != pid
    assert restored["preserved_original"] is True
    assert len(facade.store.list_projects()) == 2
    original = good(facade, "ui.project.open", project_id=pid)["project"]
    copy = good(facade, "ui.project.open", project_id=restored["restored_project_id"])["project"]
    assert original["revision"] == 2
    assert original["sources"][0]["text"] == copy["sources"][0]["text"]
    assert original["title"] == "Backup pilot"
    assert copy["title"].endswith("(restored)")


def _make_zip(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, raw in entries:
            output.writestr(name, raw)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "member",
    ["../project.json", "/project.json", "payload.py", "project.json/evil"],
)
def test_backup_rejects_unexpected_entries(tmp_path: Path, member: str) -> None:
    facade, pid = project_with_source(tmp_path)
    manager = SnapshotManager(facade.store)
    filename = f"{pid}-2.rwbackup"
    path = manager._path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _make_zip(
        [
            ("manifest.json", b'{"archive_version":1}'),
            (member, b"{}"),
        ]
    )
    path.write_bytes(data)
    with pytest.raises(UIError):
        manager.inspect(filename)


def test_backup_rejects_oversize_and_bad_filename(tmp_path: Path) -> None:
    facade, pid = project_with_source(tmp_path)
    manager = SnapshotManager(facade.store)
    with pytest.raises(UIError):
        manager.inspect("../secrets.json")
    path = manager._path(f"{pid}-2.rwbackup")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"a" * (MAX_ARCHIVE_BYTES + 1))
    with pytest.raises(UIError):
        manager.inspect(path.name)


def test_snapshot_qt_approval_and_restore(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade, pid = project_with_source(tmp_path)
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Backups")
    window.preview_backup()
    assert "revision 2" in window.backup_receipt.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window.create_backup()
    assert window.backup_list.count() == 0
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.create_backup()
    assert window.backup_list.count() == 1
    window.backup_list.setCurrentRow(0)
    assert "Verified SHA-256" in window.backup_receipt.text()
    window.restore_backup()
    assert window.project_id != pid
    assert "restored" in window.dashboard.text().lower()
    window.close()
