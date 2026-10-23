"""Versioned interchange types, identifiers and deterministic encoding."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

SCHEMA_VERSION = 1
ARCHIVE_VERSION = "1.0.0"


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def new_id() -> str:
    return str(uuid4())


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class ProjectInfo:
    id: str
    title: str
    question: str
    design: str
    locale: str
    privacy: Literal["private", "restricted", "public"] = "private"
    revision: int = 0


@dataclass(frozen=True, slots=True)
class Reference:
    id: str
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    doi: str | None = None
    kind: str = "article"
    source_format: str = "manual"
    raw: str = ""
    metadata_status: str = "unverified"
    provenance: dict[str, str] = field(default_factory=dict)

    def as_wire(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["authors"] = list(self.authors)
        return payload


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    id: str
    document_id: str
    quote: str
    start: int
    end: int
    page: int | None
    text_hash: str
    verified: bool


@dataclass(frozen=True, slots=True)
class ImportReceipt:
    read: int
    imported: int
    skipped: int
    failed: int
    source_sha256: str
    warnings: tuple[str, ...] = ()

    def as_wire(self) -> dict[str, Any]:
        return asdict(self)
