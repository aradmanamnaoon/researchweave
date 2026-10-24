from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.schema_migrations import inspect_schema, migrate_project
from researchweave.evidence.storage import ProjectStore


def _downgrade(root: Path, version: int) -> str:
    with ProjectStore.create(root, "نسخه قدیمی", "آیا داده حفظ می‌شود؟", "observational") as store:
        project_id = store.info().id
    db = root / "data" / "project.sqlite"
    connection = sqlite3.connect(db)
    try:
        connection.execute("DROP TABLE review_retrieval")
        connection.execute("DROP TABLE review_search_hits")
        connection.execute("DROP TABLE review_search_runs")
        if version == 0:
            connection.execute("DROP TABLE reference_alias")
            connection.execute("DELETE FROM migrations")
        else:
            connection.execute("DELETE FROM migrations WHERE version>1")
        connection.execute(f"PRAGMA user_version={version}")
        connection.commit()
    finally:
        connection.close()
    return project_id


@pytest.mark.parametrize("version", [0, 1])
def test_migration_from_n_minus_two_and_n_minus_one_preserves_data(
    tmp_path: Path, version: int
) -> None:
    root = tmp_path / f"legacy-{version}"
    project_id = _downgrade(root, version)
    preview = inspect_schema(root)
    assert preview["compatibility"] == "upgrade_available"
    assert preview["migration_path"] == list(range(version + 1, 3))
    assert preview["writes"] == 0

    receipt = migrate_project(root)
    assert receipt["from_version"] == version
    assert receipt["to_version"] == 2
    assert Path(receipt["backup"]).is_file()
    with ProjectStore(root) as reopened:
        assert reopened.info().id == project_id
        assert reopened.info().title == "نسخه قدیمی"
        assert reopened.audit()["ok"]
        versions = [
            row[0]
            for row in reopened.conn.execute("SELECT version FROM migrations ORDER BY version")
        ]
        assert 2 in versions

    repeated = migrate_project(root)
    assert repeated["changed"] is False
    assert repeated["backup"] is None


def test_migration_failure_rolls_back_and_preserves_verified_backup(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    _downgrade(root, 0)

    def fail(version: int, _connection: sqlite3.Connection) -> None:
        if version == 1:
            raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="synthetic interruption"):
        migrate_project(root, failure_hook=fail)
    assert inspect_schema(root)["current_version"] == 0
    backups = list((root / "data" / "migration_backups").glob("*.sqlite"))
    assert len(backups) == 1
    verifier = sqlite3.connect(backups[0])
    try:
        assert verifier.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert verifier.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        verifier.close()


def test_migration_rejects_future_or_unrecognized_schema(tmp_path: Path) -> None:
    future = tmp_path / "future"
    with ProjectStore.create(future, "Future", "Question", "exploratory"):
        pass
    connection = sqlite3.connect(future / "data" / "project.sqlite")
    connection.execute("PRAGMA user_version=99")
    connection.commit()
    connection.close()
    assert inspect_schema(future)["compatibility"] == "future_unsupported"
    with pytest.raises(EvidenceError) as unsupported:
        migrate_project(future)
    assert unsupported.value.code == "SCHEMA_MISMATCH"

    invalid = tmp_path / "invalid"
    (invalid / "data").mkdir(parents=True)
    connection = sqlite3.connect(invalid / "data" / "project.sqlite")
    connection.execute("CREATE TABLE unrelated(value TEXT)")
    connection.execute("PRAGMA user_version=0")
    connection.commit()
    connection.close()
    preview = inspect_schema(invalid)
    assert preview["compatibility"] == "unsupported_legacy"
    with pytest.raises(EvidenceError):
        migrate_project(invalid)


def test_migration_is_available_before_legacy_project_open_through_facade(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    temporary = workspace / "temporary"
    project_id = _downgrade(temporary, 0)
    destination = workspace / project_id
    temporary.rename(destination)

    read_only = build_evidence_facade(workspace)
    preview = read_only.execute("project.migration_preview", {"project_id": project_id}, {})
    assert preview["status"] == "ok"
    assert preview["data"]["current_version"] == 0
    blocked = read_only.execute("project.migrate", {"project_id": project_id}, {})
    assert blocked["status"] == "failed"
    assert blocked["error"]["code"] == "NEEDS_APPROVAL"

    writer = build_evidence_facade(workspace, allow_local_writes=True)
    migrated = writer.execute("project.migrate", {"project_id": project_id}, {})
    assert migrated["status"] == "ok"
    reopened = writer.execute("project.open", {"project_id": project_id}, {})
    assert reopened["status"] == "ok"
    assert reopened["data"]["id"] == project_id
