"""Host-issued, one-time capabilities for sensitive analysis operations.

Capabilities are intentionally process-local.  A caller cannot authorize itself by
placing a boolean in a JSON context: the trusted desktop host must ask the facade's
issuer for a token after presenting the exact operation and arguments to the user.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import require
from .models import canonical_json, digest


@dataclass(frozen=True)
class HostCapability:
    """Opaque approval envelope bound to one exact operation invocation."""

    project_id: str
    operation: str
    argument_hash: str
    effect: str
    nonce: str
    issued_at: float
    expires_at: float
    signature: str

    def public_summary(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "operation": self.operation,
            "argument_hash": self.argument_hash,
            "effect": self.effect,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


class CapabilityIssuer:
    """Issue and verify non-serializable trust rooted in an in-memory secret."""

    def __init__(self, project_root: Path, *, max_ttl_seconds: int = 300):
        root = project_root.resolve()
        require(root.is_absolute(), "Project root must be absolute")
        require(1 <= max_ttl_seconds <= 3600, "Capability TTL budget outside allowed range")
        self._project_root = root
        self._project_id = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        self._secret = secrets.token_bytes(32)
        self._max_ttl_seconds = max_ttl_seconds
        self._consumed: set[str] = set()

    @property
    def project_id(self) -> str:
        return self._project_id

    def _payload(
        self,
        *,
        operation: str,
        argument_hash: str,
        effect: str,
        nonce: str,
        issued_at: float,
        expires_at: float,
    ) -> bytes:
        return canonical_json(
            {
                "project_id": self._project_id,
                "operation": operation,
                "argument_hash": argument_hash,
                "effect": effect,
                "nonce": nonce,
                "issued_at": issued_at,
                "expires_at": expires_at,
            }
        )

    def issue(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        effect: str,
        ttl_seconds: int = 60,
        now: float | None = None,
    ) -> HostCapability:
        """Create an approval after the trusted host has shown the exact preview."""

        require(bool(operation) and operation.count(".") == 1, "Invalid operation identifier")
        require(effect in {"local-write", "code-execution", "sensitive-export"}, "Invalid effect")
        require(1 <= ttl_seconds <= self._max_ttl_seconds, "Capability TTL outside allowed range")
        issued_at = float(time.time() if now is None else now)
        expires_at = issued_at + ttl_seconds
        nonce = secrets.token_hex(16)
        argument_hash = digest(dict(arguments))
        payload = self._payload(
            operation=operation,
            argument_hash=argument_hash,
            effect=effect,
            nonce=nonce,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        signature = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        return HostCapability(
            self._project_id,
            operation,
            argument_hash,
            effect,
            nonce,
            issued_at,
            expires_at,
            signature,
        )

    def verify_and_consume(
        self,
        capability: object,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        effect: str,
        now: float | None = None,
    ) -> HostCapability:
        """Validate exact binding, freshness and signature, then burn the nonce."""

        require(
            isinstance(capability, HostCapability),
            "Trusted host capability required",
            "PERMISSION_DENIED",
        )
        current = float(time.time() if now is None else now)
        require(
            capability.project_id == self._project_id,
            "Capability belongs to another project",
            "PERMISSION_DENIED",
        )
        require(
            capability.operation == operation, "Capability operation mismatch", "PERMISSION_DENIED"
        )
        require(capability.effect == effect, "Capability effect mismatch", "PERMISSION_DENIED")
        require(
            capability.argument_hash == digest(dict(arguments)),
            "Capability arguments changed",
            "PERMISSION_DENIED",
        )
        require(
            capability.issued_at <= current <= capability.expires_at,
            "Capability expired or not yet valid",
            "PERMISSION_DENIED",
        )
        require(
            capability.nonce not in self._consumed,
            "Capability has already been used",
            "PERMISSION_DENIED",
        )
        payload = self._payload(
            operation=capability.operation,
            argument_hash=capability.argument_hash,
            effect=capability.effect,
            nonce=capability.nonce,
            issued_at=capability.issued_at,
            expires_at=capability.expires_at,
        )
        expected = hmac.new(self._secret, payload, hashlib.sha256).hexdigest()
        require(
            hmac.compare_digest(expected, capability.signature),
            "Capability signature invalid",
            "PERMISSION_DENIED",
        )
        self._consumed.add(capability.nonce)
        return capability

    def consumed(self, nonce: str) -> bool:
        return nonce in self._consumed


@dataclass(frozen=True)
class HostPaths:
    """Filesystem roots injected when the facade is created by the trusted host."""

    import_root: Path | None = None
    export_root: Path | None = None
    execution_root: Path | None = None

    def __post_init__(self) -> None:
        for value in (self.import_root, self.export_root, self.execution_root):
            if value is not None:
                require(value.is_absolute(), "Trusted host roots must be absolute")

    @staticmethod
    def _bounded(root: Path | None, relative: str, *, must_exist: bool) -> Path:
        require(root is not None, "Trusted host root not configured", "PERMISSION_DENIED")
        require(
            relative and not Path(relative).is_absolute(),
            "Path must be project-relative",
            "PERMISSION_DENIED",
        )
        base = root.resolve()
        candidate = (base / relative).resolve()
        require(
            candidate.is_relative_to(base), "Path escapes trusted host root", "PERMISSION_DENIED"
        )
        if must_exist:
            require(candidate.is_file(), "Input file does not exist", "NOT_FOUND")
        else:
            require(candidate.parent.is_dir(), "Output directory does not exist", "NOT_FOUND")
        return candidate

    def import_file(self, relative: str) -> Path:
        return self._bounded(self.import_root, relative, must_exist=True)

    def export_file(self, relative: str) -> Path:
        return self._bounded(self.export_root, relative, must_exist=False)

    def execution_directory(self) -> Path | None:
        if self.execution_root is None:
            return None
        root = self.execution_root.resolve()
        require(root.is_dir(), "Execution root does not exist", "NOT_FOUND")
        return root
