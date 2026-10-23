"""Explicit, backup-preserving SQLite schema migration runner."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .errors import EvidenceError, require
from .models import SCHEMA_VERSION, new_id, now_utc
from .storage import REVIEW_SCHEMA_V2, _schema_statements

MigrationHook = Callable[[int, sqlite3.Connection], None]

V0_TO_V1 = """
CREATE TABLE IF NOT EXISTS migrations (
    version INTEGER PRIMARY KEY, installed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reference_alias (
    original_id TEXT PRIMARY KEY REFERENCES reference(id),
    canonical_id TEXT NOT NULL REFERENCES reference(id),
    reason TEXT NOT NULL
);
"""

LEGACY_REQUIRED_TABLES = {
    "project",
    "events",
    "objects",
    "sources",
    "document_text",
    "reference",
}


def _database(root: Path) -> Path:
    resolved = root.resolve()
    db = resolved / "data" / "project.sqlite"
    require(
        db.is_file() and not db.is_symlink(),
        "Project database is missing or unsafe",
        "NOT_FOUND",
    )
    return db


def _connect(db: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(db, isolation_level=None, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection
    except sqlite3.DatabaseError as exc:
        raise EvidenceError(
            "INTEGRITY_FAILURE",
            "Project database could not be opened",
            "Restore a verified backup before retrying migration.",
        ) from exc


def inspect_schema(root: Path) -> dict[str, Any]:
    """Read migration compatibility without modifying the project."""
    db = _database(root)
    connection = _connect(db)
    try:
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        except sqlite3.DatabaseError as exc:
            raise EvidenceError(
                "INTEGRITY_FAILURE",
                "Project database failed integrity inspection",
                "Restore a verified backup before migrating.",
            ) from exc
        missing = sorted(LEGACY_REQUIRED_TABLES - tables)
        if version > SCHEMA_VERSION:
            compatibility = "future_unsupported"
        elif version == SCHEMA_VERSION:
            compatibility = "current"
        elif version in {0, 1} and not missing:
            compatibility = "upgrade_available"
        else:
            compatibility = "unsupported_legacy"
        return {
            "current_version": version,
            "target_version": SCHEMA_VERSION,
            "compatibility": compatibility,
            "integrity": integrity,
            "missing_required_tables": missing,
            "migration_path": list(range(version + 1, SCHEMA_VERSION + 1))
            if compatibility == "upgrade_available"
            else [],
            "writes": 0,
        }
    finally:
        connection.close()


def _backup(connection: sqlite3.Connection, db: Path, from_version: int) -> Path:
    backup_dir = db.parent / "migration_backups"
    backup_dir.mkdir(exist_ok=True)
    require(
        backup_dir.is_dir() and not backup_dir.is_symlink(),
        "Migration backup directory is unsafe",
        "INTEGRITY_FAILURE",
    )
    snapshot = backup_dir / f"pre-v{SCHEMA_VERSION}-from-v{from_version}-{new_id()}.sqlite"
    target = sqlite3.connect(snapshot)
    try:
        connection.backup(target)
    finally:
        target.close()
    require(
        snapshot.is_file() and snapshot.stat().st_size > 0,
        "Migration backup was empty",
        "INTEGRITY_FAILURE",
    )
    verifier = sqlite3.connect(snapshot)
    try:
        require(
            verifier.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
            "Migration backup failed integrity verification",
            "INTEGRITY_FAILURE",
        )
    finally:
        verifier.close()
    return snapshot


def migrate_project(
    root: Path,
    *,
    failure_hook: MigrationHook | None = None,
) -> dict[str, Any]:
    """Upgrade schema 0/1 projects to the current version in one transaction."""
    preview = inspect_schema(root)
    current = int(preview["current_version"])
    if preview["compatibility"] == "current":
        return {
            **preview,
            "changed": False,
            "backup": None,
            "installed_versions": [],
        }
    require(
        preview["compatibility"] == "upgrade_available",
        "Project schema cannot be migrated by this version",
        "SCHEMA_MISMATCH",
    )
    require(
        preview["integrity"] == "ok",
        "Project database is corrupt",
        "INTEGRITY_FAILURE",
    )
    db = _database(root)
    connection = _connect(db)
    snapshot = _backup(connection, db, current)
    installed: list[int] = []
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if current == 0:
                for statement in _schema_statements(V0_TO_V1):
                    connection.execute(statement)
                connection.execute(
                    "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (?,?)",
                    (1, now_utc()),
                )
                connection.execute("PRAGMA user_version=1")
                installed.append(1)
                if failure_hook is not None:
                    failure_hook(1, connection)
            if current <= 1:
                for statement in _schema_statements(REVIEW_SCHEMA_V2):
                    connection.execute(statement)
                connection.execute(
                    "INSERT OR IGNORE INTO migrations(version,installed_at) VALUES (?,?)",
                    (2, now_utc()),
                )
                connection.execute("PRAGMA user_version=2")
                installed.append(2)
                if failure_hook is not None:
                    failure_hook(2, connection)
            require(
                connection.execute("PRAGMA foreign_key_check").fetchone() is None,
                "Migration introduced foreign-key violations",
                "INTEGRITY_FAILURE",
            )
            require(
                connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                "Migration damaged database integrity",
                "INTEGRITY_FAILURE",
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    except sqlite3.DatabaseError as exc:
        raise EvidenceError(
            "MIGRATION_FAILED",
            "SQLite rejected the schema migration",
            "Inspect the preserved pre-migration backup and database integrity.",
        ) from exc
    finally:
        connection.close()
    verification = inspect_schema(root)
    require(
        verification["compatibility"] == "current" and verification["integrity"] == "ok",
        "Migrated database did not verify",
        "INTEGRITY_FAILURE",
    )
    return {
        "from_version": current,
        "to_version": SCHEMA_VERSION,
        "changed": True,
        "backup": str(snapshot),
        "installed_versions": installed,
        "integrity": verification["integrity"],
        "missing_required_tables": verification["missing_required_tables"],
    }
