"""Explicit reversible duplicate decisions preserve individual imported records."""

import base64
import sqlite3

from researchweave.evidence import build_evidence_facade


def test_merge_unmerge_preserves_raw_metadata_and_reopens(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute("project.create", {"title": "Library",
        "question": "What records match?", "design": "systematic_review"}, {})
    project_id = created["data"]["project_id"]
    raw = ("@article{one,title={Same Label},author={Doe, Jane},year={2021},"
           "doi={10.1234/one}}\n@article{two,title={Same Label},"
           "author={Roe, John},year={2022},doi={10.1234/two}}")
    imported = facade.execute("library.bibliography_import", {
        "project_id": project_id, "format": "bibtex",
        "data_base64": base64.b64encode(raw.encode()).decode()}, {})
    assert imported["status"] == "ok", imported
    left, right = [r["id"] for r in imported["data"]["references"]]
    assert len(left) == len(right) == 36
    assert facade.execute("reference.merge", {
        "project_id": project_id, "canonical_id": left,
        "duplicate_id": right, "rationale": "Same work confirmed by reviewer"},
        {"expected_revision": imported["data"]["revision"]})["status"] == "ok"
    reopened = build_evidence_facade(tmp_path, allow_local_writes=True)
    with sqlite3.connect(tmp_path / project_id / "data" / "project.sqlite") as conn:
        alias = conn.execute("SELECT original_id,canonical_id FROM reference_alias").fetchone()
        assert alias == (right, left)
        assert conn.execute("SELECT COUNT(*) FROM reference").fetchone()[0] == 2
    conflict = reopened.execute("reference.merge", {
        "project_id": project_id, "canonical_id": right,
        "duplicate_id": left, "rationale": "Attempt cycle"}, {})
    assert conflict["status"] == "failed" and conflict["error"]["code"] == "CONFLICT"
    reverted = reopened.execute("reference.unmerge", {
        "project_id": project_id, "duplicate_id": right, "rationale": "Identity disproven"}, {})
    assert reverted["status"] == "ok", reverted
    with sqlite3.connect(tmp_path / project_id / "data" / "project.sqlite") as conn:
        assert conn.execute("SELECT COUNT(*) FROM reference_alias").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM reference").fetchone()[0] == 2
    assert reopened.execute("project.integrity", {"project_id": project_id}, {})[
        "data"]["ok"]


def test_merge_requires_review_and_valid_ids(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute("project.create", {"title": "Library",
        "question": "What records match?", "design": "exploratory"}, {})
    project_id = created["data"]["project_id"]
    denied = facade.execute("reference.merge", {
        "project_id": project_id, "canonical_id": "first",
        "duplicate_id": "second", "rationale": ""}, {})
    assert denied["status"] == "failed"
    assert denied["error"]["code"] == "INVALID_INPUT"
    assert facade.execute("project.open", {"project_id": project_id}, {})[
        "data"]["revision"] == 0
