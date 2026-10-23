"""Local append-only, tamper-evident event journal with payload redaction."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import AIError
from .policy import canonical_digest


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    project_id: str
    operation: str
    effect: str
    status: str
    arguments_digest: str
    result_digest: str
    previous_signature: str
    signature: str


class AuditJournal:
    """Host-keyed journal verifies both content and event ordering.

    It intentionally contains no prompt, source quotation, credential or model
    response bytes. Integrity is HMAC-based and detects local modifications
    when the host keeps its signing secret outside the project directory.
    """

    def __init__(self, database: Path, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise AIError("INVALID_INPUT", "Host audit key must contain at least 32 bytes")
        self._key = signing_key
        self.db = sqlite3.connect(database, isolation_level=None, timeout=5)
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS audit ("
            "sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL, "
            "previous_signature TEXT NOT NULL, signature TEXT NOT NULL)"
        )

    def _sign(self, previous: str, payload: str) -> str:
        return hmac.new(
            self._key, (previous + "\n" + payload).encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _safe_payload(
        project_id: str,
        operation: str,
        effect: str,
        status: str,
        arguments: Mapping[str, Any],
        result: Any,
        timestamp: str,
    ) -> dict[str, str]:
        if not project_id or len(project_id) > 256 or not operation or len(operation) > 128:
            raise AIError("INVALID_INPUT", "Audit scope is invalid")
        if effect not in {
            "read",
            "local-write",
            "external-network",
            "sensitive-egress",
            "code-execution",
            "irreversible",
        }:
            raise AIError("INVALID_INPUT", "Invalid audited effect")
        if status not in {"proposed", "approved", "denied", "started", "ok", "failed"}:
            raise AIError("INVALID_INPUT", "Invalid audit state")
        try:
            argument_hash = canonical_digest(dict(arguments))
            result_hash = canonical_digest(result)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Audit values are not canonical JSON") from exc
        return {
            "timestamp": timestamp,
            "project_id": project_id,
            "operation": operation,
            "effect": effect,
            "status": status,
            "arguments_digest": argument_hash,
            "result_digest": result_hash,
        }

    def append(
        self,
        project_id: str,
        operation: str,
        effect: str,
        status: str,
        arguments: Mapping[str, Any],
        result: Any,
    ) -> AuditEvent:
        payload_dict = self._safe_payload(
            project_id,
            operation,
            effect,
            status,
            arguments,
            result,
            datetime.now(UTC).isoformat(),
        )
        payload = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.db.execute(
                "SELECT sequence,signature FROM audit ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = (previous[0] + 1) if previous else 1
            previous_signature = previous[1] if previous else "0" * 64
            signature = self._sign(previous_signature, payload)
            self.db.execute(
                "INSERT INTO audit(sequence,payload,previous_signature,signature) VALUES(?,?,?,?)",
                (sequence, payload, previous_signature, signature),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return AuditEvent(
            sequence, **payload_dict, previous_signature=previous_signature, signature=signature
        )

    def verify(self) -> int:
        last = "0" * 64
        expected_sequence = 1
        rows = self.db.execute(
            "SELECT sequence,payload,previous_signature,signature FROM audit ORDER BY sequence"
        )
        for sequence, payload, previous_signature, signature in rows:
            if sequence != expected_sequence or previous_signature != last:
                raise AIError("INTEGRITY_FAILURE", "Audit ordering or chain is broken")
            if not hmac.compare_digest(self._sign(last, payload), signature):
                raise AIError("INTEGRITY_FAILURE", "Audit record authentication failed")
            try:
                decoded = json.loads(payload)
                if not isinstance(decoded, dict) or set(decoded) != {
                    "timestamp",
                    "project_id",
                    "operation",
                    "effect",
                    "status",
                    "arguments_digest",
                    "result_digest",
                }:
                    raise ValueError("Invalid audit payload")
            except (TypeError, ValueError) as exc:
                raise AIError("INTEGRITY_FAILURE", "Malformed authenticated audit data") from exc
            last = signature
            expected_sequence += 1
        return expected_sequence - 1

    def export_redacted(self, *, limit: int = 500) -> list[dict[str, Any]]:
        if not 1 <= limit <= 10000:
            raise AIError("INVALID_INPUT", "Invalid audit view limit")
        self.verify()
        return [
            {"sequence": sequence, **json.loads(payload), "signature": signature}
            for sequence, payload, signature in self.db.execute(
                "SELECT sequence,payload,signature FROM audit ORDER BY sequence DESC LIMIT ?",
                (limit,),
            )
        ]

    def close(self) -> None:
        self.db.close()
