"""Unified command routing across evidence, analysis, AI, and desktop domains."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .audit import AuditStore
from .authorization import AuthorizationError, HostApproval, HostAuthority
from .contracts import OperationRequest


class Facade(Protocol):
    def capability_manifest(self) -> list[Mapping[str, Any]]: ...

    def preview(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    def execute(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


ContextFactory = Callable[[OperationRequest, str], dict[str, Any]]
Executor = Callable[[OperationRequest, dict[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class DomainBinding:
    name: str
    facade: Facade
    context_factory: ContextFactory | None = None
    executor: Executor | None = None


@dataclass(frozen=True)
class RegisteredOperation:
    binding: DomainBinding
    effect: str
    manifest: Mapping[str, Any]


def normalized_effect(value: object) -> str:
    effect = str(value or "read")
    if effect == "conditional":
        return "local-write"
    if effect == "sensitive-egress":
        return "sensitive-export"
    return effect


class CommandBus:
    """Route typed requests and enforce a host approval before any side effect."""

    def __init__(self, authority: HostAuthority, audit: AuditStore) -> None:
        self.authority = authority
        self.audit = audit
        self._operations: dict[str, RegisteredOperation] = {}

    def register(self, binding: DomainBinding) -> None:
        for item in binding.facade.capability_manifest():
            operation = str(item.get("operation", ""))
            if not operation:
                raise ValueError(f"{binding.name} advertised an empty operation id")
            if operation in self._operations:
                previous = self._operations[operation].binding.name
                message = f"Duplicate operation {operation!r}: {previous} and {binding.name}"
                raise ValueError(message)
            self._operations[operation] = RegisteredOperation(
                binding=binding,
                effect=normalized_effect(item.get("effect")),
                manifest=dict(item),
            )

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                **dict(registered.manifest),
                "operation": operation,
                "domain": registered.binding.name,
                "effect": registered.effect,
            }
            for operation, registered in sorted(self._operations.items())
        ]

    def effect_for(self, operation: str) -> str:
        registered = self._operations.get(operation)
        if registered is None:
            raise KeyError(operation)
        return registered.effect

    def issue_approval(self, request: OperationRequest, *, ttl_seconds: int = 60) -> HostApproval:
        registered = self._operations.get(request.operation)
        if registered is None:
            raise KeyError(request.operation)
        if registered.effect == "read":
            raise ValueError("Read-only operations do not require approval")
        return self.authority.issue(request, ttl_seconds=ttl_seconds)

    @staticmethod
    def _failure(request: OperationRequest, code: str, message: str) -> dict[str, Any]:
        return {
            "request_id": str(request.request_id),
            "status": "failed",
            "data": {},
            "artifacts": [],
            "warnings": [],
            "error": {"code": code, "message": message, "recovery": "Review the request."},
            "provenance": [],
            "impact": {"local_writes": [], "network_hosts": [], "irreversible": False},
        }

    def dispatch(
        self, request: OperationRequest, *, approval: HostApproval | None = None
    ) -> dict[str, Any]:
        registered = self._operations.get(request.operation)
        if registered is None:
            return self._failure(request, "NOT_FOUND", "Unknown operation")
        effect = registered.effect
        try:
            if not request.preview and effect != "read":
                self.authority.verify_and_consume(request, approval)
        except AuthorizationError as exc:
            result = self._failure(request, "NEEDS_APPROVAL", str(exc))
            self.audit.append(request, effect=effect, result=result)
            return result

        context: dict[str, Any] = {
            "request_id": str(request.request_id),
            "project_id": str(request.project_id),
            "actor": request.actor,
        }
        if request.expected_revision is not None:
            context["expected_revision"] = request.expected_revision
        if registered.binding.context_factory is not None and not request.preview:
            context.update(registered.binding.context_factory(request, effect))

        if request.preview:
            raw = registered.binding.facade.preview(request.operation, request.arguments, context)
        elif registered.binding.executor is not None:
            raw = registered.binding.executor(request, context)
        else:
            raw = registered.binding.facade.execute(request.operation, request.arguments, context)
        result = dict(raw)
        result.setdefault("request_id", str(request.request_id))
        result.setdefault("status", "ok")
        self.audit.append(request, effect=effect, result=result)
        return result
