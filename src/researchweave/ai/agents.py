from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import AIError
from .policy import Approval, ApprovalIssuer, canonical_digest

Handler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Capability:
    operation: str
    effect: str
    handler: Handler
    description: str


class AgentRuntime:
    """Allowlisted, durable executor. Tool output never grants tool authority."""

    def __init__(self, database: Path, issuer: ApprovalIssuer | None = None) -> None:
        self.db = sqlite3.connect(database)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS plans ("
            "id TEXT PRIMARY KEY, project TEXT NOT NULL, "
            "state TEXT NOT NULL, steps TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS receipts ("
            "id TEXT PRIMARY KEY, plan TEXT NOT NULL, step INTEGER NOT NULL, "
            "status TEXT NOT NULL, data TEXT NOT NULL, created TEXT NOT NULL, "
            "UNIQUE(plan,step))"
        )
        self.db.commit()
        self.issuer = issuer
        self.capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if capability.effect not in {"read", "local-write", "external-network", "code-execution"}:
            raise AIError("INVALID_INPUT", "Unknown effect classification")
        if capability.operation in self.capabilities:
            raise AIError("CONFLICT", "Duplicate capability")
        self.capabilities[capability.operation] = capability

    def create_plan(self, project: str, steps: list[dict[str, Any]]) -> str:
        if not project or not 1 <= len(steps) <= 100:
            raise AIError("INVALID_INPUT", "Project and bounded steps required")
        for step in steps:
            if (
                set(step) != {"operation", "arguments"}
                or step["operation"] not in self.capabilities
                or not isinstance(step["arguments"], dict)
            ):
                raise AIError("INVALID_INPUT", "Unknown operation or invalid step arguments")
        identifier = str(uuid.uuid4())
        with self.db:
            self.db.execute(
                "INSERT INTO plans VALUES(?,?,?,?)",
                (identifier, project, "ready", json.dumps(steps)),
            )
        return identifier

    def inspect(self, plan_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT project,state,steps FROM plans WHERE id=?", (plan_id,)
        ).fetchone()
        if row is None:
            raise AIError("NOT_FOUND", "Plan does not exist")
        return {"id": plan_id, "project": row[0], "state": row[1], "steps": json.loads(row[2])}

    def preview(self, plan_id: str, step_number: int) -> dict[str, Any]:
        plan = self.inspect(plan_id)
        try:
            step = plan["steps"][step_number]
        except IndexError as exc:
            raise AIError("NOT_FOUND", "Step does not exist") from exc
        capability = self.capabilities[step["operation"]]
        return {
            "operation": capability.operation,
            "effect": capability.effect,
            "arguments_digest": canonical_digest(step["arguments"]),
            "approval_required": capability.effect != "read",
            "description": capability.description,
        }

    def execute(
        self, plan_id: str, step_number: int, approval: Approval | None = None
    ) -> dict[str, Any]:
        plan = self.inspect(plan_id)
        if plan["state"] == "cancelled":
            raise AIError("CANCELLED", "Plan was cancelled")
        if not 0 <= step_number < len(plan["steps"]):
            raise AIError("NOT_FOUND", "Step does not exist")
        if step_number:
            prior = self.db.execute(
                "SELECT status FROM receipts WHERE plan=? AND step=?", (plan_id, step_number - 1)
            ).fetchone()
            if prior is None or prior[0] != "ok":
                raise AIError("CONFLICT", "Earlier step must finish first")
        existing = self.db.execute(
            "SELECT data FROM receipts WHERE plan=? AND step=?", (plan_id, step_number)
        ).fetchone()
        if existing:
            loaded = json.loads(existing[0])
            if not isinstance(loaded, dict):
                raise AIError("INTEGRITY_FAILURE", "Saved operation receipt is malformed")
            return loaded
        step = plan["steps"][step_number]
        capability = self.capabilities[step["operation"]]
        if capability.effect != "read":
            if self.issuer is None:
                raise AIError("NEEDS_APPROVAL", "Trusted host issuer not configured")
            self.issuer.verify(approval, plan["project"], capability.operation, step["arguments"])
        result = capability.handler(dict(step["arguments"]))
        if not isinstance(result, dict):
            raise AIError("SCHEMA_MISMATCH", "Handler must return an object")
        receipt = {
            "operation": capability.operation,
            "status": "ok",
            "result": result,
            "arguments_digest": canonical_digest(step["arguments"]),
        }
        with self.db:
            self.db.execute(
                "INSERT INTO receipts VALUES(?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    plan_id,
                    step_number,
                    "ok",
                    json.dumps(receipt),
                    datetime.now(UTC).isoformat(),
                ),
            )
            if step_number == len(plan["steps"]) - 1:
                self.db.execute("UPDATE plans SET state='complete' WHERE id=?", (plan_id,))
        return receipt

    def cancel(self, plan_id: str) -> None:
        self.inspect(plan_id)
        with self.db:
            self.db.execute("UPDATE plans SET state='cancelled' WHERE id=?", (plan_id,))

    def close(self) -> None:
        self.db.close()
