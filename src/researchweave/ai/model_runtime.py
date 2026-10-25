from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from .errors import AIError
from .http_transport import PinnedHTTPTransport
from .policy import EgressPolicy, validate_endpoint
from .provider_adapters import (
    AnthropicAdapter,
    ChatAdapter,
    GeminiAdapter,
    OpenAICompatibleAdapter,
    ProviderMessage,
    ProviderResult,
)
from .providers import HTTPTransport

_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_KINDS = frozenset({"openai-compatible", "anthropic", "gemini"})


@dataclass(frozen=True)
class ModelProfile:
    """Serializable model endpoint configuration with no credential material."""

    identifier: str
    kind: str
    endpoint: str
    model: str
    local: bool = False
    credential_env: str | None = None
    tool_calling: bool = False
    enabled: bool = True

    def validate(self) -> ModelProfile:
        if not _PROFILE_ID.fullmatch(self.identifier):
            raise AIError("INVALID_INPUT", "Invalid model profile identifier")
        if self.kind not in _KINDS:
            raise AIError("INVALID_INPUT", "Unsupported model provider protocol")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 256:
            raise AIError("INVALID_INPUT", "Model identifier is required")
        validate_endpoint(self.endpoint, local=self.local)
        if self.kind in {"anthropic", "gemini"} and self.local:
            raise AIError("INVALID_INPUT", "Native Anthropic and Gemini adapters are remote-only")
        if self.credential_env is not None and not _ENV_NAME.fullmatch(self.credential_env):
            raise AIError("INVALID_INPUT", "Credential environment variable name is invalid")
        return self

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> ModelProfile:
        try:
            profile = cls(
                identifier=str(raw["identifier"]),
                kind=str(raw["kind"]),
                endpoint=str(raw["endpoint"]),
                model=str(raw["model"]),
                local=bool(raw.get("local", False)),
                credential_env=(
                    None
                    if raw.get("credential_env") in (None, "")
                    else str(raw.get("credential_env"))
                ),
                tool_calling=bool(raw.get("tool_calling", False)),
                enabled=bool(raw.get("enabled", True)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AIError("INVALID_INPUT", "Model profile is incomplete") from exc
        return profile.validate()

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelConfigStore:
    """Atomic JSON store for provider/model selection; credentials stay external."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"version": self.VERSION, "active_profile": None, "profiles": []})
        self._read()

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise AIError("STORAGE_FAILURE", "Model configuration could not be read") from exc
        if not isinstance(raw, dict) or raw.get("version") != self.VERSION:
            raise AIError("INTEGRITY_FAILURE", "Unsupported model configuration version")
        profiles = raw.get("profiles")
        active = raw.get("active_profile")
        if not isinstance(profiles, list) or not all(isinstance(item, dict) for item in profiles):
            raise AIError("INTEGRITY_FAILURE", "Stored model profiles are malformed")
        parsed = [ModelProfile.from_mapping(dict(item)) for item in profiles]
        identifiers = [item.identifier for item in parsed]
        if len(identifiers) != len(set(identifiers)):
            raise AIError("INTEGRITY_FAILURE", "Stored model profile identifiers are duplicated")
        if active is not None and (not isinstance(active, str) or active not in identifiers):
            raise AIError("INTEGRITY_FAILURE", "Active model profile is missing")
        return {
            "version": self.VERSION,
            "active_profile": active,
            "profiles": [item.public_dict() for item in parsed],
        }

    def _write(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise AIError("STORAGE_FAILURE", "Model configuration could not be saved") from exc

    def snapshot(self) -> dict[str, Any]:
        return self._read()

    def profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(ModelProfile.from_mapping(item) for item in self._read()["profiles"])

    def get(self, identifier: str) -> ModelProfile:
        for profile in self.profiles():
            if profile.identifier == identifier:
                return profile
        raise AIError("NOT_FOUND", "Model profile does not exist")

    def active(self) -> ModelProfile:
        state = self._read()
        identifier = state["active_profile"]
        if identifier is None:
            raise AIError("NOT_FOUND", "No active model profile is configured")
        profile = self.get(str(identifier))
        if not profile.enabled:
            raise AIError("PROVIDER_UNAVAILABLE", "Active model profile is disabled")
        return profile

    def upsert(self, profile: ModelProfile, *, activate: bool = False) -> dict[str, Any]:
        profile = profile.validate()
        state = self._read()
        profiles = [ModelProfile.from_mapping(item) for item in state["profiles"]]
        replaced = False
        updated: list[ModelProfile] = []
        for existing in profiles:
            if existing.identifier == profile.identifier:
                updated.append(profile)
                replaced = True
            else:
                updated.append(existing)
        if not replaced:
            updated.append(profile)
        state["profiles"] = [
            item.public_dict() for item in sorted(updated, key=lambda x: x.identifier)
        ]
        if activate or state["active_profile"] is None:
            state["active_profile"] = profile.identifier
        self._write(state)
        return self._read()

    def activate(self, identifier: str | None) -> dict[str, Any]:
        state = self._read()
        if identifier is not None:
            profile = self.get(identifier)
            if not profile.enabled:
                raise AIError("PROVIDER_UNAVAILABLE", "Disabled model profile cannot be activated")
        state["active_profile"] = identifier
        self._write(state)
        return self._read()


class ConfiguredModelRuntime:
    """Resolve one selected profile into the existing provider adapter contract."""

    def __init__(
        self,
        store: ModelConfigStore,
        policy: EgressPolicy,
        *,
        transport: HTTPTransport | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.transport = transport or PinnedHTTPTransport()

    @staticmethod
    def _credential(profile: ModelProfile) -> str | None:
        if profile.credential_env is None:
            return None
        value = os.environ.get(profile.credential_env)
        if not value:
            raise AIError(
                "CREDENTIAL_REQUIRED",
                f"Credential environment variable {profile.credential_env} is not set",
            )
        return value

    def adapter(self, profile_id: str | None = None) -> ChatAdapter:
        profile = self.store.active() if profile_id is None else self.store.get(profile_id)
        if not profile.enabled:
            raise AIError("PROVIDER_UNAVAILABLE", "Selected model profile is disabled")
        credential = self._credential(profile)
        if profile.kind == "openai-compatible":
            return OpenAICompatibleAdapter(
                profile.identifier,
                profile.endpoint,
                profile.model,
                credential=credential,
                local=profile.local,
                tool_calling=profile.tool_calling,
                transport=self.transport,
            )
        if profile.kind == "anthropic":
            if credential is None:
                raise AIError("CREDENTIAL_REQUIRED", "Anthropic profile requires a credential")
            return AnthropicAdapter(
                credential,
                profile.model,
                endpoint=profile.endpoint,
                transport=self.transport,
            )
        if profile.kind == "gemini":
            if credential is None:
                raise AIError("CREDENTIAL_REQUIRED", "Gemini profile requires a credential")
            return GeminiAdapter(
                credential,
                profile.model,
                endpoint=profile.endpoint,
                transport=self.transport,
            )
        raise AIError("INVALID_INPUT", "Unsupported model provider protocol")

    def complete(
        self,
        messages: list[ProviderMessage],
        *,
        profile_id: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        adapter = self.adapter(profile_id)
        return adapter.complete(
            messages,
            self.policy,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def complete_with_tools(
        self,
        messages: list[ProviderMessage],
        tools: Sequence[Mapping[str, Any]],
        *,
        profile_id: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> ProviderResult:
        adapter = self.adapter(profile_id)
        if not adapter.capabilities.tool_calling:
            raise AIError("PROVIDER_UNAVAILABLE", "Active model has no native tool calling")
        complete_with_tools = getattr(adapter, "complete_with_tools", None)
        if not callable(complete_with_tools):
            raise AIError("PROVIDER_UNAVAILABLE", "Active adapter cannot execute native tools")
        return cast(
            ProviderResult,
            cast(Any, complete_with_tools)(
                messages,
                self.policy,
                tools,
                max_tokens=max_tokens,
                temperature=temperature,
            ),
        )

    def stream(
        self,
        messages: list[ProviderMessage],
        *,
        profile_id: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        on_delta: Callable[[str], None] | None = None,
    ) -> ProviderResult:
        adapter = self.adapter(profile_id)
        if not isinstance(adapter, OpenAICompatibleAdapter) or not adapter.capabilities.streaming:
            raise AIError("PROVIDER_UNAVAILABLE", "Active model profile does not support streaming")
        return adapter.stream(
            messages,
            self.policy,
            max_tokens=max_tokens,
            temperature=temperature,
            on_delta=on_delta,
        )

    def stream_with_tools(
        self,
        messages: list[ProviderMessage],
        tools: Sequence[Mapping[str, Any]],
        *,
        profile_id: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        on_delta: Callable[[str], None] | None = None,
    ) -> ProviderResult:
        adapter = self.adapter(profile_id)
        if (
            not isinstance(adapter, OpenAICompatibleAdapter)
            or not adapter.capabilities.tool_calling
        ):
            raise AIError("PROVIDER_UNAVAILABLE", "Active model has no native tool calling")
        return adapter.stream_with_tools(
            messages,
            self.policy,
            tools,
            max_tokens=max_tokens,
            temperature=temperature,
            on_delta=on_delta,
        )
