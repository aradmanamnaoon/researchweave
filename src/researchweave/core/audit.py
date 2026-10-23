"""Privacy-preserving durable audit metadata for integration operations."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import OperationRequest, digest


class AuditStore:
    """Append operation metadata and content hashes without storing argument payloads."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS operation_audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                request_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                operation TEXT NOT NULL,
                effect TEXT NOT NULL,
                preview INTEGER NOT NULL,
                status TEXT NOT NULL,
                input_sha256 TEXT NOT NULL,
                output_sha256 TEXT NOT NULL,
                error_code TEXT
            )
            """
        )
        self._connection.commit()

    def append(
        self,
        request: OperationRequest,
        *,
        effect: str,
        result: dict[str, Any],
    ) -> int:
        error = result.get("error")
        error_code = (
            str(error.get("code")) if isinstance(error, dict) and error.get("code") else None
        )
        cursor = self._connection.execute(
            """
            INSERT INTO operation_audit (
                recorded_at, request_id, project_id, actor, operation, effect, preview,
                status, input_sha256, output_sha256, error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                str(request.request_id),
                str(request.project_id),
                request.actor,
                request.operation,
                effect,
                int(request.preview),
                str(result.get("status", "failed")),
                digest(request.approval_payload()),
                digest(result),
                error_code,
            ),
        )
        self._connection.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Audit insert did not return a sequence")
        return int(cursor.lastrowid)

    def events(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT sequence, recorded_at, request_id, project_id, actor, operation,
                      effect, preview, status, input_sha256, output_sha256, error_code
               FROM operation_audit ORDER BY sequence"""
        ).fetchall()
        keys = (
            "sequence",
            "recorded_at",
            "request_id",
            "project_id",
            "actor",
            "operation",
            "effect",
            "preview",
            "status",
            "input_sha256",
            "output_sha256",
            "error_code",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def close(self) -> None:
        self._connection.close()
