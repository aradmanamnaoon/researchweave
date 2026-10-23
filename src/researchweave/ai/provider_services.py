from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .errors import AIError
from .policy import EgressPolicy
from .provider_adapters import ChatAdapter, ProviderMessage, ProviderResult
from .retrieval_security import PrivacyClass, PrivacyClassifier


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    configured: bool
    reachable: bool | None
    local: bool
    error_code: str | None
    latency_ms: int | None


@dataclass(frozen=True)
class ModelChoice:
    provider_id: str
    model: str
    local: bool
    reason: str
    monetary_cost_known: bool


class ProviderCatalog:
    def __init__(self) -> None:
        self.adapters: dict[str, ChatAdapter] = {}

    def register(self, adapter: ChatAdapter) -> None:
        if adapter.identifier in self.adapters:
            raise AIError("CONFLICT", "Duplicate provider adapter")
        self.adapters[adapter.identifier] = adapter

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": adapter.identifier,
                "model": adapter.model,
                "endpoint": adapter.endpoint,
                "local": adapter.local,
                "capabilities": {
                    "chat": adapter.capabilities.chat,
                    "streaming": adapter.capabilities.streaming,
                    "structured_output": adapter.capabilities.structured_output,
                    "tool_calling": adapter.capabilities.tool_calling,
                    "embeddings": adapter.capabilities.embeddings,
                    "vision": adapter.capabilities.vision,
                },
            }
            for adapter in sorted(self.adapters.values(), key=lambda item: item.identifier)
        ]

    def get(self, identifier: str) -> ChatAdapter:
        try:
            return self.adapters[identifier]
        except KeyError as exc:
            raise AIError("NOT_FOUND", "Unknown provider adapter") from exc


class ModelChooser:
    def __init__(self, catalog: ProviderCatalog) -> None:
        self.catalog = catalog
        self.privacy = PrivacyClassifier()

    def choose(
        self,
        candidates: Sequence[str],
        *,
        project_class: str,
        offline_only: bool,
        prefer_local: bool = True,
    ) -> ModelChoice:
        if not candidates:
            raise AIError("NOT_FOUND", "No candidate providers were supplied")
        adapters = [self.catalog.get(item) for item in candidates]
        if offline_only:
            adapters = [item for item in adapters if item.local]
        if not adapters:
            raise AIError("OFFLINE_DENIED", "No local provider is available for offline-only mode")
        classification = PrivacyClass.parse(project_class)
        allowed = []
        for adapter in adapters:
            decision = self.privacy.classify(
                project_class,
                project_class,
                provider_local=adapter.local,
            )
            if adapter.local or decision.may_leave_device:
                allowed.append(adapter)
        if not allowed:
            raise AIError("PERMISSION_DENIED", "Project privacy class blocks candidate providers")
        if prefer_local:
            allowed.sort(key=lambda item: (not item.local, item.identifier))
        else:
            allowed.sort(key=lambda item: item.identifier)
        selected = allowed[0]
        return ModelChoice(
            provider_id=selected.identifier,
            model=selected.model,
            local=selected.local,
            reason=(
                "Selected local provider to keep payload on-device."
                if selected.local
                else f"Remote provider permitted for {classification.name.lower()} data."
            ),
            monetary_cost_known=False,
        )


class ProviderHealthService:
    def __init__(self, catalog: ProviderCatalog) -> None:
        self.catalog = catalog

    def probe(
        self,
        identifier: str,
        policy: EgressPolicy,
        *,
        perform_request: bool = False,
    ) -> ProviderHealth:
        try:
            adapter = self.catalog.get(identifier)
        except AIError:
            return ProviderHealth(identifier, False, None, False, "NOT_FOUND", None)
        if not perform_request:
            return ProviderHealth(identifier, True, None, adapter.local, None, None)
        started = time.perf_counter()
        try:
            adapter.complete(
                [ProviderMessage("user", "Reply with the single word OK.")],
                policy,
                max_tokens=4,
                temperature=0,
            )
        except AIError as exc:
            return ProviderHealth(
                identifier,
                True,
                False,
                adapter.local,
                exc.code,
                max(0, int((time.perf_counter() - started) * 1000)),
            )
        return ProviderHealth(
            identifier,
            True,
            True,
            adapter.local,
            None,
            max(0, int((time.perf_counter() - started) * 1000)),
        )


class ProviderFailover:
    """Explicit bounded failover that never changes local/remote mode silently."""

    def __init__(self, catalog: ProviderCatalog) -> None:
        self.catalog = catalog

    def complete(
        self,
        candidates: Sequence[str],
        messages: Sequence[ProviderMessage],
        policy: EgressPolicy,
        *,
        max_tokens: int = 512,
        allow_remote_fallback: bool = False,
    ) -> ProviderResult:
        if not candidates:
            raise AIError("NOT_FOUND", "No providers configured for failover")
        first = self.catalog.get(candidates[0])
        errors: list[str] = []
        for identifier in candidates:
            adapter = self.catalog.get(identifier)
            if first.local and not adapter.local and not allow_remote_fallback:
                errors.append(f"{identifier}:REMOTE_FALLBACK_REQUIRES_APPROVAL")
                continue
            try:
                return adapter.complete(messages, policy, max_tokens=max_tokens)
            except AIError as exc:
                errors.append(f"{identifier}:{exc.code}")
                if exc.code not in {
                    "PROVIDER_UNAVAILABLE",
                    "RATE_LIMITED",
                    "TIMEOUT",
                    "SERVICE_UNAVAILABLE",
                }:
                    raise
        raise AIError("PROVIDER_UNAVAILABLE", "All eligible providers failed: " + ", ".join(errors))
