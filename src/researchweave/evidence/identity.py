"""Reference identity verification from explicit provider metadata observations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

from .bibliography import normalize_doi, normalize_title
from .errors import require
from .library import LibraryService
from .models import canonical_json, new_id, now_utc, sha256
from .storage import ProjectStore

PROVIDERS = {"crossref", "openalex", "pubmed", "europepmc", "manual"}


def _authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def compare_identity(
    reference: Any, provider: str, observation: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare one normalized provider record without inferring unsupported scientific validity."""
    require(provider in PROVIDERS, "Unsupported identity provider", "UNSUPPORTED_FORMAT")
    require(len(observation) <= 100, "Provider observation is too large", "RESOURCE_LIMIT")
    observed_title = observation.get("title")
    observed_year = observation.get("year")
    observed_doi_raw = observation.get("doi")
    observed_authors = _authors(observation.get("authors"))
    require(observed_title is None or isinstance(observed_title, str),
            "Provider title must be text")
    require(observed_year is None or type(observed_year) is int,
            "Provider year must be an integer")
    require(observed_doi_raw is None or isinstance(observed_doi_raw, str),
            "Provider DOI must be text")

    local_doi = normalize_doi(reference.doi)
    observed_doi = normalize_doi(observed_doi_raw if isinstance(observed_doi_raw, str) else None)
    title_similarity: float | None = None
    if isinstance(observed_title, str) and observed_title.strip():
        title_similarity = SequenceMatcher(
            None, normalize_title(reference.title), normalize_title(observed_title)
        ).ratio()
    year_match = (
        None if reference.year is None or observed_year is None
        else reference.year == observed_year
    )
    doi_match = None if local_doi is None or observed_doi is None else local_doi == observed_doi
    author_overlap: float | None = None
    if reference.authors and observed_authors:
        local = {normalize_title(author) for author in reference.authors}
        remote = {normalize_title(author) for author in observed_authors}
        author_overlap = len(local & remote) / max(len(local), len(remote))

    mismatches: list[str] = []
    if doi_match is False:
        mismatches.append("doi")
    if title_similarity is not None and title_similarity < 0.85:
        mismatches.append("title")
    if year_match is False:
        mismatches.append("year")
    if author_overlap is not None and author_overlap == 0:
        mismatches.append("authors")

    if local_doi is None:
        existence = "unknown"
        identity = "insufficient_identifier"
    elif observed_doi is None:
        existence = "unknown"
        identity = "provider_record_without_matching_doi"
    elif doi_match is False:
        existence = "unknown"
        identity = "mismatch"
    elif mismatches:
        existence = "confirmed_by_provider_observation"
        identity = "metadata_mismatch"
    elif title_similarity is not None and title_similarity >= 0.95:
        existence = "confirmed_by_provider_observation"
        identity = "exact"
    else:
        existence = "confirmed_by_provider_observation"
        identity = "probable"

    return {
        "provider": provider,
        "reference_id": reference.id,
        "doi_syntax": "valid" if local_doi else "absent_or_invalid",
        "doi": local_doi,
        "doi_existence": existence,
        "identity": identity,
        "doi_match": doi_match,
        "title_similarity": title_similarity,
        "year_match": year_match,
        "author_overlap": author_overlap,
        "mismatches": mismatches,
        "retraction_status": "unknown",
        "correction_status": "unknown",
        "claim_support": "unassessed",
        "scientific_claims_verified": False,
        "provider_record_id": observation.get("provider_id"),
    }


class IdentityService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.library = LibraryService(store)

    @staticmethod
    def _table(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS reference_identity_checks ("
            "id TEXT PRIMARY KEY, reference_id TEXT NOT NULL REFERENCES reference(id), "
            "provider TEXT NOT NULL, observation_json TEXT NOT NULL, "
            "observation_sha256 TEXT NOT NULL, result_json TEXT NOT NULL, "
            "checked_at TEXT NOT NULL)"
        )

    def record(
        self,
        reference_id: str,
        provider: str,
        observation: Mapping[str, Any],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        reference = self.library.get_reference(reference_id)
        result = compare_identity(reference, provider, observation)
        observation_json = canonical_json(dict(observation))
        result_json = canonical_json(result)
        check_id = new_id()

        def persist(conn: Any) -> None:
            self._table(conn)
            conn.execute(
                "INSERT INTO reference_identity_checks VALUES (?,?,?,?,?,?,?)",
                (
                    check_id,
                    reference_id,
                    provider,
                    observation_json,
                    sha256(observation_json.encode()),
                    result_json,
                    now_utc(),
                ),
            )

        _, revision = self.store.mutate(
            "reference.identity_record",
            {
                "check_id": check_id,
                "reference_id": reference_id,
                "provider": provider,
                "observation_sha256": sha256(observation_json.encode()),
                "identity": result["identity"],
            },
            persist,
            expected_revision=expected_revision,
        )
        return {**result, "check_id": check_id, "revision": revision}

    def history(self, reference_id: str) -> list[dict[str, Any]]:
        exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='reference_identity_checks'"
        ).fetchone()
        if exists is None:
            return []
        return [
            {
                "check_id": row["id"],
                "reference_id": row["reference_id"],
                "provider": row["provider"],
                "observation": json.loads(row["observation_json"]),
                "observation_sha256": row["observation_sha256"],
                "result": json.loads(row["result_json"]),
                "checked_at": row["checked_at"],
            }
            for row in self.store.conn.execute(
                "SELECT * FROM reference_identity_checks WHERE reference_id=? "
                "ORDER BY checked_at,id",
                (reference_id,),
            )
        ]
