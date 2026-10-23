from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .budgets import BudgetStore
from .errors import AIError
from .policy import EgressPolicy
from .retrieval_security import PrivacyClassifier


class CompletionBackend(Protocol):
    def complete(
        self,
        identifier: str,
        prompt: str,
        policy: EgressPolicy,
        max_tokens: int = 512,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EgressPreview:
    provider_id: str
    destination_host: str
    payload_bytes: int
    payload_sha256: str
    project_class: str
    effective_class: str
    local: bool
    may_leave_device: bool
    requires_approval: bool
    redactions: int
    content_preview: str


class PrivacyEgressEngine:
    """Create an inspectable payload preview before any provider call."""

    _SENSITIVE_KEYS = {
        "secret",
        "token",
        "password",
        "credential",
        "api_key",
        "authorization",
    }

    def __init__(self) -> None:
        self.classifier = PrivacyClassifier()

    @staticmethod
    def _sanitize_text(text: str, redactions: Mapping[str, str] | None) -> tuple[str, int]:
        if len(text) > 1_000_000:
            raise AIError("RESOURCE_LIMIT", "Egress payload exceeds preview budget")
        sanitized = text
        count = 0
        for secret, replacement in (redactions or {}).items():
            if not secret:
                continue
            occurrences = sanitized.count(secret)
            if occurrences:
                sanitized = sanitized.replace(secret, replacement)
                count += occurrences
        return sanitized, count

    def preview(
        self,
        *,
        provider_id: str,
        endpoint: str,
        prompt: str,
        project_class: str,
        item_class: str | None,
        local: bool,
        redactions: Mapping[str, str] | None = None,
    ) -> EgressPreview:
        if not provider_id:
            raise AIError("INVALID_INPUT", "Provider ID is required")
        sanitized, count = self._sanitize_text(prompt, redactions)
        decision = self.classifier.classify(
            project_class,
            item_class,
            provider_local=local,
        )
        host = urlsplit(endpoint).hostname or ""
        if not host:
            raise AIError("INVALID_INPUT", "Provider endpoint has no host")
        content_preview = sanitized[:240]
        if len(sanitized) > 240:
            content_preview += "…"
        return EgressPreview(
            provider_id=provider_id,
            destination_host=host,
            payload_bytes=len(sanitized.encode()),
            payload_sha256=hashlib.sha256(sanitized.encode()).hexdigest(),
            project_class=project_class,
            effective_class=decision.effective.name.lower(),
            local=local,
            may_leave_device=decision.may_leave_device,
            requires_approval=decision.requires_approval,
            redactions=count,
            content_preview=content_preview,
        )


@dataclass(frozen=True)
class UsageRecord:
    sequence: int
    project_id: str
    provider_id: str
    model: str
    status: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    error_code: str | None
    created_at: str


class UsageDiagnostics:
    """Durable aggregate provider telemetry stored locally only.

    Prompts, responses, credentials and request bodies are never persisted.
    """

    def __init__(self, database: Path) -> None:
        self.db = sqlite3.connect(database, timeout=5)
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS usage_events ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "project_id TEXT NOT NULL, provider_id TEXT NOT NULL, model TEXT NOT NULL, "
                "status TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER, "
                "latency_ms INTEGER NOT NULL, error_code TEXT, created_at TEXT NOT NULL)"
            )

    def record(
        self,
        *,
        project_id: str,
        provider_id: str,
        model: str,
        status: str,
        latency_ms: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error_code: str | None = None,
    ) -> UsageRecord:
        if not project_id or not provider_id or not model:
            raise AIError("INVALID_INPUT", "Usage event identity is incomplete")
        if status not in {"ok", "failed", "cancelled"}:
            raise AIError("INVALID_INPUT", "Invalid usage status")
        for value in (input_tokens, output_tokens):
            if value is not None and (type(value) is not int or value < 0):
                raise AIError("INVALID_INPUT", "Token usage must be nonnegative")
        if not 0 <= latency_ms <= 86_400_000:
            raise AIError("INVALID_INPUT", "Latency is outside supported bounds")
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO usage_events(project_id,provider_id,model,status,input_tokens,"
                "output_tokens,latency_ms,error_code,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    provider_id,
                    model,
                    status,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    error_code,
                    datetime.now(UTC).isoformat(),
                ),
            )
        if cursor.lastrowid is None:
            raise AIError("STORAGE_FAILURE", "Usage event sequence was not assigned")
        sequence = cursor.lastrowid
        row = self.db.execute(
            "SELECT project_id,provider_id,model,status,input_tokens,output_tokens,"
            "latency_ms,error_code,created_at FROM usage_events WHERE sequence=?",
            (sequence,),
        ).fetchone()
        if row is None:
            raise AIError("STORAGE_FAILURE", "Usage event could not be re-read")
        return UsageRecord(
            sequence,
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            None if row[4] is None else int(row[4]),
            None if row[5] is None else int(row[5]),
            int(row[6]),
            None if row[7] is None else str(row[7]),
            str(row[8]),
        )

    def summary(self, project_id: str) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT provider_id,status,input_tokens,output_tokens,latency_ms,error_code "
            "FROM usage_events WHERE project_id=?",
            (project_id,),
        ).fetchall()
        providers: dict[str, dict[str, Any]] = {}
        for provider, status, input_tokens, output_tokens, latency, error_code in rows:
            entry = providers.setdefault(
                str(provider),
                {
                    "requests": 0,
                    "failed": 0,
                    "cancelled": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "tokens_known": True,
                    "latency_ms_total": 0,
                    "errors": {},
                },
            )
            entry["requests"] += 1
            entry["failed"] += int(status == "failed")
            entry["cancelled"] += int(status == "cancelled")
            if input_tokens is None or output_tokens is None:
                entry["tokens_known"] = False
            else:
                entry["input_tokens"] += int(input_tokens)
                entry["output_tokens"] += int(output_tokens)
            entry["latency_ms_total"] += int(latency)
            if error_code:
                errors = entry["errors"]
                errors[str(error_code)] = errors.get(str(error_code), 0) + 1
        for entry in providers.values():
            requests = int(entry["requests"])
            entry["mean_latency_ms"] = (
                entry["latency_ms_total"] / requests if requests else 0.0
            )
            del entry["latency_ms_total"]
        return {
            "project_id": project_id,
            "providers": providers,
            "contains_payloads": False,
            "contains_credentials": False,
        }

    def close(self) -> None:
        self.db.close()


