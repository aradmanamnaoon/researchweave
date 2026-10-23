from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .errors import AIError
from .policy import EgressPolicy


class HTTPTransport(Protocol):
    def send(
        self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float
    ) -> bytes: ...


class URLTransport:
    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        request = Request(url, data=payload, headers=dict(headers), method="POST")  # noqa: S310
        try:
            with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
                if response.geturl() != url:
                    raise AIError("PERMISSION_DENIED", "HTTP redirects are disabled")
                result = response.read(2_000_001)
                if len(result) > 2_000_000:
                    raise AIError("RESOURCE_LIMIT", "Provider response exceeds limit")
                return bytes(result)
        except HTTPError as exc:
            code = {401: "PERMISSION_DENIED", 403: "PERMISSION_DENIED", 429: "RATE_LIMITED"}.get(
                exc.code, "PROVIDER_UNAVAILABLE"
            )
            raise AIError(code, f"Provider HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Provider connection failed") from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise AIError("PERMISSION_DENIED", "Provider redirects are forbidden")


@dataclass(frozen=True)
class ProviderProfile:
    identifier: str
    model: str
    endpoint: str
    local: bool = False
    credential: str | None = field(default=None, repr=False)


class ProviderRegistry:
    def __init__(self, transport: HTTPTransport | None = None) -> None:
        self._profiles: dict[str, ProviderProfile] = {}
        self.transport = transport or URLTransport()

    def register(self, profile: ProviderProfile) -> None:
        if not profile.identifier or not profile.model:
            raise AIError("INVALID_INPUT", "Provider ID and model are required")
        from .policy import validate_endpoint

        validate_endpoint(profile.endpoint, local=profile.local)
        self._profiles[profile.identifier] = profile

    def list(self) -> list[dict[str, Any]]:
        return [
            {"id": p.identifier, "model": p.model, "endpoint": p.endpoint, "local": p.local}
            for p in self._profiles.values()
        ]

    def complete(
        self, identifier: str, prompt: str, policy: EgressPolicy, max_tokens: int = 512
    ) -> dict[str, Any]:
        profile = self._profiles.get(identifier)
        if profile is None:
            raise AIError("NOT_FOUND", "Unknown provider")
        if not prompt or len(prompt) > 100_000 or not 1 <= max_tokens <= 4096:
            raise AIError("INVALID_INPUT", "Prompt or generation budget invalid")
        policy.permit(profile.endpoint, local=profile.local)
        url = profile.endpoint.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if profile.credential:
            headers["Authorization"] = "Bearer " + profile.credential
        payload = json.dumps(
            {
                "model": profile.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }
        ).encode()
        raw = self.transport.send(url, headers, payload, timeout=20)
        try:
            response = json.loads(raw)
            answer = response["choices"][0]["message"]["content"]
            if not isinstance(answer, str):
                raise TypeError
        except (TypeError, KeyError, IndexError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Unexpected provider response") from exc
        return {
            "text": answer,
            "provider": profile.identifier,
            "model": profile.model,
            "usage": response.get("usage", {}),
        }
