from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.citation_graph import CitationGraphService
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.identity import IdentityService, compare_identity
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore


def _refs(store: ProjectStore) -> tuple[str, str]:
    imported = LibraryService(store).import_bibliography(
        b"@article{a,title={Exact Study},author={Doe, Ada},year={2024},doi={10.1000/exact}}\n"
        b"@article{b,title={Citing Study},author={Roe, Bea},year={2025},doi={10.1000/citing}}",
        "bibtex",
    )
    return imported["references"][0]["id"], imported["references"][1]["id"]


def test_identity_exact_mismatch_persistence_and_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Identity", "Which citation is this?", "exploratory") as store:
        exact_id, _ = _refs(store)
        reference = LibraryService(store).get_reference(exact_id)
        exact = compare_identity(reference, "crossref", {
            "title": "Exact Study",
            "authors": ["Doe, Ada"],
            "year": 2024,
            "doi": "https://doi.org/10.1000/EXACT",
            "provider_id": "10.1000/exact",
        })
        assert exact["identity"] == "exact"
        assert exact["claim_support"] == "unassessed"
        service = IdentityService(store)
        recorded = service.record(exact_id, "crossref", {
            "title": "Different work",
            "authors": ["Other, Person"],
            "year": 2020,
            "doi": "10.1000/exact",
        })
        assert recorded["identity"] == "metadata_mismatch"
        assert set(recorded["mismatches"]) >= {"title", "year", "authors"}
    with ProjectStore(root) as reopened:
        history = IdentityService(reopened).history(exact_id)
        assert history[0]["result"]["identity"] == "metadata_mismatch"
        assert reopened.audit()["ok"]


def test_identity_invalid_doi_never_becomes_verified(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "Identity", "Question", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{x,title={Unknown},author={Doe, Ada},doi={10.}}", "bibtex"
        )
        reference = LibraryService(store).get_reference(imported["references"][0]["id"])
        result = compare_identity(reference, "manual", {
            "title": "Unknown", "doi": "10.1000/other"
        })
        assert result["doi_syntax"] == "absent_or_invalid"
        assert result["doi_existence"] == "unknown"
        assert result["scientific_claims_verified"] is False


def test_citation_graph_requires_explicit_existing_references_and_reopens(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Citations", "What cites what?", "exploratory") as store:
        cited_id, citing_id = _refs(store)
        graph = CitationGraphService(store)
        added = graph.add(
            citing_id,
            cited_id,
            "Confirmed from imported reference list",
            "reviewer",
        )
        assert added["read_status_inferred"] is False
        with pytest.raises(EvidenceError) as duplicate:
            graph.add(citing_id, cited_id, "Again", "reviewer")
        assert duplicate.value.code == "CONFLICT"
        with pytest.raises(EvidenceError) as missing:
            graph.add(citing_id, "missing", "Imported list", "reviewer")
        assert missing.value.code == "NOT_FOUND"
    with ProjectStore(root) as reopened:
        exported = CitationGraphService(reopened).graph()
        assert len(exported["edges"]) == 1
        assert exported["orphan_edges"] == []
        assert exported["read_status_inferred"] is False
        assert reopened.audit()["ok"]
