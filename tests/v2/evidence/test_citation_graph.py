"""Persistent citation relationships require documentary evidence and human review."""

import base64
import sqlite3

from researchweave.evidence import build_evidence_facade


def _call(facade, operation, **args):
    result = facade.execute(operation, args, {})
    assert result["status"] == "ok", result
    return result["data"]


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def test_anchored_citation_link_reopen_export_revoke(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    pid = _call(facade, "project.create", title="Citations",
                question="Which studies cite one another?", design="observational")["project_id"]
    original = _call(facade, "library.bibliography_import", project_id=pid,
                     format="bibtex", data_base64=_b64(
                         "@article{one,title={Synthetic First},author={Doe, Ada},year={2024}}"
                         "@article{two,title={Synthetic Second},author={Roe, Ada},year={2022}}"))
    a, b = [item["id"] for item in original["references"]]
    empty = _call(facade, "reference.citation_graph", project_id=pid)
    assert empty["edges"] == [] and not empty["paper_read_inferred"]
    source = _call(facade, "library.import", project_id=pid, title="Source passage",
                   media_type="text/plain", data_base64=_b64(
                       "Synthetic Second was discussed in this work."))
    anchor = _call(facade, "evidence.anchor", project_id=pid,
                   source_id=source["source_id"], quote="Synthetic Second", start=0, end=16)
    assert anchor["quote_verified"]
    linked = _call(facade, "reference.citation_link", project_id=pid, citing_id=a,
                   cited_id=b, anchor_id=anchor["anchor_id"], actor="Reviewer Ada",
                   rationale="The verified source passage names the cited record.")
    assert linked["status"] == "human_attested_exact_anchor"
    reopened = build_evidence_facade(tmp_path, allow_local_writes=True)
    graph = _call(reopened, "reference.citation_graph", project_id=pid)
    assert len(graph["nodes"]) == 2 and graph["active_edges"] == 1
    assert graph["verified"] and not graph["paper_read_inferred"]
    graphml = _call(reopened, "reference.citation_graphml", project_id=pid)
    assert graphml["text"].count("<edge ") == 1
    repeated = reopened.execute("reference.citation_link", {
        "project_id": pid, "citing_id": a, "cited_id": b,
        "anchor_id": anchor["anchor_id"], "actor": "Reviewer Ada",
        "rationale": "Duplicated mapping"}, {})
    assert repeated["error"]["code"] == "CONFLICT"
    _call(reopened, "reference.citation_revoke", project_id=pid, edge_id=linked["id"],
          actor="Reviewer Ada", rationale="Corrected after source inspection")
    assert _call(reopened, "reference.citation_graph", project_id=pid)["active_edges"] == 0
    all_edges = _call(reopened, "reference.citation_graph", project_id=pid,
                      include_revoked=True)["edges"]
    assert all_edges[0]["revoked_at"] is not None
    assert _call(reopened, "project.integrity", project_id=pid)["ok"]


def test_missing_anchor_and_tampering_do_not_certify_citations(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    pid = _call(facade, "project.create", title="Citations",
                question="Do links need evidence?", design="exploratory")["project_id"]
    bibliography = _call(facade, "library.bibliography_import", project_id=pid,
                         format="ris", data_base64=_b64(
                             "TY  - JOUR\nTI  - A\nER  - \n"
                             "TY  - JOUR\nTI  - B\nER  - \n"))
    a, b = [record["id"] for record in bibliography["references"]]
    rejected = facade.execute("reference.citation_link", {
        "project_id": pid, "citing_id": a, "cited_id": b,
        "anchor_id": "made-up", "actor": "Researcher", "rationale": "No proof"}, {})
    assert rejected["error"]["code"] == "INTEGRITY_FAILURE"
    assert _call(facade, "reference.citation_graph", project_id=pid)["active_edges"] == 0
    source = _call(facade, "library.import", project_id=pid, title="Source",
                   media_type="text/plain", data_base64=_b64("B is cited."))
    anchor = _call(facade, "evidence.anchor", project_id=pid,
                   source_id=source["source_id"], quote="B", start=0, end=1)
    _call(facade, "reference.citation_link", project_id=pid, citing_id=a,
          cited_id=b, anchor_id=anchor["anchor_id"], actor="Researcher",
          rationale="Human verified source relation")
    with sqlite3.connect(tmp_path / pid / "data" / "project.sqlite") as conn:
        conn.execute("UPDATE anchors SET quote='tampered'")
    corrupted = facade.execute("reference.citation_graph", {"project_id": pid}, {})
    assert corrupted["error"]["code"] == "INTEGRITY_FAILURE"
