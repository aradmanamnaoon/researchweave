"""Public-domain workflow tests for newly connected services."""

import base64
import sqlite3

from researchweave.evidence import build_evidence_facade


def _call(facade, name, **arguments):
    result = facade.execute(name, arguments, {})
    assert result["status"] == "ok", result
    return result["data"]


def test_facade_docx_pages_and_verified_reopen(tmp_path):
    from tests.v2.evidence.test_fulltext import docx

    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    project_id = _call(
        facade,
        "project.create",
        title="Documents",
        question="How to preserve exact spans?",
        design="exploratory",
    )["project_id"]
    source = _call(
        facade,
        "library.import",
        project_id=project_id,
        title="Unicode document",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data_base64=base64.b64encode(docx()).decode(),
    )
    reopened = build_evidence_facade(tmp_path)
    pages = _call(
        reopened, "library.source_pages", project_id=project_id, source_id=source["source_id"]
    )
    assert pages["available"]
    assert [page["text"] for page in pages["pages"]] == ["Evidence", "متن"]
    assert pages["pages"][0]["section_kind"] == "Heading1"
    assert pages["pages"][0]["heading"] == "Evidence"
    assert (
        _call(
            reopened, "library.source_text", project_id=project_id, source_id=source["source_id"]
        )["text"]
        == "Evidence\n\nمتن"
    )
    with sqlite3.connect(tmp_path / project_id / "data" / "project.sqlite") as conn:
        conn.execute("UPDATE fulltext_pages SET text='tampered'")
    failed = reopened.execute(
        "library.source_pages", {"project_id": project_id, "source_id": source["source_id"]}, {}
    )
    assert failed["error"]["code"] == "INTEGRITY_FAILURE"


def test_facade_gap_and_read_only_query(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    project_id = _call(
        facade,
        "project.create",
        title="Gap study",
        question="Where is evidence missing?",
        design="systematic_review",
    )["project_id"]
    db_path = tmp_path / project_id / "data" / "project.sqlite"
    read_only = build_evidence_facade(tmp_path)
    before = db_path.read_bytes()
    assert _call(read_only, "review.gaps", project_id=project_id)["records"] == []
    assert before == db_path.read_bytes()
    saved = _call(
        facade,
        "review.gap_add",
        project_id=project_id,
        question="No evidence for subgroup?",
        limitations="One database only",
        searches=[
            {"database": "Synthetic", "date": "2026-10-23", "strategy": "subgroup AND question"}
        ],
    )
    assert saved["status"] == "open"
    assert _call(read_only, "review.gaps", project_id=project_id)["records"][0]["id"] == saved["id"]
    bad = read_only.execute(
        "review.gap_add",
        {"project_id": project_id, "question": "q", "searches": [], "limitations": "unknown"},
        {},
    )
    assert bad["error"]["code"] == "NEEDS_APPROVAL"
