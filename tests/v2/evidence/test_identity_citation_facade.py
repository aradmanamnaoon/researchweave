from __future__ import annotations

import base64
import json
from pathlib import Path

from researchweave.evidence import build_evidence_facade


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode("ascii")


def _call(facade, operation: str, **arguments):
    result = facade.execute(operation, arguments, {})
    assert result["status"] == "ok", json.dumps(result, ensure_ascii=False)
    return result["data"]


def test_identity_and_citation_graph_through_public_facade(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    project_id = _call(
        facade,
        "project.create",
        title="Identity graph",
        question="Which record is which?",
        design="exploratory",
    )["project_id"]
    imported = _call(
        facade,
        "library.bibliography_import",
        project_id=project_id,
        format="bibtex",
        data_base64=_b64(
            "@article{a,title={Exact Study},author={Doe, Ada},year={2024},"
            "doi={10.1000/exact}}\n"
            "@article{b,title={Citing Study},author={Roe, Bea},year={2025},"
            "doi={10.1000/citing}}"
        ),
    )
    cited_id, citing_id = [record["id"] for record in imported["references"]]
    identity = _call(
        facade,
        "reference.identity_record",
        project_id=project_id,
        reference_id=cited_id,
        provider="crossref",
        observed={
            "title": "Exact Study",
            "authors": ["Doe, Ada"],
            "year": 2024,
            "doi": "10.1000/exact",
            "provider_id": "10.1000/exact",
        },
    )
    assert identity["identity"] == "exact"
    assert identity["scientific_claims_verified"] is False
    _call(
        facade,
        "reference.citation_add",
        project_id=project_id,
        citing_reference_id=citing_id,
        cited_reference_id=cited_id,
        provenance="Confirmed from imported bibliography",
        confirmed_by="reviewer",
    )

    reopened = build_evidence_facade(tmp_path)
    history = _call(
        reopened,
        "reference.identity_history",
        project_id=project_id,
        reference_id=cited_id,
    )
    assert history["records"][0]["result"]["identity"] == "exact"
    graph = _call(reopened, "reference.citation_graph", project_id=project_id)
    assert len(graph["edges"]) == 1
    assert graph["read_status_inferred"] is False
