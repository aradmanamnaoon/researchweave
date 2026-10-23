"""Versioned deterministic analysis plans, dependency checks and replay receipts.

The host is responsible for selecting an authorized project and injecting the
facade. Plans are declarative records; they never contain executable Python.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from .errors import require
from .models import canonical_json, digest, runtime_versions, utc_now


@dataclass(frozen=True)
class AnalysisStep:
    """One operation, with dependencies and optional runtime argument bindings."""

    step_id: str
    operation: str
    arguments: dict[str, Any]
    dependencies: tuple[str, ...] = ()
    binds: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisPlan:
    plan_id: str
    schema_version: int
    steps: tuple[AnalysisStep, ...]
    seed: int
    rationale: str
    hypotheses: tuple[str, ...] = ()

    def validate(self) -> None:
        require(self.schema_version == 1, "Unsupported analysis plan schema", "SCHEMA_MISMATCH")
        require(bool(self.plan_id) and self.plan_id.isidentifier(), "Invalid plan identifier")
        require(
            isinstance(self.seed, int) and 0 <= self.seed < 2**32,
            "Seed must be an unsigned 32-bit integer",
        )
        require(1 <= len(self.steps) <= 100, "Plan step budget must be 1..100")
        ids = [step.step_id for step in self.steps]
        require(len(set(ids)) == len(ids), "Duplicate step identifier", "CONFLICT")
        for step in self.steps:
            require(step.step_id.isidentifier(), "Step identifiers must be names")
            require(
                step.operation not in {"dataset.import", "runtime.python", "runtime.r"},
                "Plan cannot implicitly import or execute scripts",
                "PERMISSION_DENIED",
            )
            require(
                step.operation.count(".") == 1
                and step.operation.startswith(("dataset.", "statistics.", "plot.")),
                "Unsupported plan operation",
            )
            require(
                set(step.dependencies) <= set(ids) - {step.step_id},
                "Unknown/cyclic self dependency",
                "SCHEMA_MISMATCH",
            )
            require(
                set(step.binds.values()) <= set(step.dependencies),
                "Bindings require explicit dependency",
                "SCHEMA_MISMATCH",
            )
            require(all(key.isidentifier() for key in step.binds), "Invalid bound key")
        self.execution_order()  # verifies absence of cycles

    def execution_order(self) -> tuple[str, ...]:
        ready: list[str] = []
        remaining = {step.step_id: set(step.dependencies) for step in self.steps}
        while remaining:
            next_ids = sorted(key for key, deps in remaining.items() if not deps)
            require(bool(next_ids), "Cycle in analysis plan", "SCHEMA_MISMATCH")
            for key in next_ids:
                ready.append(key)
                del remaining[key]
            for dependencies in remaining.values():
                dependencies.difference_update(next_ids)
        return tuple(ready)

    @property
    def spec_hash(self) -> str:
        return digest(asdict(self))

    def to_json(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> AnalysisPlan:
        require(
            set(data) == {"plan_id", "schema_version", "steps", "seed", "rationale", "hypotheses"},
            "Invalid plan keys",
            "SCHEMA_MISMATCH",
        )
        require(isinstance(data["steps"], (list, tuple)), "Plan steps must be an array")
        steps = tuple(
            AnalysisStep(
                step_id=step["step_id"],
                operation=step["operation"],
                arguments=dict(step["arguments"]),
                dependencies=tuple(step.get("dependencies", ())),
                binds=dict(step.get("binds", {})),
            )
            for step in data["steps"]
        )
        plan = cls(
            str(data["plan_id"]),
            int(data["schema_version"]),
            steps,
            int(data["seed"]),
            str(data["rationale"]),
            tuple(data["hypotheses"]),
        )
        plan.validate()
        return plan


class AnalysisDispatcher(Protocol):
    def execute(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class ExecutionReceipt:
    plan_hash: str
    environment: dict[str, str]
    step_results: tuple[dict[str, Any], ...]
    status: str
    output_hash: str
    executed_at: str

    def deterministic_projection(self) -> dict[str, Any]:
        return {
            "plan_hash": self.plan_hash,
            "environment": self.environment,
            "step_results": self.step_results,
            "status": self.status,
        }


def _bind_arguments(step: AnalysisStep, results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    arguments = dict(step.arguments)
    for key, step_id in step.binds.items():
        result = results[step_id]
        require(result.get("status") == "ok", "Cannot bind failed predecessor")
        output = result.get("data")
        require(
            isinstance(output, Mapping) and key in output,
            "Bound predecessor output missing",
            "SCHEMA_MISMATCH",
        )
        bound_output = cast(Mapping[str, Any], output)
        arguments[key] = bound_output[key]
    return arguments


def execute_plan(
    plan: AnalysisPlan, dispatcher: AnalysisDispatcher, trusted_context: Mapping[str, Any]
) -> ExecutionReceipt:
    plan.validate()
    by_id = {step.step_id: step for step in plan.steps}
    results: dict[str, Mapping[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    for step_id in plan.execution_order():
        step = by_id[step_id]
        arguments = _bind_arguments(step, results)
        result = dispatcher.execute(step.operation, arguments, trusted_context)
        # Preserve structured results exactly, but refuse nondeterministic/private objects.
        canonical_json(result)
        results[step_id] = result
        entries.append(
            {
                "step_id": step_id,
                "operation": step.operation,
                "argument_hash": digest(arguments),
                "result": dict(result),
            }
        )
        if result.get("status") != "ok":
            break
    state = (
        "ok"
        if len(entries) == len(plan.steps)
        and all(entry["result"]["status"] == "ok" for entry in entries)
        else "failed"
    )
    environment = runtime_versions()
    projection = {
        "plan_hash": plan.spec_hash,
        "environment": environment,
        "step_results": entries,
        "status": state,
    }
    return ExecutionReceipt(
        plan.spec_hash, environment, tuple(entries), state, digest(projection), utc_now()
    )


def verify_replay(expected: ExecutionReceipt, actual: ExecutionReceipt) -> dict[str, Any]:
    require(expected.plan_hash == actual.plan_hash, "Plan hash differs", "INTEGRITY_FAILURE")
    if expected.environment != actual.environment:
        return {
            "match": False,
            "reason": "environment_changed",
            "expected_environment": expected.environment,
            "actual_environment": actual.environment,
        }
    # Exclude nonsemantic run timestamps already absent from deterministic projection.
    match = expected.output_hash == actual.output_hash
    return {
        "match": match,
        "reason": "same" if match else "results_changed",
        "expected_output_hash": expected.output_hash,
        "actual_output_hash": actual.output_hash,
    }


def receipt_from_json(data: Mapping[str, Any]) -> ExecutionReceipt:
    """Parse and integrity-check an execution receipt supplied at a command boundary."""

    require(
        set(data)
        == {
            "plan_hash",
            "environment",
            "step_results",
            "status",
            "output_hash",
            "executed_at",
        },
        "Invalid receipt keys",
        "SCHEMA_MISMATCH",
    )
    require(isinstance(data["environment"], Mapping), "Receipt environment must be an object")
    require(isinstance(data["step_results"], (list, tuple)), "Receipt steps must be an array")
    require(data["status"] in {"ok", "failed"}, "Invalid receipt status", "SCHEMA_MISMATCH")
    require(
        all(isinstance(item, Mapping) for item in data["step_results"]),
        "Receipt steps must contain objects",
        "SCHEMA_MISMATCH",
    )
    receipt = ExecutionReceipt(
        str(data["plan_hash"]),
        {str(key): str(value) for key, value in data["environment"].items()},
        tuple(dict(item) for item in data["step_results"]),
        str(data["status"]),
        str(data["output_hash"]),
        str(data["executed_at"]),
    )
    require(
        digest(receipt.deterministic_projection()) == receipt.output_hash,
        "Receipt hash mismatch",
        "INTEGRITY_FAILURE",
    )
    return receipt


def save_receipt(receipt: ExecutionReceipt, destination: Path) -> None:
    require(destination.parent.is_dir(), "Receipt directory does not exist", "NOT_FOUND")
    require(not destination.exists(), "Receipt already exists", "CONFLICT")
    data = canonical_json(asdict(receipt))
    require(len(data) <= 20_000_000, "Receipt exceeds storage budget", "RESOURCE_LIMIT")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def load_receipt(path: Path) -> ExecutionReceipt:
    require(path.is_file(), "Receipt not found", "NOT_FOUND")
    require(path.stat().st_size <= 20_000_000, "Receipt exceeds budget", "RESOURCE_LIMIT")
    data = json.loads(path.read_bytes())
    require(isinstance(data, Mapping), "Receipt must be a JSON object", "SCHEMA_MISMATCH")
    return receipt_from_json(data)
