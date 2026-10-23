"""Verified research activity timeline derived from immutable project events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, sha256
from .storage import ProjectStore


def research_timeline(store: ProjectStore, *, limit: int = 100,
                      offset: int = 0, operation_prefix: str | None = None) -> dict[str, Any]:
    """Return a revision-consistent chronology only after validating event hashes.

    Event payloads are recorded for audit but can contain user research material;
    this read-only summary exposes only the digest and operational metadata.
    """
    require(type(limit) is int and 1 <= limit <= 1000, "Invalid timeline page size")
    require(type(offset) is int and 0 <= offset <= 1000000, "Invalid timeline offset")
    require(operation_prefix is None or (isinstance(operation_prefix, str) and
            0 < len(operation_prefix) <= 100), "Invalid operation filter")
    rows = store.conn.execute("SELECT * FROM events ORDER BY sequence").fetchall()
    predecessor = "0" * 64
    events: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        payload = row["payload_json"]
        digest = sha256(payload.encode("utf-8"))
        expected = sha256(canonical_json([row["sequence"], row["request_id"],
                                          row["operation"], row["actor"], digest,
                                          predecessor, row["timestamp"]]).encode())
        if (row["sequence"] != index or row["payload_hash"] != digest or
                row["previous_hash"] != predecessor or row["event_hash"] != expected):
            raise EvidenceError("INTEGRITY_FAILURE", "Event timeline verification failed",
                                "Inspect the project backup and run integrity diagnostics.")
        predecessor = row["event_hash"]
        if operation_prefix is None or row["operation"].startswith(operation_prefix):
            events.append({"sequence": index, "request_id": row["request_id"],
                           "operation": row["operation"], "actor": row["actor"],
                           "timestamp_utc": row["timestamp"], "payload_sha256": digest,
                           "event_sha256": expected})
    info = store.info()
    if info.revision != len(rows):
        raise EvidenceError("INTEGRITY_FAILURE", "Event count differs from revision",
                            "Restore a verified project backup.")
    selected = events[offset:offset + limit]
    return {"project_id": info.id, "revision": info.revision,
            "total": len(events), "offset": offset, "limit": limit,
            "events": selected, "verified": True,
            "last_event_sha256": predecessor,
            "format": "researchweave-timeline-v1"}


def timeline_json(report: Mapping[str, Any]) -> str:
    """Produce a deterministic, offline portable chronology export."""
    require(report.get("verified") is True, "Only verified timelines can be exported")
    return json.dumps(dict(report), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
