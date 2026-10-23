"""Offline scientific identity checks distinguish syntax and scientific evidence."""

import base64
import json

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.discovery import HTTPResponse
from researchweave.evidence.models import Reference
from researchweave.evidence.reference_identity import (
    compare_reference,
    reconcile_catalog_candidates,
)


def _reference() -> Reference:
    return Reference(id="record-1", title="Study of memory", authors=("Doe, Ada",),
                     year=2024, doi="10.1000/abc")


def test_exact_identifier_consistency_without_invented_claim_support():
    original = _reference()
    candidate = {"doi": "https://doi.org/10.1000/ABC", "title": "Study of Memory",
                 "authors": ["Ada Doe"], "year": 2024, "is_retracted": True}
    local = compare_reference(original, candidate)
    assert local["identity"] == "bibliographic_consistency"
    assert local["catalog_presence"] == "unknown"
    assert local["retraction_and_correction"]["retraction"] == "unverified_local_signal"
    assert not local["verified_scientific_claims"] and not local["paper_read"]
    catalog = reconcile_catalog_candidates(original, [candidate], provider="crossref",
                                           response_sha256=["f" * 64])
    assert catalog["identity"] == "bibliographic_consistency"
    assert catalog["catalog_presence"] == "reported"
    assert catalog["candidates"][0]["retraction_and_correction"]["retraction"] == (
        "provider_reported")
    assert catalog["candidates"][0]["response_sha256"] == ["f" * 64]


def test_conflicting_or_unobserved_doi_does_not_become_verified():
    reference = _reference()
    mismatched = compare_reference(reference, {"doi": "10.1000/different",
                                               "title": "Study of memory", "year": 2024})
    assert mismatched["identity"] == "metadata_mismatch"
    assert "different_identifier" in {field["status"] for field in mismatched["details"]}
    unobserved = reconcile_catalog_candidates(reference,
        [{"doi": "10.1000/different", "title": "Study of memory"}],
        provider="openalex", response_sha256=[])
    assert unobserved["identity"] == "unknown"
    assert unobserved["catalog_presence"] == "not_observed"


def test_facade_offline_refusal_local_comparison_and_network_provenance(tmp_path):
    class Transport:
        def get(self, url, *, headers, timeout):
            assert "crossref.org" in url
            assert "/works/10.1000%2Fabc" in url
            return HTTPResponse(200, json.dumps({"message": {
                "DOI": "10.1000/abc", "title": ["Study of memory"],
                "author": [{"given": "Ada", "family": "Doe"}],
                "published": {"date-parts": [[2024]]},
                "relation": {"is-corrected-by": [{"id": "10.1000/correction"}]},
            }}).encode())

    workspace = tmp_path / "projects"
    facade = build_evidence_facade(workspace, allow_local_writes=True)
    created = facade.execute("project.create", {
        "title": "DOI", "question": "Is this the same record?", "design": "exploratory"}, {})
    project_id = created["data"]["project_id"]
    raw = ("@article{a,title={Study of memory},author={Doe, Ada},"
           "year={2024},doi={10.1000/abc}}")
    imported = facade.execute("library.bibliography_import", {
        "project_id": project_id, "format": "bibtex",
        "data_base64": base64.b64encode(raw.encode()).decode()}, {})
    reference_id = imported["data"]["references"][0]["id"]
    local = facade.execute("reference.compare_metadata", {
        "project_id": project_id, "reference_id": reference_id,
        "candidate": {"doi": "10.1000/abc", "title": "Different work"}}, {})
    assert local["data"]["identity"] == "metadata_mismatch"
    offline = facade.execute("reference.provider_identity", {
        "project_id": project_id, "reference_id": reference_id,
        "provider": "crossref"}, {})
    assert offline["error"]["code"] == "OFFLINE_DENIED"

    permitted = build_evidence_facade(workspace, allow_remote_queries=True,
                                      metadata_transport=Transport())
    checked = permitted.execute("reference.provider_identity", {
        "project_id": project_id, "reference_id": reference_id,
        "provider": "crossref"}, {})
    assert checked["status"] == "ok", checked
    assert checked["data"]["identity"] == "bibliographic_consistency"
    assert checked["data"]["catalog_presence"] == "reported"
    assert checked["data"]["candidates"][0]["retraction_and_correction"][
        "correction"] == "provider_reported"
    assert not checked["data"]["verified_scientific_claims"]
    assert facade.execute("project.open", {"project_id": project_id}, {})[
        "data"]["revision"] == 1


def test_provider_lookup_filters_nearby_but_wrong_dois():
    class Transport:
        def get(self, url, *, headers, timeout):
            assert "/works/10.1000%2Fabc" in url
            return HTTPResponse(200, json.dumps({"message": {
                "DOI": "10.1000/abc", "title": ["Requested record"],
                "relation": {"is-retracted-by": [{"id": "10.1000/retraction"}]},
            }}).encode())

    from researchweave.evidence.discovery import CatalogClient

    result = CatalogClient(Transport(), offline=False).lookup_doi("crossref", "10.1000/ABC")
    assert result["catalog_presence"] == "reported"
    assert len(result["records"]) == 1
    assert result["records"][0]["doi"] == "10.1000/abc"
    assert result["records"][0]["is_retracted"] is True
    assert not result["scientific_claims_verified"] and not result["paper_read"]
