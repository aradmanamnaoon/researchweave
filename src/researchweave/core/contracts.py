"""Stable wire contracts shared by desktop, CLI, agents, and domain facades."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _json_default(value: object) -> object:
    if isinstance(value, bytes):
        return {
            "$type": "bytes",
            "length": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, Path):
        return {"$type": "path", "value": str(value)}
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}")


def canonical_json(value: object) -> bytes:
    """Serialize JSON deterministically and reject non-finite/non-JSON values."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class OperationRequest(BaseModel):
    """Versioned request envelope used at the integration boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal[1] = 1
    request_id: UUID = Field(default_factory=uuid4)
    operation: str = Field(min_length=3, max_length=160, pattern=r"^[a-z][a-z0-9_.-]+$")
    project_id: UUID
    arguments: dict[str, Any] = Field(default_factory=dict)
    preview: bool = False
    expected_revision: int | None = Field(default=None, ge=0)
    actor: str = Field(default="local-user", min_length=1, max_length=120)

    def approval_payload(self) -> dict[str, Any]:
        """Return the exact fields an approval is bound to."""

        return {
            "protocol_version": self.protocol_version,
            "request_id": str(self.request_id),
            "operation": self.operation,
            "project_id": str(self.project_id),
            "arguments": self.arguments,
            "expected_revision": self.expected_revision,
            "actor": self.actor,
        }


COMMON_ERROR_CODES = frozenset(
    {
        "INVALID_INPUT",
        "NOT_FOUND",
        "CONFLICT",
        "PERMISSION_DENIED",
        "NEEDS_APPROVAL",
        "DEPENDENCY_MISSING",
        "OFFLINE_DENIED",
        "NETWORK_ERROR",
        "RATE_LIMITED",
        "AUTH_FAILED",
        "TIMEOUT",
        "CANCELLED",
        "INTEGRITY_FAILURE",
        "SCHEMA_MISMATCH",
        "UNSUPPORTED_FORMAT",
        "RESOURCE_LIMIT",
        "INTERNAL_ERROR",
    }
)
