"""Offline deterministic acceptance tests for evidence domain services."""

from __future__ import annotations

import base64
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.bibliography import normalize_doi, parse_bibliography
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.project_format import archive_project, restore_archive, verify_archive
from researchweave.evidence.storage import ProjectStore


def encoded(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def run(facade, operation, **arguments):
    result = facade.execute(operation, arguments, {})
    assert result["status"] == "ok", json.dumps(result)
    return result["data"]


def test_beginner_persistence_quotes_and_archive(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path / "workspace", allow_local_writes=True)
    project = run(facade, "project.create", title="مغز و حافظه", question="How is memory studied?",
                  design="exploratory")
    project_id = project["project_id"]
    sources = []
    for n in range(3):
        data = run(facade, "library.import", project_id=project_id,
                   title=f"Synthetic note {n}", media_type="text/plain",
                   data_base64=encoded(f"Synthetic observation {n}: no human participants."))
        sources.append(data["source_id"])
    text = run(facade, "library.source_text", project_id=project_id, source_id=sources[0])["text"]
    quote = "Synthetic observation"
    exact = run(facade, "evidence.anchor", project_id=project_id, source_id=sources[0],
                quote=quote, start=0, end=len(quote))
    assert exact["quote_verified"] is True
    false_quote = run(facade, "evidence.anchor", project_id=project_id, source_id=sources[0],
                      quote="invented", start=0, end=8)
    assert false_quote["quote_verified"] is False
    run(facade, "evidence.note", project_id=project_id, source_id=sources[0],
        title="Reading note", body="This is a human interpretation.")
    notebook = run(facade, "evidence.notebook_export", project_id=project_id)["text"]
    assert "Reading note" in notebook and sources[0] in notebook
    before = run(facade, "project.open", project_id=project_id)
    assert before["revision"] == 6
    assert run(facade, "project.integrity", project_id=project_id)["ok"]
    archive = run(facade, "project.archive", project_id=project_id, filename="notes.rwproj")
    assert archive["files"] == 4
    snapshot = tmp_path / "workspace" / "exports" / "notes.rwproj"
    assert verify_archive(snapshot)["project_revision"] == 6
    restored = restore_archive(snapshot, tmp_path / "restored")
    assert restored["revision"] == 6
    with ProjectStore(tmp_path / "restored") as store:
        assert store.info().title == "مغز و حافظه"
        assert store.audit()["ok"]
        assert len(store.conn.execute("SELECT * FROM sources").fetchall()) == 3
    assert text.startswith("Synthetic")


def test_invalid_archive_does_not_touch_destination(tmp_path: Path) -> None:
    malicious = tmp_path / "malicious.rwproj"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape.txt", "unsafe")
        archive.writestr("manifest.json", "{}")
    target = tmp_path / "output"
    with pytest.raises(EvidenceError):
        restore_archive(malicious, target)
    assert not target.exists()
    assert not (tmp_path / "escape.txt").exists()


def test_revision_denial_and_corruption(tmp_path: Path) -> None:
    store = ProjectStore.create(tmp_path / "db", "Title", "Research question", "exploratory")
    try:
        with pytest.raises(EvidenceError) as stale:
            store.mutate("test", {"x": 1}, lambda connection: None,
                         expected_revision=1)
        assert stale.value.code == "STALE_REVISION"
        assert store.info().revision == 0
        store.mutate("test", {"x": 1}, lambda connection: None,
                     expected_revision=0, request_id="request-one")
        with pytest.raises(EvidenceError) as duplicate:
            store.mutate("test", {"x": 1}, lambda connection: None,
                         expected_revision=1, request_id="request-one")
        assert duplicate.value.code == "CONFLICT"
        assert store.audit()["ok"]
        store.conn.execute("UPDATE events SET payload_hash='bad' WHERE sequence=1")
        assert not store.audit()["ok"]
    finally:
        store.close()


def test_bibliography_and_review_disagreement(tmp_path: Path) -> None:
    project_dir = tmp_path / "ws"
    facade = build_evidence_facade(project_dir, allow_local_writes=True)
    project_id = run(facade, "project.create", title="Review", question="What is the result?",
                     design="systematic_review")["project_id"]
    bib = "@article{k1, title={Test {Trial}}, author={Doe, Ada and Roe, Bea}, year={2024}, doi={invalid}}"
    references = run(facade, "library.bibliography_import", project_id=project_id,
                     format="bibtex", data_base64=encoded(bib))["references"]
    ref = references[0]
    assert ref["doi"] is None and "invalid" in ref["raw"]
    assert run(facade, "reference.validate", project_id=project_id,
               reference_id=ref["id"])["identity"] == "unknown"
    registration = run(facade, "review.register", project_id=project_id, review_id="review-1",
                       reference_id=ref["id"], study_id="study-1")
    record_id = registration["record_id"]
    run(facade, "review.screen", project_id=project_id, review_id="review-1",
        record_id=record_id, reviewer="r1", stage="title_abstract", decision="include")
    hidden = run(facade, "review.status", project_id=project_id, review_id="review-1",
                 record_id=record_id, stage="title_abstract")
    assert hidden["votes"] == [] and hidden["status"] == "pending_second_vote"
    run(facade, "review.screen", project_id=project_id, review_id="review-1",
        record_id=record_id, reviewer="r2", stage="title_abstract", decision="exclude",
        reason="Wrong population")
    conflict = run(facade, "review.status", project_id=project_id, review_id="review-1",
                   record_id=record_id, stage="title_abstract")
    assert conflict["status"] == "conflict"
    run(facade, "review.adjudicate", project_id=project_id, review_id="review-1",
        record_id=record_id, stage="title_abstract", decision="include",
        adjudicator="lead", reason="Protocol eligibility fulfilled")
    run(facade, "review.advance", project_id=project_id, review_id="review-1",
        record_id=record_id)
    prisma = run(facade, "review.prisma", project_id=project_id, review_id="review-1")
    assert prisma["records_identified"] == 1 and prisma["reports_sought"] == 1
    assert prisma["complete_prisma_2020"] is False
    assert run(facade, "project.integrity", project_id=project_id)["ok"]


def test_protocol_amendment_and_manuscript_check(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path / "ws", allow_local_writes=True)
    project = run(facade, "project.create", title="Paper", question="Why?", design="qualitative")
    project_id = project["project_id"]
    body = {"design": "qualitative", "objective": "Describe a synthetic phenomenon"}
    protocol = run(facade, "protocol.create", project_id=project_id,
                   title="Protocol", author="Researcher", body=body)
    run(facade, "protocol.amend", project_id=project_id,
        protocol_id=protocol["protocol_id"], author="Researcher",
        rationale="Changed after review", body={**body, "recruitment": "none"})
    history = run(facade, "protocol.history", project_id=project_id,
                  protocol_id=protocol["protocol_id"])["history"]
    assert [row["version"] for row in history] == [1, 2]
    assert history[0]["body"] == body
    assert history[1]["rationale"] == "Changed after review"
    references = run(facade, "library.bibliography_import", project_id=project_id,
        format="ris", data_base64=encoded("TY  - JOUR\nTI  - Synthetic source\nER  - \n"))["references"]
    run(facade, "writing.section_save", project_id=project_id, manuscript_id="paper-1",
        section="Introduction", body="Background [@study].",
        citations={"study": references[0]["id"]})
    report = run(facade, "writing.inspect", project_id=project_id, manuscript_id="paper-1")
    assert report["issues"][0]["code"] == "REFERENCE_IDENTITY_UNVERIFIED"
    markdown = run(facade, "writing.render", project_id=project_id,
                   manuscript_id="paper-1")["text"]
    assert "Synthetic source" in markdown and "unverified" in markdown


def test_denied_write_preview_and_malformed_bib(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path / "ws")
    denied = facade.execute("project.create",
                            {"title": "T", "question": "Q", "design": "exploratory"}, {})
    assert denied["error"]["code"] == "NEEDS_APPROVAL"
    preview = facade.preview("project.create",
                            {"title": "T", "question": "Q", "design": "exploratory"}, {})
    assert preview["status"] == "ok" and not (tmp_path / "ws").exists()
    with pytest.raises(EvidenceError):
        parse_bibliography(b"@article{k, title={unclosed}", "bibtex")
    assert normalize_doi("https://doi.org/10.1000/AbC") == "10.1000/abc"
