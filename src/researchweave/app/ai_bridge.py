"""Trusted desktop adapter for executing explicitly approved AI operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from researchweave.core import CommandBus, OperationRequest


class ProductionAIBackend:
    """Route approved desktop actions through the shared AI command-bus boundary."""

    def __init__(self, bus: CommandBus) -> None:
        self._bus = bus

    def capabilities(self) -> list[Mapping[str, Any]]:
        return [item for item in self._bus.capabilities() if item.get("domain") == "ai"]

    def execute_approved(
        self,
        project_id: str,
        action: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            scope = UUID(project_id)
        except ValueError as exc:
            raise ValueError("Desktop project identifier is not a UUID") from exc
        operation = str(action.get("operation", ""))
        arguments = action.get("arguments", {})
        if not isinstance(arguments, Mapping):
            raise ValueError("Approved AI arguments must be structured")
        capability = next(
            (item for item in self.capabilities() if item.get("operation") == operation),
            None,
        )
        if capability is None:
            return {
                "status": "failed",
                "data": {},
                "error": {
                    "code": "PERMISSION_DENIED",
                    "message": "Approved desktop action is not an AI-domain operation",
                    "recovery": "Choose an operation from the integrated AI capability list.",
                },
            }
        effect = self._bus.effect_for(operation)
        if effect == "external-network" and (
            not bool(action.get("data_egress"))
            or not str(action.get("network_destination", "")).strip()
        ):
            return {
                "status": "failed",
                "data": {},
                "error": {
                    "code": "NEEDS_APPROVAL",
                    "message": "Remote AI execution requires an explicit egress destination",
                    "recovery": (
                        "Create and approve a new proposal with the exact network destination."
                    ),
                },
            }
        request = OperationRequest(
            operation=operation,
            project_id=scope,
            arguments=dict(arguments),
            actor="desktop-approved-agent",
        )
        approval = None
        if effect != "read":
            approval = self._bus.issue_approval(request)
        return self._bus.dispatch(request, approval=approval)
