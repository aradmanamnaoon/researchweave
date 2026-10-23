from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import AIError
from .policy import EgressPolicy
from .retrieval_security import PromptInjectionFirewall

JobHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    retryable_codes: frozenset[str] = frozenset(
        {"TIMEOUT", "RATE_LIMITED", "SERVICE_UNAVAILABLE", "TRANSIENT_FAILURE"}
    )

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 20:
            raise AIError("INVALID_INPUT", "max_attempts must be between 1 and 20")


@dataclass(frozen=True)
class JobDefinition:
    name: str
    handler: JobHandler
    retry_policy: RetryPolicy
    idempotent: bool = True


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    name: str
    state: str
    attempts: int
    checkpoint: dict[str, Any] | None
    result: dict[str, Any] | None
    error_code: str | None


class LongTaskOrchestrator:
    """Durable bounded job runner with cancellation and dead-letter recovery."""

    def __init__(self, database: Path) -> None:
        self.db = sqlite3.connect(database, timeout=5)
        self.db.execute("PRAGMA busy_timeout=5000")
        self.definitions: dict[str, JobDefinition] = {}
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS long_jobs ("
                "id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL, "
                "arguments_json TEXT NOT NULL, attempts INTEGER NOT NULL, "
                "checkpoint_json TEXT, result_json TEXT, error_code TEXT, "
                "cancel_requested INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS job_events ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, "
                "event TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def register(self, definition: JobDefinition) -> None:
        if not definition.name or definition.name in self.definitions:
            raise AIError("CONFLICT", "Job definition is empty or already registered")
        self.definitions[definition.name] = definition

    @staticmethod
    def _encode(value: Mapping[str, Any]) -> str:
        try:
            return json.dumps(
                dict(value),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        except (TypeError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Job data must be JSON serializable") from exc

    @staticmethod
    def _decode(value: str | None) -> dict[str, Any] | None:
        if value is None:
            return None
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise AIError("INTEGRITY_FAILURE", "Stored job payload is malformed")
        return dict(decoded)

    def _event(self, job_id: str, event: str, detail: Mapping[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO job_events(job_id,event,detail_json,created_at) VALUES(?,?,?,?)",
            (job_id, event, self._encode(detail), datetime.now(UTC).isoformat()),
        )

    def submit(self, name: str, arguments: Mapping[str, Any]) -> str:
        if name not in self.definitions:
            raise AIError("NOT_FOUND", "Unknown job definition")
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        encoded = self._encode(arguments)
        with self.db:
            self.db.execute(
                "INSERT INTO long_jobs(id,name,state,arguments_json,attempts,created_at,updated_at) "
                "VALUES(?,?,?,?,0,?,?)",
                (job_id, name, "queued", encoded, now, now),
            )
            self._event(job_id, "submitted", {"name": name})
        return job_id

    def snapshot(self, job_id: str) -> JobSnapshot:
        row = self.db.execute(
            "SELECT name,state,attempts,checkpoint_json,result_json,error_code "
            "FROM long_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise AIError("NOT_FOUND", "Job does not exist")
        return JobSnapshot(
            job_id=job_id,
            name=str(row[0]),
            state=str(row[1]),
            attempts=int(row[2]),
            checkpoint=self._decode(None if row[3] is None else str(row[3])),
            result=self._decode(None if row[4] is None else str(row[4])),
            error_code=None if row[5] is None else str(row[5]),
        )

    def request_cancel(self, job_id: str) -> None:
        snapshot = self.snapshot(job_id)
        if snapshot.state in {"completed", "cancelled", "dead-letter"}:
            return
        with self.db:
            self.db.execute(
                "UPDATE long_jobs SET cancel_requested=1,updated_at=? WHERE id=?",
                (datetime.now(UTC).isoformat(), job_id),
            )
            self._event(job_id, "cancel-requested", {})

    def checkpoint(self, job_id: str, checkpoint: Mapping[str, Any]) -> None:
        snapshot = self.snapshot(job_id)
        if snapshot.state not in {"running", "paused"}:
            raise AIError("CONFLICT", "Checkpoint allowed only for active jobs")
        encoded = self._encode(checkpoint)
        with self.db:
            self.db.execute(
                "UPDATE long_jobs SET checkpoint_json=?,updated_at=? WHERE id=?",
                (encoded, datetime.now(UTC).isoformat(), job_id),
            )
            self._event(job_id, "checkpoint", {"keys": sorted(checkpoint)})

    def run_once(self, job_id: str) -> JobSnapshot:
        row = self.db.execute(
            "SELECT name,state,arguments_json,attempts,cancel_requested FROM long_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise AIError("NOT_FOUND", "Job does not exist")
        name, state, arguments_json, attempts, cancel_requested = row
        if state in {"completed", "cancelled", "dead-letter"}:
            return self.snapshot(job_id)
        definition = self.definitions.get(str(name))
        if definition is None:
            raise AIError("NOT_FOUND", "Registered job definition is unavailable after restart")
        if bool(cancel_requested):
            with self.db:
                self.db.execute(
                    "UPDATE long_jobs SET state='cancelled',updated_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), job_id),
                )
                self._event(job_id, "cancelled", {})
            return self.snapshot(job_id)
        if state == "running" and not definition.idempotent:
            with self.db:
                self.db.execute(
                    "UPDATE long_jobs SET state='dead-letter',error_code='RECOVERY_REQUIRED',"
                    "updated_at=? WHERE id=?",
                    (datetime.now(UTC).isoformat(), job_id),
                )
                self._event(
                    job_id,
                    "dead-letter",
                    {"reason": "uncertain non-idempotent prior execution"},
                )
            return self.snapshot(job_id)
        next_attempt = int(attempts) + 1
        with self.db:
            self.db.execute(
                "UPDATE long_jobs SET state='running',attempts=?,error_code=NULL,updated_at=? "
                "WHERE id=?",
                (next_attempt, datetime.now(UTC).isoformat(), job_id),
            )
            self._event(job_id, "attempt-started", {"attempt": next_attempt})
        arguments = self._decode(str(arguments_json))
        if arguments is None:
            raise AIError("INTEGRITY_FAILURE", "Job arguments are missing")
        try:
            result = dict(definition.handler(arguments))
        except AIError as exc:
            retryable = (
                exc.code in definition.retry_policy.retryable_codes
                and next_attempt < definition.retry_policy.max_attempts
            )
            terminal_state = "queued" if retryable else "dead-letter"
            with self.db:
                self.db.execute(
                    "UPDATE long_jobs SET state=?,error_code=?,updated_at=? WHERE id=?",
                    (terminal_state, exc.code, datetime.now(UTC).isoformat(), job_id),
                )
                self._event(
                    job_id,
                    "attempt-failed",
                    {
                        "attempt": next_attempt,
                        "error_code": exc.code,
                        "retryable": retryable,
                    },
                )
            return self.snapshot(job_id)
        encoded_result = self._encode(result)
        with self.db:
            cancel_now = bool(
                self.db.execute(
                    "SELECT cancel_requested FROM long_jobs WHERE id=?",
                    (job_id,),
                ).fetchone()[0]
            )
            if cancel_now:
                self.db.execute(
                    "UPDATE long_jobs SET state='cancelled',result_json=NULL,updated_at=? "
                    "WHERE id=?",
                    (datetime.now(UTC).isoformat(), job_id),
                )
                self._event(job_id, "cancelled-after-handler", {})
            else:
                self.db.execute(
                    "UPDATE long_jobs SET state='completed',result_json=?,error_code=NULL,"
                    "updated_at=? WHERE id=?",
                    (encoded_result, datetime.now(UTC).isoformat(), job_id),
                )
                self._event(job_id, "completed", {"attempt": next_attempt})
        return self.snapshot(job_id)

    def events(self, job_id: str) -> list[dict[str, Any]]:
        self.snapshot(job_id)
        return [
            {
                "sequence": int(sequence),
                "event": str(event),
                "detail": self._decode(str(detail_json)) or {},
                "created_at": str(created_at),
            }
            for sequence, event, detail_json, created_at in self.db.execute(
                "SELECT sequence,event,detail_json,created_at FROM job_events "
                "WHERE job_id=? ORDER BY sequence",
                (job_id,),
            )
        ]

    def close(self) -> None:
        self.db.close()


@dataclass(frozen=True)
class SimulationTool:
    operation: str
    effect: str
    response: Mapping[str, Any]


class OfflineSimulationRunner:
    """Execute a deterministic synthetic tool trajectory without filesystem/network effects."""

    def __init__(self, tools: Sequence[SimulationTool]) -> None:
        self.tools = {tool.operation: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise AIError("CONFLICT", "Duplicate simulation tool")

    def run(self, steps: Sequence[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
        if len(steps) > 500:
            raise AIError("RESOURCE_LIMIT", "Simulation has too many steps")
        trace: list[dict[str, Any]] = []
        for index, (operation, arguments) in enumerate(steps):
            tool = self.tools.get(operation)
            if tool is None:
                raise AIError("NOT_FOUND", f"Simulation tool not found: {operation}")
            trace.append(
                {
                    "index": index,
                    "operation": operation,
                    "effect": tool.effect,
                    "arguments": dict(arguments),
                    "response": dict(tool.response),
                }
            )
        return {
            "mode": "offline-simulation",
            "network_calls": 0,
            "filesystem_writes": 0,
            "trace": trace,
        }


@dataclass(frozen=True)
class SecurityCase:
    name: str
    content: str
    proposed_endpoint: str | None = None
    proposed_effect: str = "read"


@dataclass(frozen=True)
class SecurityCaseResult:
    name: str
    passed: bool
    blocked_reason: str | None
    findings: tuple[str, ...]


class AgentSecurityRegressionHarness:
    """Exercise untrusted content against firewall and transport-level egress policy."""

    def __init__(
        self,
        *,
        policy: EgressPolicy,
        firewall: PromptInjectionFirewall | None = None,
    ) -> None:
        self.policy = policy
        self.firewall = firewall or PromptInjectionFirewall()

    def run_case(self, case: SecurityCase) -> SecurityCaseResult:
        findings = self.firewall.inspect(case.content)
        finding_names = tuple(item.category for item in findings)
        try:
            if case.proposed_effect in {
                "external-network",
                "sensitive-egress",
                "code-execution",
                "irreversible",
            }:
                self.firewall.guard_external_action(case.content)
            if case.proposed_endpoint is not None:
                self.policy.permit(case.proposed_endpoint, local=False)
        except AIError as exc:
            return SecurityCaseResult(
                name=case.name,
                passed=True,
                blocked_reason=exc.code,
                findings=finding_names,
            )
        dangerous = (
            case.proposed_effect
            in {
                "external-network",
                "sensitive-egress",
                "code-execution",
                "irreversible",
            }
            or case.proposed_endpoint is not None
        )
        return SecurityCaseResult(
            name=case.name,
            passed=not dangerous,
            blocked_reason=None,
            findings=finding_names,
        )

    def run_suite(self, cases: Sequence[SecurityCase]) -> dict[str, Any]:
        results = [self.run_case(case) for case in cases]
        return {
            "total": len(results),
            "passed": sum(item.passed for item in results),
            "failed": [item.name for item in results if not item.passed],
            "results": [
                {
                    "name": item.name,
                    "passed": item.passed,
                    "blocked_reason": item.blocked_reason,
                    "findings": list(item.findings),
                }
                for item in results
            ],
        }
