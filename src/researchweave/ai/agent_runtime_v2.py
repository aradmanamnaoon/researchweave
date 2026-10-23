from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import AIError
from .policy import Approval, ApprovalIssuer, canonical_digest

JsonDict = dict[str, Any]
StepHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class ToolContract:
    operation: str
    effect: str
    handler: StepHandler
    reversible: bool
    idempotent: bool
    allowed_arguments: frozenset[str]

    def validate_arguments(self, arguments: Mapping[str, Any]) -> JsonDict:
        if not isinstance(arguments, Mapping):
            raise AIError("INVALID_INPUT", "Tool arguments must be an object")
        unknown = set(arguments) - self.allowed_arguments
        if unknown:
            raise AIError(
                "INVALID_INPUT",
                f"Tool {self.operation} received unknown arguments: {sorted(unknown)}",
            )
        return dict(arguments)


@dataclass(frozen=True)
class AgentStep:
    step_id: str
    operation: str
    arguments: JsonDict
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentPlan:
    plan_id: str
    project_id: str
    revision: int
    state: str
    steps: tuple[AgentStep, ...]


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    plan_id: str
    step_id: str | None
    event_type: str
    payload_digest: str
    created_at: str


class DurableAgentRuntime:
    """Crash-resumable plan executor with exact approval scope and idempotency.

    Side effects are protected by a durable intent record written before the
    handler is called. Non-idempotent operations never auto-replay after a crash:
    a host must explicitly resolve the uncertain intent.
    """

    _VALID_EFFECTS = {
        "read",
        "local-write",
        "external-network",
        "sensitive-egress",
        "code-execution",
        "irreversible",
    }

    def __init__(self, database: Path, issuer: ApprovalIssuer | None = None) -> None:
        self.db = sqlite3.connect(database, timeout=5)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.issuer = issuer
        self.tools: dict[str, ToolContract] = {}
        self._init_schema()

    def _init_schema(self) -> None:
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS agent_plans ("
                "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL, "
                "state TEXT NOT NULL, steps_json TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS agent_step_state ("
                "plan_id TEXT NOT NULL REFERENCES agent_plans(id) ON DELETE CASCADE, "
                "step_id TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
                "intent_digest TEXT, result_json TEXT, error_code TEXT, "
                "updated_at TEXT NOT NULL, PRIMARY KEY(plan_id, step_id))"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS agent_events ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL, "
                "step_id TEXT, event_type TEXT NOT NULL, payload_digest TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )

    def register_tool(self, contract: ToolContract) -> None:
        if contract.effect not in self._VALID_EFFECTS:
            raise AIError("INVALID_INPUT", "Unknown tool effect")
        if not contract.operation or contract.operation in self.tools:
            raise AIError("CONFLICT", "Tool operation is empty or already registered")
        self.tools[contract.operation] = contract

    @staticmethod
    def _serialize_steps(steps: Sequence[AgentStep]) -> str:
        return json.dumps(
            [
                {
                    "step_id": item.step_id,
                    "operation": item.operation,
                    "arguments": item.arguments,
                    "dependencies": list(item.dependencies),
                }
                for item in steps
            ],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_steps(raw: str) -> tuple[AgentStep, ...]:
        decoded = json.loads(raw)
        if not isinstance(decoded, list):
            raise AIError("INTEGRITY_FAILURE", "Stored plan steps are malformed")
        steps: list[AgentStep] = []
        for item in decoded:
            if not isinstance(item, dict):
                raise AIError("INTEGRITY_FAILURE", "Stored plan step is malformed")
            steps.append(
                AgentStep(
                    step_id=str(item["step_id"]),
                    operation=str(item["operation"]),
                    arguments=dict(item["arguments"]),
                    dependencies=tuple(str(value) for value in item["dependencies"]),
                )
            )
        return tuple(steps)

    def _validate_graph(self, steps: Sequence[AgentStep]) -> None:
        if not 1 <= len(steps) <= 500:
            raise AIError("RESOURCE_LIMIT", "Plans require 1-500 steps")
        by_id = {step.step_id: step for step in steps}
        if len(by_id) != len(steps) or any(not step.step_id for step in steps):
            raise AIError("INVALID_INPUT", "Step IDs must be unique and non-empty")
        for step in steps:
            contract = self.tools.get(step.operation)
            if contract is None:
                raise AIError("NOT_FOUND", f"Unknown tool: {step.operation}")
            contract.validate_arguments(step.arguments)
            if step.step_id in step.dependencies:
                raise AIError("INVALID_INPUT", "Step cannot depend on itself")
            if any(dep not in by_id for dep in step.dependencies):
                raise AIError("INVALID_INPUT", "Plan has a missing dependency")
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in permanent:
                return
            if step_id in temporary:
                raise AIError("INVALID_INPUT", "Plan dependency graph contains a cycle")
            temporary.add(step_id)
            for dependency in by_id[step_id].dependencies:
                visit(dependency)
            temporary.remove(step_id)
            permanent.add(step_id)

        for identifier in by_id:
            visit(identifier)

    def create_plan(self, project_id: str, steps: Sequence[AgentStep]) -> AgentPlan:
        if not project_id or len(project_id) > 256:
            raise AIError("INVALID_INPUT", "Invalid project ID")
        self._validate_graph(steps)
        plan_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self.db:
            self.db.execute(
                "INSERT INTO agent_plans(id,project_id,revision,state,steps_json,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (plan_id, project_id, 1, "ready", self._serialize_steps(steps), now),
            )
            self.db.executemany(
                "INSERT INTO agent_step_state(plan_id,step_id,state,updated_at) VALUES(?,?,?,?)",
                [(plan_id, step.step_id, "pending", now) for step in steps],
            )
            self._event(plan_id, None, "plan-created", {"revision": 1, "steps": len(steps)})
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: str) -> AgentPlan:
        row = self.db.execute(
            "SELECT project_id,revision,state,steps_json FROM agent_plans WHERE id=?",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise AIError("NOT_FOUND", "Plan does not exist")
        return AgentPlan(
            plan_id=plan_id,
            project_id=str(row[0]),
            revision=int(row[1]),
            state=str(row[2]),
            steps=self._deserialize_steps(str(row[3])),
        )

    def preview(self, plan_id: str) -> JsonDict:
        plan = self.get_plan(plan_id)
        steps = []
        for item in plan.steps:
            contract = self.tools[item.operation]
            steps.append(
                {
                    "step_id": item.step_id,
                    "operation": item.operation,
                    "effect": contract.effect,
                    "arguments_digest": canonical_digest(item.arguments),
                    "approval_required": contract.effect != "read",
                    "reversible": contract.reversible,
                    "idempotent": contract.idempotent,
                    "dependencies": list(item.dependencies),
                }
            )
        return {
            "plan_id": plan.plan_id,
            "project_id": plan.project_id,
            "revision": plan.revision,
            "state": plan.state,
            "steps": steps,
        }

    def revise_step(
        self,
        plan_id: str,
        step_id: str,
        arguments: Mapping[str, Any],
        *,
        expected_revision: int,
    ) -> AgentPlan:
        plan = self.get_plan(plan_id)
        if plan.revision != expected_revision:
            raise AIError("CONFLICT", "Plan revision changed")
        if plan.state not in {"ready", "paused"}:
            raise AIError("CONFLICT", "Plan cannot be edited in its current state")
        changed = False
        updated: list[AgentStep] = []
        for step in plan.steps:
            if step.step_id == step_id:
                validated = self.tools[step.operation].validate_arguments(arguments)
                updated.append(
                    AgentStep(step.step_id, step.operation, validated, step.dependencies)
                )
                changed = True
            else:
                updated.append(step)
        if not changed:
            raise AIError("NOT_FOUND", "Step does not exist")
        self._validate_graph(updated)
        now = datetime.now(UTC).isoformat()
        with self.db:
            cursor = self.db.execute(
                "UPDATE agent_plans SET revision=revision+1,steps_json=?,state='ready' "
                "WHERE id=? AND revision=?",
                (self._serialize_steps(updated), plan_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise AIError("CONFLICT", "Plan was modified concurrently")
            self.db.execute(
                "UPDATE agent_step_state SET state='pending',intent_digest=NULL,result_json=NULL,"
                "error_code=NULL,updated_at=? WHERE plan_id=? AND step_id=?",
                (now, plan_id, step_id),
            )
            self._event(
                plan_id,
                step_id,
                "human-correction",
                {"old_revision": expected_revision, "new_arguments": validated},
            )
        return self.get_plan(plan_id)

    def _event(
        self,
        plan_id: str,
        step_id: str | None,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        self.db.execute(
            "INSERT INTO agent_events(plan_id,step_id,event_type,payload_digest,created_at) "
            "VALUES(?,?,?,?,?)",
            (
                plan_id,
                step_id,
                event_type,
                canonical_digest(dict(payload)),
                datetime.now(UTC).isoformat(),
            ),
        )

    def _step(self, plan: AgentPlan, step_id: str) -> AgentStep:
        try:
            return next(step for step in plan.steps if step.step_id == step_id)
        except StopIteration as exc:
            raise AIError("NOT_FOUND", "Step does not exist") from exc

    def _dependency_states(self, plan_id: str, step: AgentStep) -> dict[str, str]:
        if not step.dependencies:
            return {}
        rows = self.db.execute(
            "SELECT step_id,state FROM agent_step_state WHERE plan_id=?",
            (plan_id,),
        ).fetchall()
        wanted = set(step.dependencies)
        return {
            str(step_id): str(state)
            for step_id, state in rows
            if str(step_id) in wanted
        }

    def execute_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        approval: Approval | None = None,
        allow_uncertain_retry: bool = False,
    ) -> Mapping[str, Any]:
        plan = self.get_plan(plan_id)
        if plan.state == "cancelled":
            raise AIError("CONFLICT", f"Plan is {plan.state}")
        step = self._step(plan, step_id)
        contract = self.tools[step.operation]
        dependencies = self._dependency_states(plan_id, step)
        if any(dependencies.get(dep) != "ok" for dep in step.dependencies):
            raise AIError("CONFLICT", "Dependencies must complete successfully first")
        row = self.db.execute(
            "SELECT state,intent_digest,result_json FROM agent_step_state "
            "WHERE plan_id=? AND step_id=?",
            (plan_id, step_id),
        ).fetchone()
        if row is None:
            raise AIError("INTEGRITY_FAILURE", "Step state is missing")
        state, prior_intent, prior_result = (
            None if value is None else str(value) for value in row
        )
        if state == "ok":
            if prior_result is None:
                raise AIError("INTEGRITY_FAILURE", "Completed step is missing result")
            decoded = json.loads(prior_result)
            if not isinstance(decoded, dict):
                raise AIError("INTEGRITY_FAILURE", "Completed step result is malformed")
            return decoded
        if plan.state == "completed":
            raise AIError("INTEGRITY_FAILURE", "Completed plan contains an unfinished step")
        if state == "cancelled":
            raise AIError("CANCELLED", "Step was cancelled")
        intent = canonical_digest(
            {
                "plan_id": plan.plan_id,
                "revision": plan.revision,
                "step_id": step.step_id,
                "operation": step.operation,
                "arguments": step.arguments,
            }
        )
        if state == "running" and prior_intent == intent:
            if not contract.idempotent and not allow_uncertain_retry:
                raise AIError(
                    "RECOVERY_REQUIRED",
                    "A previous non-idempotent attempt may have executed; "
                    "explicit recovery is required",
                )
        if contract.effect != "read":
            if self.issuer is None:
                raise AIError("NEEDS_APPROVAL", "Trusted host approval issuer is required")
            approval_args = {
                "plan_id": plan.plan_id,
                "plan_revision": plan.revision,
                "step_id": step.step_id,
                "operation": step.operation,
                "arguments": step.arguments,
            }
            self.issuer.verify(
                approval,
                plan.project_id,
                "agent.execute",
                approval_args,
            )
        now = datetime.now(UTC).isoformat()
        with self.db:
            self.db.execute(
                "UPDATE agent_step_state SET state='running',attempts=attempts+1,"
                "intent_digest=?,result_json=NULL,error_code=NULL,updated_at=? "
                "WHERE plan_id=? AND step_id=?",
                (intent, now, plan_id, step_id),
            )
            self.db.execute(
                "UPDATE agent_plans SET state='running' WHERE id=?",
                (plan_id,),
            )
            self._event(plan_id, step_id, "step-started", {"intent": intent})
        try:
            result = dict(contract.handler(step.arguments))
            encoded = json.dumps(
                result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
        except AIError as exc:
            with self.db:
                self.db.execute(
                    "UPDATE agent_step_state SET state='failed',error_code=?,updated_at=? "
                    "WHERE plan_id=? AND step_id=?",
                    (exc.code, datetime.now(UTC).isoformat(), plan_id, step_id),
                )
                self.db.execute(
                    "UPDATE agent_plans SET state='paused' WHERE id=?",
                    (plan_id,),
                )
                self._event(plan_id, step_id, "step-failed", {"error_code": exc.code})
            raise
        except Exception as exc:
            with self.db:
                self.db.execute(
                    "UPDATE agent_step_state SET state='failed',error_code='TOOL_FAILURE',"
                    "updated_at=? WHERE plan_id=? AND step_id=?",
                    (datetime.now(UTC).isoformat(), plan_id, step_id),
                )
                self.db.execute(
                    "UPDATE agent_plans SET state='paused' WHERE id=?",
                    (plan_id,),
                )
                self._event(plan_id, step_id, "step-failed", {"error_code": "TOOL_FAILURE"})
            raise AIError("TOOL_FAILURE", "Tool execution failed") from exc
        with self.db:
            self.db.execute(
                "UPDATE agent_step_state SET state='ok',result_json=?,error_code=NULL,updated_at=? "
                "WHERE plan_id=? AND step_id=?",
                (encoded, datetime.now(UTC).isoformat(), plan_id, step_id),
            )
            self._event(
                plan_id,
                step_id,
                "step-completed",
                {"result_digest": canonical_digest(result)},
            )
            unfinished = self.db.execute(
                "SELECT COUNT(*) FROM agent_step_state WHERE plan_id=? AND state!='ok'",
                (plan_id,),
            ).fetchone()
            if unfinished is not None and int(unfinished[0]) == 0:
                self.db.execute(
                    "UPDATE agent_plans SET state='completed' WHERE id=?",
                    (plan_id,),
                )
        return result

    def cancel(self, plan_id: str) -> None:
        plan = self.get_plan(plan_id)
        if plan.state == "completed":
            raise AIError("CONFLICT", "Completed plan cannot be cancelled")
        now = datetime.now(UTC).isoformat()
        with self.db:
            self.db.execute(
                "UPDATE agent_plans SET state='cancelled' WHERE id=?",
                (plan_id,),
            )
            self.db.execute(
                "UPDATE agent_step_state SET state='cancelled',updated_at=? "
                "WHERE plan_id=? AND state IN ('pending','failed')",
                (now, plan_id),
            )
            self._event(plan_id, None, "plan-cancelled", {})

    def recover(self, plan_id: str) -> JsonDict:
        plan = self.get_plan(plan_id)
        rows = self.db.execute(
            "SELECT step_id,state,intent_digest,attempts,error_code "
            "FROM agent_step_state WHERE plan_id=? ORDER BY rowid",
            (plan_id,),
        ).fetchall()
        uncertain: list[str] = []
        retryable: list[str] = []
        completed: list[str] = []
        for step_id, state, _, _, _ in rows:
            step = self._step(plan, str(step_id))
            contract = self.tools[step.operation]
            if state == "ok":
                completed.append(str(step_id))
            elif state == "running":
                if contract.idempotent:
                    retryable.append(str(step_id))
                else:
                    uncertain.append(str(step_id))
            elif state in {"failed", "pending"}:
                retryable.append(str(step_id))
        return {
            "plan_id": plan_id,
            "state": plan.state,
            "completed": completed,
            "retryable": retryable,
            "uncertain_side_effects": uncertain,
        }

    def events(self, plan_id: str) -> list[RunEvent]:
        self.get_plan(plan_id)
        rows = self.db.execute(
            "SELECT sequence,step_id,event_type,payload_digest,created_at "
            "FROM agent_events WHERE plan_id=? ORDER BY sequence",
            (plan_id,),
        ).fetchall()
        return [
            RunEvent(
                sequence=int(sequence),
                plan_id=plan_id,
                step_id=None if step_id is None else str(step_id),
                event_type=str(event_type),
                payload_digest=str(payload_digest),
                created_at=str(created_at),
            )
            for sequence, step_id, event_type, payload_digest, created_at in rows
        ]

    def close(self) -> None:
        self.db.close()


@dataclass(frozen=True)
class ContextItem:
    role: str
    text: str
    protected: bool = False
    source_anchor: str | None = None


class ContextCompactor:
    """Budget context while preserving protected restrictions and evidence anchors."""

    def compact(self, items: Sequence[ContextItem], *, max_chars: int) -> list[ContextItem]:
        if not 256 <= max_chars <= 1_000_000:
            raise AIError("INVALID_INPUT", "Invalid context budget")
        protected = [item for item in items if item.protected or item.source_anchor]
        protected_cost = sum(len(item.text) for item in protected)
        if protected_cost > max_chars:
            raise AIError(
                "RESOURCE_LIMIT",
                "Protected restrictions and source anchors exceed the context budget",
            )
        chosen: list[ContextItem] = list(protected)
        remaining = max_chars - protected_cost
        for item in reversed(items):
            if item in protected:
                continue
            if len(item.text) <= remaining:
                chosen.append(item)
                remaining -= len(item.text)
        positions = {id(item): index for index, item in enumerate(items)}
        return sorted(chosen, key=lambda item: positions[id(item)])


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: int
    system_text: str
    user_template: str
    digest: str


class PromptTemplateStore:
    """Versioned trusted templates; project text is interpolated only as user data."""

    def __init__(self, database: Path) -> None:
        self.db = sqlite3.connect(database)
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS prompt_templates ("
                "name TEXT NOT NULL, version INTEGER NOT NULL, system_text TEXT NOT NULL, "
                "user_template TEXT NOT NULL, digest TEXT NOT NULL, created_at TEXT NOT NULL, "
                "PRIMARY KEY(name,version))"
            )

    def add(self, name: str, system_text: str, user_template: str) -> PromptTemplate:
        if not name or "{{project_text}}" not in user_template:
            raise AIError(
                "INVALID_INPUT",
                "Template requires a name and a {{project_text}} user-data placeholder",
            )
        if "{{project_text}}" in system_text:
            raise AIError("PERMISSION_DENIED", "Untrusted project text cannot enter system role")
        latest = self.db.execute(
            "SELECT COALESCE(MAX(version),0) FROM prompt_templates WHERE name=?",
            (name,),
        ).fetchone()
        version = int(latest[0]) + 1 if latest else 1
        digest = hashlib.sha256(
            f"{name}\0{version}\0{system_text}\0{user_template}".encode()
        ).hexdigest()
        with self.db:
            self.db.execute(
                "INSERT INTO prompt_templates VALUES(?,?,?,?,?,?)",
                (
                    name,
                    version,
                    system_text,
                    user_template,
                    digest,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return PromptTemplate(name, version, system_text, user_template, digest)

    def get(self, name: str, version: int | None = None) -> PromptTemplate:
        if version is None:
            row = self.db.execute(
                "SELECT name,version,system_text,user_template,digest "
                "FROM prompt_templates WHERE name=? ORDER BY version DESC LIMIT 1",
                (name,),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT name,version,system_text,user_template,digest "
                "FROM prompt_templates WHERE name=? AND version=?",
                (name, version),
            ).fetchone()
        if row is None:
            raise AIError("NOT_FOUND", "Prompt template does not exist")
        return PromptTemplate(str(row[0]), int(row[1]), str(row[2]), str(row[3]), str(row[4]))

    def render(self, name: str, project_text: str, *, version: int | None = None) -> JsonDict:
        if len(project_text) > 1_000_000:
            raise AIError("RESOURCE_LIMIT", "Project text exceeds prompt budget")
        template = self.get(name, version)
        return {
            "system": template.system_text,
            "user": template.user_template.replace("{{project_text}}", project_text),
            "template_name": template.name,
            "template_version": template.version,
            "template_digest": template.digest,
        }

    def diff(self, name: str, left: int, right: int) -> JsonDict:
        a = self.get(name, left)
        b = self.get(name, right)
        return {
            "name": name,
            "from_version": left,
            "to_version": right,
            "system_changed": a.system_text != b.system_text,
            "user_template_changed": a.user_template != b.user_template,
            "from_digest": a.digest,
            "to_digest": b.digest,
        }

    def close(self) -> None:
        self.db.close()
