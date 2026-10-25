"""Trusted desktop adapter for executing explicitly approved AI operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from researchweave.ai.conversations import ConversationStore
from researchweave.ai.errors import AIError
from researchweave.ai.facade import build_ai_facade
from researchweave.ai.model_runtime import ModelConfigStore, ModelProfile
from researchweave.ai.policy import ApprovalIssuer, EgressPolicy
from researchweave.core import CommandBus, OperationRequest

from .agent_tools import register_application_tools


class ProductionAIBackend:
    """Route approved desktop actions through the shared AI command-bus boundary."""

    def __init__(self, bus: CommandBus, storage: Path, issuer: ApprovalIssuer) -> None:
        self._bus = bus
        self._storage = storage
        self._issuer = issuer

    def _model_store(self) -> ModelConfigStore:
        return ModelConfigStore(self._storage / "model-providers.json")

    def model_config(self) -> Mapping[str, Any]:
        return self._model_store().snapshot()

    def validate_model_profile(self, profile: Mapping[str, Any]) -> Mapping[str, Any]:
        return ModelProfile.from_mapping(dict(profile)).public_dict()

    def save_model_profile(
        self,
        profile: Mapping[str, Any],
        *,
        activate: bool = True,
    ) -> Mapping[str, Any]:
        parsed = ModelProfile.from_mapping(dict(profile))
        return self._model_store().upsert(parsed, activate=activate)

    def activate_model(self, identifier: str | None) -> Mapping[str, Any]:
        return self._model_store().activate(identifier)

    def _assistant_policy(
        self,
        *,
        profile_id: str | None,
        offline: bool,
        egress_acknowledged: bool,
    ) -> tuple[EgressPolicy, str]:
        store = self._model_store()
        profile = store.active() if profile_id is None else store.get(profile_id)
        if profile.local:
            return (
                EgressPolicy(offline=bool(offline), allow_local_models=True),
                profile.identifier,
            )
        if offline:
            raise AIError("OFFLINE_DENIED", "External network is disabled by desktop offline mode")
        if not egress_acknowledged:
            raise AIError(
                "NEEDS_APPROVAL",
                "Remote model use requires explicit data-egress acknowledgement",
            )
        host = (urlsplit(profile.endpoint).hostname or "").lower().rstrip(".")
        if not host:
            raise AIError("INVALID_INPUT", "Selected model endpoint has no valid host")
        return (
            EgressPolicy(
                offline=False,
                allow_local_models=True,
                allowed_hosts=(host,),
            ),
            profile.identifier,
        )

    def assistant_history(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        facade = build_ai_facade(
            self._storage,
            policy=EgressPolicy(offline=True),
            issuer=self._issuer,
        )
        try:
            return facade.assistant_history(project_id, conversation_id)
        finally:
            facade.close()

    def assistant_conversations(self, project_id: str) -> Mapping[str, Any]:
        facade = build_ai_facade(
            self._storage,
            policy=EgressPolicy(offline=True),
            issuer=self._issuer,
        )
        try:
            return {"conversations": facade.conversations.list_conversations(project_id)}
        finally:
            facade.close()

    def usage_summary(self, project_id: str) -> Mapping[str, Any]:
        try:
            scope = UUID(project_id)
        except ValueError as exc:
            raise AIError("INVALID_INPUT", "Usage summary requires a valid project ID") from exc
        response = self._bus.dispatch(
            OperationRequest(
                operation="usage.summary",
                project_id=scope,
                arguments={"project_id": project_id},
                actor="desktop-user",
            )
        )
        if response.get("status") != "ok":
            error = response.get("error", {})
            code = str(error.get("code", "AI_ERROR")) if isinstance(error, Mapping) else "AI_ERROR"
            message = (
                str(error.get("message", "Usage summary failed"))
                if isinstance(error, Mapping)
                else "Usage summary failed"
            )
            raise AIError(code, message)
        return dict(response.get("data", {}))

    def assistant_send(
        self,
        project_id: str,
        prompt: str,
        *,
        conversation_id: str | None = None,
        profile_id: str | None = None,
        offline: bool,
        egress_acknowledged: bool,
        on_delta: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, Any]:
        policy, selected_profile = self._assistant_policy(
            profile_id=profile_id,
            offline=offline,
            egress_acknowledged=egress_acknowledged,
        )
        facade = build_ai_facade(self._storage, policy=policy, issuer=self._issuer)
        try:
            register_application_tools(facade.durable_agents, self._bus, project_id)
            return facade.assistant_chat(
                project_id,
                prompt,
                conversation_id=conversation_id,
                profile_id=selected_profile,
                on_delta=on_delta,
                is_cancelled=is_cancelled,
            )
        finally:
            facade.close()

    def assistant_approve(
        self,
        project_id: str,
        conversation_id: str,
        *,
        offline: bool,
        egress_acknowledged: bool,
        on_delta: Callable[[str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Mapping[str, Any]:
        pending = ConversationStore(self._storage / "conversations.sqlite").pending_tool(
            project_id,
            conversation_id,
        )
        if pending is None:
            raise AIError("NOT_FOUND", "No pending assistant tool request exists")
        raw_profile_id = pending.get("profile_id")
        profile_id = None if raw_profile_id in (None, "") else str(raw_profile_id)
        policy, _selected_profile = self._assistant_policy(
            profile_id=profile_id,
            offline=offline,
            egress_acknowledged=egress_acknowledged,
        )
        facade = build_ai_facade(self._storage, policy=policy, issuer=self._issuer)
        try:
            register_application_tools(facade.durable_agents, self._bus, project_id)
            return facade.assistant_approve(
                project_id,
                conversation_id,
                on_delta=on_delta,
                is_cancelled=is_cancelled,
            )
        finally:
            facade.close()

    def assistant_deny(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        facade = build_ai_facade(
            self._storage,
            policy=EgressPolicy(offline=True),
            issuer=self._issuer,
        )
        try:
            return facade.assistant_deny(project_id, conversation_id)
        finally:
            facade.close()

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
