from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from .errors import AIError


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def validate_endpoint(url: str, *, local: bool = False) -> str:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or not parsed.hostname:
        raise AIError("INVALID_INPUT", "Endpoint contains invalid authority or fragment")
    if parsed.scheme not in ({"http", "https"} if local else {"https"}):
        raise AIError("PERMISSION_DENIED", "Remote endpoints require HTTPS")
    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host in {"localhost", "localhost.localdomain"}:
            if not local:
                raise AIError(
                    "PERMISSION_DENIED", "Local network endpoints require explicit local mode"
                ) from None
        elif local:
            raise AIError("PERMISSION_DENIED", "Local runtimes must use loopback") from None
    else:
        if local and not address.is_loopback:
            raise AIError("PERMISSION_DENIED", "Local runtimes must use loopback")
        if not local and not address.is_global:
            raise AIError("PERMISSION_DENIED", "Private or reserved network endpoints are blocked")
    return url


@dataclass(frozen=True)
class EgressPolicy:
    offline: bool = True
    allow_local_models: bool = True
    allowed_hosts: tuple[str, ...] = ()

    def permit(self, url: str, *, local: bool = False) -> None:
        validate_endpoint(url, local=local)
        if local:
            if not self.allow_local_models:
                raise AIError("OFFLINE_DENIED", "Local model runtime is disabled")
            return
        if self.offline:
            raise AIError("OFFLINE_DENIED", "External network is disabled")
        host = urlsplit(url).hostname or ""
        if host not in self.allowed_hosts:
            raise AIError("PERMISSION_DENIED", "Endpoint is not on the host allowlist")


@dataclass(frozen=True)
class Approval:
    project_id: str
    operation: str
    argument_digest: str
    expires_at: datetime
    signature: str


class ApprovalIssuer:
    """Host-owned authority: never construct this with model-supplied keys."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("Approval key must contain at least 32 bytes")
        self._key = key

    def issue(
        self, project_id: str, operation: str, arguments: dict[str, Any], expires_at: datetime
    ) -> Approval:
        if expires_at.tzinfo is None:
            raise ValueError("Approval expiry must have a timezone")
        digest = canonical_digest(arguments)
        message = f"{project_id}|{operation}|{digest}|{expires_at.isoformat()}".encode()
        signature = hmac.new(self._key, message, hashlib.sha256).hexdigest()
        return Approval(project_id, operation, digest, expires_at, signature)

    def verify(
        self,
        approval: Approval | None,
        project_id: str,
        operation: str,
        arguments: dict[str, Any],
    ) -> None:
        if approval is None:
            raise AIError("NEEDS_APPROVAL", "Host approval required")
        if approval.expires_at <= datetime.now(UTC):
            raise AIError("PERMISSION_DENIED", "Approval expired")
        if approval.project_id != project_id or approval.operation != operation:
            raise AIError("PERMISSION_DENIED", "Approval scope mismatch")
        expected = self.issue(project_id, operation, arguments, approval.expires_at)
        if not hmac.compare_digest(expected.signature, approval.signature):
            raise AIError("PERMISSION_DENIED", "Approval signature or arguments mismatch")
