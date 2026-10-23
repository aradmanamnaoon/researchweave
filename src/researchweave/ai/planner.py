"""Typed bounded agent graph compiler and human correction validator.

This compiler never accepts a model's declaration of approval or capability.
Only the host-created manifest registry defines callable commands and effects.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import AIError
from .policy import canonical_digest


@dataclass(frozen=True)
class ToolManifest:
    operation: str
    effect: str
    required_arguments: tuple[str, ...] = ()
    optional_arguments: tuple[str, ...] = ()
    max_payload_bytes: int = 16_384
    offline: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.operation or "." not in self.operation:
            raise AIError("INVALID_INPUT", "Tool must use a namespaced operation name")
        if self.effect not in {
            "read",
            "local-write",
            "external-network",
            "irreversible",
            "code-execution",
            "sensitive-egress",
        }:
            raise AIError("INVALID_INPUT", "Unknown tool effect")
        if self.max_payload_bytes < 128 or self.max_payload_bytes > 1_000_000:
            raise AIError("INVALID_INPUT", "Invalid tool payload budget")
        if len(set(self.required_arguments + self.optional_arguments)) != (
            len(self.required_arguments) + len(self.optional_arguments)
        ):
            raise AIError("INVALID_INPUT", "Tool argument names must be unique")

    def validate_arguments(self, arguments: Mapping[str, Any]) -> None:
        keys = set(arguments)
        if keys != (keys & set(self.required_arguments + self.optional_arguments)):
            raise AIError("SCHEMA_MISMATCH", "Tool has unexpected arguments")
        if not set(self.required_arguments).issubset(keys):
            raise AIError("SCHEMA_MISMATCH", "Tool is missing required arguments")
        try:
            payload = json.dumps(arguments, sort_keys=True, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Tool parameters must be finite JSON") from exc
        if len(payload.encode("utf-8")) > self.max_payload_bytes:
            raise AIError("RESOURCE_LIMIT", "Tool payload exceeds declared budget")


@dataclass(frozen=True)
class PlannedStep:
    step_id: str
    operation: str
    arguments: dict[str, Any]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompiledPlan:
    project_id: str
    steps: tuple[PlannedStep, ...]
    plan_digest: str
    requires_approval: tuple[str, ...]
    transmitted_operations: tuple[str, ...]
    estimated_effects: dict[str, int]
    warnings: tuple[str, ...] = ()

    def to_runtime_steps(self) -> list[dict[str, Any]]:
        return [{"operation": s.operation, "arguments": dict(s.arguments)} for s in self.steps]

    def public_preview(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "plan_digest": self.plan_digest,
            "steps": [
                {
                    "step_id": s.step_id,
                    "operation": s.operation,
                    "arguments_digest": canonical_digest(s.arguments),
                    "dependencies": list(s.dependencies),
                }
                for s in self.steps
            ],
            "requires_approval": list(self.requires_approval),
            "transmitted_operations": list(self.transmitted_operations),
            "estimated_effects": dict(self.estimated_effects),
            "warnings": list(self.warnings),
        }


class PlanCompiler:
    def __init__(self, manifests: Sequence[ToolManifest]) -> None:
        self.manifests: dict[str, ToolManifest] = {}
        for manifest in manifests:
            if manifest.operation in self.manifests:
                raise AIError("CONFLICT", "Duplicate host tool manifest")
            self.manifests[manifest.operation] = manifest

    def compile(
        self, project_id: str, steps: Sequence[PlannedStep], *, offline: bool = True
    ) -> CompiledPlan:
        if not project_id or len(project_id) > 256 or not 1 <= len(steps) <= 100:
            raise AIError("INVALID_INPUT", "Project and 1 to 100 steps are required")
        graph: dict[str, PlannedStep] = {}
        effects: dict[str, int] = {}
        for step in steps:
            if not step.step_id or len(step.step_id) > 128 or step.step_id in graph:
                raise AIError("CONFLICT", "Step identifiers must be unique")
            if set(step.dependencies) & {step.step_id}:
                raise AIError("INVALID_INPUT", "Step cannot depend on itself")
            if len(set(step.dependencies)) != len(step.dependencies):
                raise AIError("INVALID_INPUT", "Repeated step dependency")
            manifest = self.manifests.get(step.operation)
            if manifest is None:
                raise AIError("NOT_FOUND", "Plan references an unknown capability")
            manifest.validate_arguments(step.arguments)
            if offline and not manifest.offline:
                raise AIError("OFFLINE_DENIED", "Plan requests a network-only tool")
            graph[step.step_id] = step
            effects[manifest.effect] = effects.get(manifest.effect, 0) + 1

        for step in steps:
            if not set(step.dependencies).issubset(graph):
                raise AIError("NOT_FOUND", "Step dependency does not exist")

        # Stable topological order ensures fixed synthetic test trajectories.
        indegree = {sid: len(item.dependencies) for sid, item in graph.items()}
        children: dict[str, list[str]] = {sid: [] for sid in graph}
        for item in graph.values():
            for dependency in item.dependencies:
                children[dependency].append(item.step_id)
        queue = sorted(sid for sid, count in indegree.items() if count == 0)
        ordered: list[PlannedStep] = []
        while queue:
            sid = queue.pop(0)
            ordered.append(graph[sid])
            for child in children[sid]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
                    queue.sort()
        if len(ordered) != len(graph):
            raise AIError("CONFLICT", "Plan contains a dependency cycle")

        approved = tuple(
            item.step_id for item in ordered if self.manifests[item.operation].effect != "read"
        )
        transmitted = tuple(
            item.step_id
            for item in ordered
            if self.manifests[item.operation].effect in {"external-network", "sensitive-egress"}
        )
        digest = canonical_digest(
            {
                "project": project_id,
                "steps": [
                    {
                        "id": item.step_id,
                        "operation": item.operation,
                        "args": item.arguments,
                        "depends": list(item.dependencies),
                    }
                    for item in ordered
                ],
            }
        )
        return CompiledPlan(project_id, tuple(ordered), digest, approved, transmitted, effects)

    def revise(
        self,
        original: CompiledPlan,
        replacements: Mapping[str, Mapping[str, Any]],
        *,
        offline: bool = True,
    ) -> CompiledPlan:
        if not set(replacements).issubset({step.step_id for step in original.steps}):
            raise AIError("NOT_FOUND", "Correction references a missing plan step")
        edited = [
            PlannedStep(
                item.step_id,
                item.operation,
                dict(replacements[item.step_id])
                if item.step_id in replacements
                else dict(item.arguments),
                item.dependencies,
            )
            for item in original.steps
        ]
        # Recompile from the host tool registry: old approvals are bound to the
        # original arguments and cannot automatically approve a revised plan.
        updated = self.compile(original.project_id, edited, offline=offline)
        if updated.plan_digest == original.plan_digest:
            return updated
        return CompiledPlan(
            updated.project_id,
            updated.steps,
            updated.plan_digest,
            updated.requires_approval,
            updated.transmitted_operations,
            updated.estimated_effects,
            ("Human plan correction changed the argument digest; reapprove effects.",),
        )
