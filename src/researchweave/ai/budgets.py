"""Durable per-project model-call budgets and privacy-safe usage summaries.

Estimated tokens are admission controls, not tokenizer-exact counts. Charges
only use provider-reported usage where present; unknown cost stays unknown.
"""

from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import AIError


@dataclass(frozen=True)
class Budget:
    project_id: str
    max_requests: int
    max_tokens: int
    max_reserved_tokens: int


@dataclass(frozen=True)
class Reservation:
    identifier: str
    project_id: str
    token_limit: int


@dataclass(frozen=True)
class UsageSummary:
    project_id: str
    requests_completed: int
    tokens_used: int
    tokens_reserved: int
    requests_pending: int
    requests_failed: int
    monetary_cost_known: bool


class BudgetStore:
    """SQLite reservations ensure agent plans cannot oversubscribe token budgets.

    The host must issue a reservation *before* calling the provider. Each
    terminal request closes its reservation exactly once. Interrupted calls
    remain reserved until explicitly reconciled with provider receipts.
    """

    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS budgets ("
            "project TEXT PRIMARY KEY, max_requests INTEGER NOT NULL, "
            "max_tokens INTEGER NOT NULL, max_reserved_tokens INTEGER NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS calls ("
            "id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES budgets(project), "
            "token_limit INTEGER NOT NULL, token_used INTEGER, "
            "state TEXT NOT NULL CHECK(state IN ('reserved','complete','failed')), "
            "CHECK(token_used IS NULL OR token_used >= 0))"
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS calls_project ON calls(project)")

    def configure(self, budget: Budget) -> None:
        if not budget.project_id or len(budget.project_id) > 256:
            raise AIError("INVALID_INPUT", "Invalid project ID")
        if not 1 <= budget.max_requests <= 1_000_000:
            raise AIError("INVALID_INPUT", "Invalid maximum model-call count")
        if not 1 <= budget.max_tokens <= 1_000_000_000:
            raise AIError("INVALID_INPUT", "Invalid maximum total tokens")
        if not 1 <= budget.max_reserved_tokens <= budget.max_tokens:
            raise AIError("INVALID_INPUT", "Invalid concurrent token budget")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute(
                "SELECT 1 FROM calls WHERE project=? LIMIT 1", (budget.project_id,)
            ).fetchone():
                raise AIError("CONFLICT", "Budget cannot change after calls are recorded")
            self.db.execute(
                "INSERT INTO budgets VALUES(?,?,?,?) "
                "ON CONFLICT(project) DO UPDATE SET "
                "max_requests=excluded.max_requests,max_tokens=excluded.max_tokens,"
                "max_reserved_tokens=excluded.max_reserved_tokens",
                (
                    budget.project_id,
                    budget.max_requests,
                    budget.max_tokens,
                    budget.max_reserved_tokens,
                ),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _aggregates(self, project_id: str) -> tuple[int, int, int, int, int]:
        row = self.db.execute(
            "SELECT COUNT(*), "
            "COALESCE(SUM(CASE WHEN state='complete' THEN token_used ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN state='reserved' THEN token_limit ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN state='reserved' THEN 1 ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN state='failed' THEN 1 ELSE 0 END),0) "
            "FROM calls WHERE project=?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise AIError("INTERNAL_ERROR", "Unable to read model usage")
        return tuple(int(v) for v in row)  # type: ignore[return-value]

    def reserve(self, project_id: str, token_limit: int) -> Reservation:
        if not 1 <= token_limit <= 1_000_000:
            raise AIError("INVALID_INPUT", "Request token budget must be bounded")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            budget = self.db.execute(
                "SELECT max_requests,max_tokens,max_reserved_tokens FROM budgets WHERE project=?",
                (project_id,),
            ).fetchone()
            if budget is None:
                raise AIError("NOT_FOUND", "No model budget configured for project")
            calls, used, reserved, _, _ = self._aggregates(project_id)
            if calls + 1 > budget[0] or used + reserved + token_limit > budget[1]:
                raise AIError("RESOURCE_LIMIT", "Project total model budget exhausted")
            if reserved + token_limit > budget[2]:
                raise AIError("RESOURCE_LIMIT", "Concurrent token reservation budget exceeded")
            identifier = str(uuid.uuid4())
            self.db.execute(
                "INSERT INTO calls (id,project,token_limit,state) VALUES(?,?,?,'reserved')",
                (identifier, project_id, token_limit),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return Reservation(identifier, project_id, token_limit)

    def close_reservation(
        self, reservation: Reservation, *, actual_tokens: int | None, failed: bool = False
    ) -> None:
        if actual_tokens is not None and (
            type(actual_tokens) is not int or not 0 <= actual_tokens <= reservation.token_limit
        ):
            raise AIError("INVALID_INPUT", "Actual usage must fit the reserved request budget")
        if not failed and actual_tokens is None:
            raise AIError("INVALID_INPUT", "Successful calls require observed token count")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT project,token_limit,state FROM calls WHERE id=?",
                (reservation.identifier,),
            ).fetchone()
            if row is None or row[0] != reservation.project_id or row[1] != reservation.token_limit:
                raise AIError("PERMISSION_DENIED", "Reservation identity does not match")
            if row[2] != "reserved":
                raise AIError("CONFLICT", "Reservation was already finalized")
            self.db.execute(
                "UPDATE calls SET state=?,token_used=? WHERE id=?",
                ("failed" if failed else "complete", actual_tokens, reservation.identifier),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def summary(self, project_id: str) -> UsageSummary:
        if not self.db.execute("SELECT 1 FROM budgets WHERE project=?", (project_id,)).fetchone():
            raise AIError("NOT_FOUND", "Project budget does not exist")
        calls, used, reserved, pending, failed = self._aggregates(project_id)
        return UsageSummary(
            project_id=project_id,
            requests_completed=calls - pending - failed,
            tokens_used=used,
            tokens_reserved=reserved,
            requests_pending=pending,
            requests_failed=failed,
            monetary_cost_known=False,
        )

    @staticmethod
    def admission_estimate(prompt: str, max_output_tokens: int) -> int:
        """A conservative heuristic, explicitly distinct from tokenization."""
        if not prompt or len(prompt) > 100_000 or not 1 <= max_output_tokens <= 4096:
            raise AIError("INVALID_INPUT", "Model request exceeds admission limits")
        return math.ceil(len(prompt.encode("utf-8")) / 2) + max_output_tokens

    def close(self) -> None:
        self.db.close()