class BudgetedCompletionService:
    """Bind provider calls to budget reservation, privacy preview and diagnostics."""

    def __init__(
        self,
        backend: CompletionBackend,
        budgets: BudgetStore,
        diagnostics: UsageDiagnostics,
        egress: PrivacyEgressEngine | None = None,
    ) -> None:
        self.backend = backend
        self.budgets = budgets
        self.diagnostics = diagnostics
        self.egress = egress or PrivacyEgressEngine()

    @staticmethod
    def _usage(response: Mapping[str, Any]) -> tuple[int | None, int | None]:
        usage = response.get("usage")
        if not isinstance(usage, Mapping):
            return None, None
        input_value = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_value = usage.get("completion_tokens", usage.get("output_tokens"))
        if type(input_value) is not int or input_value < 0:
            input_value = None
        if type(output_value) is not int or output_value < 0:
            output_value = None
        return input_value, output_value

    def complete(
        self,
        *,
        project_id: str,
        provider_id: str,
        model: str,
        endpoint: str,
        prompt: str,
        project_class: str,
        item_class: str | None,
        local: bool,
        policy: EgressPolicy,
        max_tokens: int,
        approved: bool,
        redactions: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        preview = self.egress.preview(
            provider_id=provider_id,
            endpoint=endpoint,
            prompt=prompt,
            project_class=project_class,
            item_class=item_class,
            local=local,
            redactions=redactions,
        )
        if not local and not preview.may_leave_device:
            raise AIError("PERMISSION_DENIED", "Privacy policy blocks remote model egress")
        if preview.requires_approval and not approved:
            raise AIError("NEEDS_APPROVAL", "Explicit egress approval is required")
        sanitized, _ = self.egress._sanitize_text(prompt, redactions)
        reservation_limit = BudgetStore.admission_estimate(sanitized, max_tokens)
        reservation = self.budgets.reserve(project_id, reservation_limit)
        started = datetime.now(UTC)
        try:
            response = self.backend.complete(provider_id, sanitized, policy, max_tokens)
        except AIError as exc:
            self.budgets.close_reservation(reservation, actual_tokens=None, failed=True)
            latency = max(0, int((datetime.now(UTC) - started).total_seconds() * 1000))
            self.diagnostics.record(
                project_id=project_id,
                provider_id=provider_id,
                model=model,
                status="failed",
                latency_ms=latency,
                error_code=exc.code,
            )
            raise
        input_tokens, output_tokens = self._usage(response)
        actual = (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else min(reservation.token_limit, reservation_limit)
        )
        self.budgets.close_reservation(reservation, actual_tokens=actual)
        latency = max(0, int((datetime.now(UTC) - started).total_seconds() * 1000))
        self.diagnostics.record(
            project_id=project_id,
            provider_id=provider_id,
            model=model,
            status="ok",
            latency_ms=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return {
            **response,
            "privacy": {
                "destination_host": preview.destination_host,
                "payload_sha256": preview.payload_sha256,
                "effective_class": preview.effective_class,
                "redactions": preview.redactions,
            },
            "budget": {
                "reserved_tokens": reservation.token_limit,
                "actual_tokens": actual,
                "provider_usage_known": input_tokens is not None and output_tokens is not None,
            },
        }
