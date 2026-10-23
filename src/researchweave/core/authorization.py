"""Trusted-host approval tokens bound to one exact operation request."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from .contracts import OperationRequest, digest


class AuthorizationError(RuntimeError):
    """Raised when a host approval is absent, stale, substituted, or replayed."""


@dataclass(frozen=True)
class HostApproval:
    request_digest: str
    nonce: str
    issued_at: float
    expires_at: float
    signature: str


class HostAuthority:
    """Process-local authority controlled only by the application host."""

    def __init__(self, *, max_ttl_seconds: int = 300) -> None:
        if not 1 <= max_ttl_seconds <= 3600:
            raise ValueError("Approval TTL budget must be between 1 and 3600 seconds")
        self._secret = secrets.token_bytes(32)
        self._max_ttl_seconds = max_ttl_seconds
        self._consumed: set[str] = set()

    def _signature(self, request_digest: str, nonce: str, expires_at: float) -> str:
        message = f"{request_digest}|{nonce}|{expires_at:.6f}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def issue(
        self,
        request: OperationRequest,
        *,
        ttl_seconds: int = 60,
        now: float | None = None,
    ) -> HostApproval:
        if request.preview:
            raise ValueError("Preview requests do not require approval")
        if not 1 <= ttl_seconds <= self._max_ttl_seconds:
            raise ValueError("Approval TTL exceeds host policy")
        issued_at = time.time() if now is None else float(now)
        expires_at = issued_at + ttl_seconds
        request_digest = digest(request.approval_payload())
        nonce = secrets.token_hex(16)
        return HostApproval(
            request_digest=request_digest,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
            signature=self._signature(request_digest, nonce, expires_at),
        )

    def verify_and_consume(
        self,
        request: OperationRequest,
        approval: HostApproval | None,
        *,
        now: float | None = None,
    ) -> None:
        if approval is None:
            raise AuthorizationError("Host approval required")
        current = time.time() if now is None else float(now)
        expected_digest = digest(request.approval_payload())
        if approval.request_digest != expected_digest:
            raise AuthorizationError("Approval arguments or request identity changed")
        if not approval.issued_at <= current <= approval.expires_at:
            raise AuthorizationError("Approval expired or is not yet valid")
        if approval.nonce in self._consumed:
            raise AuthorizationError("Approval has already been used")
        expected_signature = self._signature(
            approval.request_digest, approval.nonce, approval.expires_at
        )
        if not hmac.compare_digest(expected_signature, approval.signature):
            raise AuthorizationError("Approval signature invalid")
        self._consumed.add(approval.nonce)
