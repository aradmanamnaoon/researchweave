"""Opt-in reference update observations without silent metadata mutation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from .errors import EvidenceError, require
from .library import LibraryService
from .models import canonical_json, new_id, now_utc, sha256
from .storage import ProjectStore

_PROVIDERS = {"crossref", "openalex", "pubmed", "europepmc", "manual"}


def _tables_exist(store: ProjectStore) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reference_watch'"
    ).fetchone() is not None


def _ensure_tables(conn: Any) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reference_watch ("
        "reference_id TEXT PRIMARY KEY REFERENCES reference(id), "
        "provider TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reference_update_checks ("
        "id TEXT PRIMARY KEY, reference_id TEXT NOT NULL REFERENCES reference(id), "
        "provider TEXT NOT NULL, checked_at TEXT NOT NULL, observation_json TEXT NOT NULL, "
        "observation_sha256 TEXT NOT NULL, status TEXT NOT NULL, changes_json TEXT NOT NULL, "
        "retraction INTEGER NOT NULL CHECK(retraction IN (0,1)), "
        "correction INTEGER NOT NULL CHECK(correction IN (0,1)))"
    )


def _normalized_authors(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    require(isinstance(value, list) and all(isinstance(item, str) for item in value),
            "Observed authors must be a list of strings")
    return tuple(cast(list[str], value))


class ReferenceUpdateMonitor:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.library = LibraryService(store)

    def subscribe(
        self,
        reference_id: str,
        provider: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self.library.get_reference(reference_id)
        require(provider in _PROVIDERS, "Unsupported reference update provider")
        timestamp = now_utc()

        def persist(conn: Any) -> None:
            _ensure_tables(conn)
            conn.execute(
                "INSERT INTO reference_watch(reference_id,provider,enabled,created_at,updated_at) "
                "VALUES (?,?,1,?,?) ON CONFLICT(reference_id) DO UPDATE SET "
                "provider=excluded.provider,enabled=1,updated_at=excluded.updated_at",
                (reference_id, provider, timestamp, timestamp),
            )

        _, revision = self.store.mutate(
            "reference_monitor.subscribe",
            {"reference_id": reference_id, "provider": provider},
            persist,
            expected_revision=expected_revision,
        )
        return {"reference_id": reference_id, "provider": provider, "enabled": True,
                "revision": revision, "network_queries": 0}

    def unsubscribe(
        self, reference_id: str, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        require(_tables_exist(self.store), "Reference watch does not exist", "NOT_FOUND")
        row = self.store.conn.execute(
            "SELECT provider FROM reference_watch WHERE reference_id=?", (reference_id,)
        ).fetchone()
        if row is None:
            raise EvidenceError("NOT_FOUND", "Reference watch does not exist",
                                "Choose a watched reference.")

        def persist(conn: Any) -> None:
            conn.execute(
                "UPDATE reference_watch SET enabled=0,updated_at=? WHERE reference_id=?",
                (now_utc(), reference_id),
            )

        _, revision = self.store.mutate(
            "reference_monitor.unsubscribe",
            {"reference_id": reference_id},
            persist,
            expected_revision=expected_revision,
        )
        return {"reference_id": reference_id, "provider": row["provider"], "enabled": False,
                "revision": revision}

    def watches(self) -> list[dict[str, Any]]:
        if not _tables_exist(self.store):
            return []
        return [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT * FROM reference_watch ORDER BY created_at,reference_id"
            )
        ]

    def watched_provider(self, reference_id: str) -> str:
        """Return the explicitly enabled provider for a watched reference."""
        require(_tables_exist(self.store), "Reference is not opted in for update checks",
                "NEEDS_APPROVAL")
        row = self.store.conn.execute(
            "SELECT provider,enabled FROM reference_watch WHERE reference_id=?",
            (reference_id,),
        ).fetchone()
        require(row is not None and bool(row["enabled"]),
                "Reference is not opted in for update checks", "NEEDS_APPROVAL")
        return str(row["provider"])

    def due_watches(self, *, now: str | None = None,
                    interval_hours: int = 168, limit: int = 100) -> dict[str, Any]:
        """Return opt-in watches due for a host-scheduled or manual metadata check.

        This method is deliberately read-only and performs no provider access.
        The trusted host decides whether and when to execute a network lookup.
        """
        require(type(interval_hours) is int and 1 <= interval_hours <= 24 * 365,
                "Reference watch interval must be between 1 hour and 1 year")
        require(type(limit) is int and 1 <= limit <= 1000,
                "Reference watch result limit must be 1..1000")
        instant_text = now or now_utc()
        try:
            instant = datetime.fromisoformat(instant_text)
        except ValueError as exc:
            raise EvidenceError("INVALID_INPUT", "Invalid watch clock timestamp",
                                "Use an ISO-8601 UTC timestamp.") from exc
        require(instant.tzinfo is not None, "Reference watch clock must include timezone")
        instant = instant.astimezone(UTC)
        if not _tables_exist(self.store):
            return {"checked_at": instant.isoformat(), "interval_hours": interval_hours,
                    "records": [], "count": 0, "network_queries": 0}
        due: list[dict[str, Any]] = []
        for row in self.store.conn.execute(
                "SELECT * FROM reference_watch WHERE enabled=1 ORDER BY updated_at,reference_id"):
            updated = datetime.fromisoformat(str(row["updated_at"]))
            require(updated.tzinfo is not None, "Stored reference watch timestamp is invalid",
                    "INTEGRITY_FAILURE")
            next_due = updated.astimezone(UTC) + timedelta(hours=interval_hours)
            if next_due <= instant:
                due.append({"reference_id": row["reference_id"],
                            "provider": row["provider"],
                            "last_checked_or_updated_at": row["updated_at"],
                            "next_due_at": next_due.isoformat(),
                            "enabled": True})
            if len(due) >= limit:
                break
        return {"checked_at": instant.isoformat(), "interval_hours": interval_hours,
                "records": due, "count": len(due), "network_queries": 0,
                "requires_explicit_network_execution": True}

    def record_observation(
        self,
        reference_id: str,
        provider: str,
        observed: Mapping[str, Any],
        *,
        checked_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(_tables_exist(self.store), "Reference is not opted in for update checks",
                "NEEDS_APPROVAL")
        watch = self.store.conn.execute(
            "SELECT * FROM reference_watch WHERE reference_id=?", (reference_id,)
        ).fetchone()
        require(watch is not None and bool(watch["enabled"]),
                "Reference is not opted in for update checks", "NEEDS_APPROVAL")
        require(provider == watch["provider"] and provider in _PROVIDERS,
                "Observation provider does not match the opt-in watch", "CONFLICT")
        reference = self.library.get_reference(reference_id)
        require(len(observed) <= 100, "Observed metadata has too many fields", "RESOURCE_LIMIT")
        allowed = {
            "title", "year", "doi", "authors", "is_retracted", "is_corrected",
            "correction_of", "retraction_notice", "provider_record_id",
            "catalog_presence", "provider_response_sha256",
        }
        require(set(observed).issubset(allowed), "Observed metadata contains unsupported fields")
        title = observed.get("title")
        year = observed.get("year")
        doi = observed.get("doi")
        authors = _normalized_authors(observed.get("authors"))
        require(title is None or isinstance(title, str), "Observed title must be text")
        require(year is None or type(year) is int, "Observed year must be an integer")
        require(doi is None or isinstance(doi, str), "Observed DOI must be text")
        require(isinstance(observed.get("is_retracted", False), bool),
                "Retraction signal must be boolean")
        require(isinstance(observed.get("is_corrected", False), bool),
                "Correction signal must be boolean")
        catalog_presence = observed.get("catalog_presence")
        require(catalog_presence is None or catalog_presence in {"reported", "not_observed"},
                "Invalid catalog presence status")
        response_hashes = observed.get("provider_response_sha256")
        require(response_hashes is None or (
            isinstance(response_hashes, list)
            and len(response_hashes) <= 5
            and all(isinstance(value, str) and len(value) == 64 for value in response_hashes)
        ), "Invalid provider response provenance hashes")

        changes: list[dict[str, Any]] = []
        if title is not None and title != reference.title:
            changes.append({"field": "title", "current": reference.title, "observed": title})
        if year is not None and year != reference.year:
            changes.append({"field": "year", "current": reference.year, "observed": year})
        if doi is not None and doi != reference.doi:
            changes.append({"field": "doi", "current": reference.doi, "observed": doi})
        if authors is not None and authors != reference.authors:
            changes.append({
                "field": "authors",
                "current": list(reference.authors),
                "observed": list(authors),
            })
        identifier_conflict = bool(reference.doi and doi and doi != reference.doi)
        retracted = bool(observed.get("is_retracted", False))
        corrected = bool(observed.get("is_corrected", False))
        status = (
            "identity_mismatch" if identifier_conflict
            else "retraction_reported" if retracted
            else "correction_reported" if corrected
            else "doi_not_observed" if catalog_presence == "not_observed"
            else "metadata_changed" if changes
            else "no_change"
        )
        timestamp = checked_at or now_utc()
        payload = canonical_json(dict(observed))
        check_id = new_id()

        def persist(conn: Any) -> None:
            conn.execute(
                "INSERT INTO reference_update_checks VALUES (?,?,?,?,?,?,?,?,?,?)",
                (check_id, reference_id, provider, timestamp, payload,
                 sha256(payload.encode("utf-8")), status, canonical_json(changes),
                 int(retracted), int(corrected)),
            )
            conn.execute(
                "UPDATE reference_watch SET updated_at=? WHERE reference_id=?",
                (timestamp, reference_id),
            )

        _, revision = self.store.mutate(
            "reference_monitor.record_observation",
            {
                "check_id": check_id,
                "reference_id": reference_id,
                "provider": provider,
                "observation_sha256": sha256(payload.encode("utf-8")),
                "status": status,
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "check_id": check_id,
            "reference_id": reference_id,
            "provider": provider,
            "checked_at": timestamp,
            "status": status,
            "changes": changes,
            "retraction_reported": retracted,
            "correction_reported": corrected,
            "metadata_updated": False,
            "requires_human_confirmation": bool(changes or retracted or corrected),
            "revision": revision,
        }

    def history(self, reference_id: str) -> list[dict[str, Any]]:
        if not _tables_exist(self.store):
            return []
        rows = self.store.conn.execute(
            "SELECT * FROM reference_update_checks WHERE reference_id=? "
            "ORDER BY checked_at,id",
            (reference_id,),
        ).fetchall()
        return [
            {
                "check_id": row["id"],
                "reference_id": row["reference_id"],
                "provider": row["provider"],
                "checked_at": row["checked_at"],
                "observation": json.loads(row["observation_json"]),
                "observation_sha256": row["observation_sha256"],
                "status": row["status"],
                "changes": json.loads(row["changes_json"]),
                "retraction_reported": bool(row["retraction"]),
                "correction_reported": bool(row["correction"]),
                "metadata_updated": False,
            }
            for row in rows
        ]
