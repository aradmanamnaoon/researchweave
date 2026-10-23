"""Minimal structured logging that redacts credential-bearing attributes."""

import json
import logging
from collections.abc import Mapping
from typing import Any

_SENSITIVE = ("secret", "password", "token", "api_key", "authorization", "credential")


def _redact(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: "[REDACTED]" if any(s in key.lower() for s in _SENSITIVE) else str(value)
        for key, value in fields.items()
    }


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit a JSON event without recording secret-like field values."""
    logger.info(json.dumps({"event": event, **_redact(fields)}, sort_keys=True))
