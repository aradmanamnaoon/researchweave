"""Explicit, opt-in local model discovery with deterministic test transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .errors import AIError
from .policy import EgressPolicy, validate_endpoint


class ProbeTransport(Protocol):
    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes: ...


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise AIError("PERMISSION_DENIED", "Local service redirect denied")


class LoopbackProbeTransport:
    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        validate_endpoint(url, local=True)
        request = Request(url, headers={"Accept": "application/json"}, method="GET")  # noqa: S310
        try:
            # Disable environment proxy configuration for the explicitly local service.
            with build_opener(ProxyHandler({}), _RejectRedirect).open(
                request, timeout=timeout
            ) as response:
                if response.geturl() != url:
                    raise AIError("PERMISSION_DENIED", "Local runtime redirect denied")
                payload: bytes = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise AIError("RESOURCE_LIMIT", "Model metadata too large")
                return payload
        except HTTPError as exc:
            raise AIError("PROVIDER_UNAVAILABLE", f"Local runtime HTTP {exc.code}") from None
        except (URLError, TimeoutError) as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Local runtime is not reachable") from exc


@dataclass(frozen=True)
class LocalModel:
    identifier: str
    digest: str | None
    size_bytes: int | None
    runtime: str


class LocalRuntimeDiscovery:
    def __init__(
        self,
        endpoint: str,
        *,
        protocol: str = "ollama",
        transport: ProbeTransport | None = None,
    ) -> None:
        self.endpoint = validate_endpoint(endpoint, local=True).rstrip("/")
        if protocol not in {"ollama", "openai-compatible"}:
            raise AIError("INVALID_INPUT", "Unsupported local runtime protocol")
        self.protocol = protocol
        self.transport = transport or LoopbackProbeTransport()

    def discover(self, policy: EgressPolicy) -> list[LocalModel]:
        policy.permit(self.endpoint, local=True)
        suffix = "/api/tags" if self.protocol == "ollama" else "/v1/models"
        data = self.transport.fetch(self.endpoint + suffix, timeout=3.0, max_bytes=2_000_000)
        try:
            response = json.loads(data)
            entries = response["models"] if self.protocol == "ollama" else response["data"]
            if not isinstance(entries, list) or len(entries) > 10_000:
                raise ValueError("Invalid model catalog length")
            result: list[LocalModel] = []
            for record in entries:
                if not isinstance(record, dict):
                    raise ValueError("Invalid model metadata")
                name = record.get("name") if self.protocol == "ollama" else record.get("id")
                if not isinstance(name, str) or not name or len(name) > 512:
                    raise ValueError("Invalid model identifier")
                digest = record.get("digest")
                size = record.get("size")
                if digest is not None and not isinstance(digest, str):
                    raise ValueError("Invalid model hash")
                if size is not None and (type(size) is not int or size < 0):
                    raise ValueError("Invalid model size")
                result.append(LocalModel(name, digest, size, self.protocol))
            return result
        except (TypeError, KeyError, ValueError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Local model catalog is malformed") from exc
