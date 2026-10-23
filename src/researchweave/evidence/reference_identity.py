"""Independent bibliographic identity comparisons with explicit uncertainty.

DOI syntax, provider-reported existence, metadata identity and scientific claim
support are distinct facts. Only a permitted provider lookup can attest that a
public catalog returned an identifier; a local metadata comparison cannot.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from .bibliography import normalize_doi, normalize_title
from .errors import require
from .models import Reference


def _person(value: str) -> str:
    """Conservative surname comparison for structured/unstructured author names."""
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    if "," in normalized:
        normalized = normalized.split(",", 1)[0]
    else:
        tokens = re.findall(r"[^\W_]+", normalized)
        normalized = tokens[-1] if tokens else ""
    return normalize_title(normalized)


def _authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [name for element in value[:100] if isinstance(element, str)
            if (name := _person(element))]


def compare_reference(record: Reference, candidate: Mapping[str, Any], *,
                      trusted_catalog_response: bool = False,
                      provider: str | None = None,
                      response_sha256: Sequence[str] = ()) -> dict[str, Any]:
    """Compare identifier and metadata without inferring evidence or paper access.

    Catalog trust is granted by an independently permissioned transport, never
    by data in `candidate`. The result says what the *catalog reports*, not
    that the article was actually read or that its conclusions are supported.
    """
    require(len(candidate) <= 120, "Excessive provider metadata fields", "RESOURCE_LIMIT")
    identifier = normalize_doi(record.doi)
    raw_candidate_doi = candidate.get("doi")
    require(raw_candidate_doi is None or isinstance(raw_candidate_doi, str),
            "Candidate DOI must be text")
    candidate_doi = normalize_doi(raw_candidate_doi)
    details: list[dict[str, Any]] = []
    if identifier is None:
        details.append({"field": "doi", "status": "reference_missing_or_invalid"})
    elif candidate_doi is None:
        details.append({"field": "doi", "status": "candidate_missing_or_invalid"})
    elif identifier != candidate_doi:
        details.append({"field": "doi", "status": "different_identifier",
                        "local": identifier, "candidate": candidate_doi})
    else:
        details.append({"field": "doi", "status": "exact"})

    title = candidate.get("title")
    if not isinstance(title, str) or not title.strip() or not record.title.strip():
        details.append({"field": "title", "status": "unknown"})
    else:
        details.append({"field": "title", "status": "exact" if
                        normalize_title(title) == normalize_title(record.title)
                        else "mismatch", "local": record.title, "candidate": title})

    year = candidate.get("year")
    if year is None or record.year is None:
        details.append({"field": "year", "status": "unknown"})
    elif type(year) is int and 1500 <= year <= 2200:
        details.append({"field": "year", "status": "exact" if
                        record.year == year else "mismatch", "local": record.year,
                        "candidate": year})
    else:
        details.append({"field": "year", "status": "invalid_provider_value"})

    authors = _authors(candidate.get("authors"))
    first = _person(record.authors[0]) if record.authors else ""
    if not first or not authors:
        details.append({"field": "first_author", "status": "unknown"})
    else:
        details.append({"field": "first_author", "status": "exact" if
                        first == authors[0] else "mismatch",
                        "local": first, "candidate": authors[0]})

    statuses = {entry["field"]: entry["status"] for entry in details}
    bad = {"different_identifier", "mismatch", "invalid_provider_value"}
    has_mismatch = bool(set(statuses.values()) & bad)
    if has_mismatch:
        identity = "metadata_mismatch"
    elif statuses["doi"] == "exact" and statuses["title"] == "exact" and (
            statuses["year"] == "exact" or statuses["first_author"] == "exact"):
        identity = "bibliographic_consistency"
    else:
        identity = "insufficient_metadata"

    retracted = candidate.get("is_retracted")
    corrected = candidate.get("is_corrected")
    require(retracted is None or isinstance(retracted, bool),
            "Retraction status must be boolean when supplied")
    require(corrected is None or isinstance(corrected, bool),
            "Correction status must be boolean when supplied")
    signals = {
        "retraction": "provider_reported" if trusted_catalog_response and retracted else
        "unverified_local_signal" if retracted else "unknown",
        "correction": "provider_reported" if trusted_catalog_response and corrected else
        "unverified_local_signal" if corrected else "unknown",
    }
    return {
        "reference_id": record.id,
        "doi": identifier,
        "doi_syntax": "valid" if identifier else "absent_or_invalid",
        "candidate_doi": candidate_doi,
        "catalog_presence": "reported" if trusted_catalog_response and candidate_doi else "unknown",
        "identity": identity,
        "bibliographic_consistency": identity == "bibliographic_consistency",
        "details": details,
        "retraction_and_correction": signals,
        "scientific_claim_support": "unassessed",
        "paper_read": False,
        "provider": provider if trusted_catalog_response else None,
        "response_sha256": list(response_sha256) if trusted_catalog_response else [],
        "verified_scientific_claims": False,
        "next_action": (
            "Resolve metadata differences using original publisher and correction notices."
            if has_mismatch else
            "Confirm publication identity and any editorial notices using original sources."
        ),
    }


def reconcile_catalog_candidates(reference: Reference, records: Sequence[Mapping[str, Any]], *,
                                 provider: str, response_sha256: Sequence[str]) -> dict[str, Any]:
    """Choose only exact DOI candidates; conflicting catalog responses remain visible."""
    require(0 < len(provider) <= 40 and bool(provider.strip()), "Provider name required")
    require(len(records) <= 50, "Too many catalog candidates", "RESOURCE_LIMIT")
    require(len(response_sha256) <= 5 and all(
        isinstance(hash_value, str) and re.fullmatch(r"[0-9a-f]{64}", hash_value)
        for hash_value in response_sha256), "Invalid catalog provenance hash")
    doi = normalize_doi(reference.doi)
    matches = [candidate for candidate in records
               if doi is not None and normalize_doi(candidate.get("doi") if
               isinstance(candidate.get("doi"), str) else None) == doi]
    results = [compare_reference(reference, candidate, trusted_catalog_response=True,
                                 provider=provider, response_sha256=response_sha256)
               for candidate in matches]
    if not results:
        return {"reference_id": reference.id, "catalog_presence": "not_observed",
                "identity": "unknown", "verified_scientific_claims": False,
                "provider": provider, "response_sha256": list(response_sha256),
                "candidates": [], "warning": "Search results cannot prove DOI nonexistence."}
    result_types = {result["identity"] for result in results}
    return {"reference_id": reference.id, "catalog_presence": "reported",
            "identity": results[0]["identity"] if len(results) == 1 else "ambiguous",
            "verified_scientific_claims": False, "provider": provider,
            "response_sha256": list(response_sha256), "candidates": results,
            "warning": "Conflicting catalog records require review" if
            len(result_types) > 1 or len(results) > 1 else
            "Catalog metadata does not establish claim support or full-text access."}
