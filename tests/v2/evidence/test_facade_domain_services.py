from __future__ import annotations

import base64
from pathlib import Path

from researchweave.evidence import build_evidence_facade


def _execute(facade, operation: str, arguments: dict, revision: int | None = None):
    context = {} if revision is None else {"expected_revision": revision}
    result = facade.execute(operation, arguments, context)
    assert result["status"] == "ok", result
    return result["data"]


def test_facade_guided_project_question_and_protocol_roundtrip(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = _execute(
        facade,
        "project.wizard_create",
        {
            "title": "Mixed methods project",
            "question": "How do synthetic observations and interviews relate?",
            "design": "mixed_methods",
            "mode": "advanced",
            "privacy": "restricted",
            "stage": "protocol",
            "tags": ["Mixed Methods"],
            "advanced": {"registry_id": "user-supplied"},
        },
    )
    project_id = created["project_id"]
    assert (tmp_path / project_id).is_dir()
    assert created["privacy"] == "restricted"
    profile = _execute(facade, "project.profile", {"project_id": project_id})
    assert profile["mode"] == "advanced"
    assert profile["tags"] == ["mixed methods"]

    question = _execute(
        facade,
        "question.create",
        {
            "project_id": project_id,
            "question": "How is exposure associated with outcome in adults?",
            "framework": "PECO",
            "fields": {
                "population": "Adults",
                "exposure": "Synthetic exposure",
                "comparison": "Lower exposure",
                "outcome": "Synthetic outcome",
            },
            "author": "Researcher",
        },
    )
    history = _execute(
        facade,
        "question.history",
        {"project_id": project_id, "question_id": question["question_id"]},
    )
    assert history["history"][0]["hypotheses_generated"] == 0

    protocol = _execute(
        facade,
        "protocol.create",
        {
            "project_id": project_id,
            "title": "Protocol",
            "author": "Researcher",
            "body": {
                "design": "mixed",
                "objective": "Describe a synthetic mixed-methods workflow.",
            },
        },
    )
    _execute(
        facade,
        "protocol.amend",
        {
            "project_id": project_id,
            "protocol_id": protocol["protocol_id"],
            "author": "Researcher",
            "rationale": "Clarify analysis before use.",
            "body": {
                "design": "mixed",
                "objective": "Describe a synthetic mixed-methods workflow.",
                "analysis": "Triangulation",
            },
        },
    )
    diff = _execute(
        facade,
        "protocol.diff",
        {
            "project_id": project_id,
            "protocol_id": protocol["protocol_id"],
            "from_version": 1,
            "to_version": 2,
        },
    )
    assert diff["changed_fields"] == ["analysis"]
    exported = _execute(
        facade,
        "protocol.export",
        {"project_id": project_id, "protocol_id": protocol["protocol_id"]},
    )
    assert "### Version 2" in exported["text"]


def test_facade_study_forms_notes_and_synthesis_lifecycle(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    project = _execute(
        facade,
        "project.create",
        {
            "title": "Review",
            "question": "What does the synthetic evidence show?",
            "design": "systematic_review",
        },
    )
    project_id = project["project_id"]
    imported = _execute(
        facade,
        "library.bibliography_import",
        {
            "project_id": project_id,
            "format": "bibtex",
            "data_base64": base64.b64encode(
                b"@article{x,title={Synthetic report},author={Doe, Ada},year={2024}}"
            ).decode(),
        },
    )
    reference_id = imported["references"][0]["id"]
    record = _execute(
        facade,
        "review.register",
        {"project_id": project_id, "review_id": "review-1", "reference_id": reference_id},
    )
    study = _execute(
        facade,
        "review.study_create",
        {"project_id": project_id, "review_id": "review-1", "label": "Study A"},
    )
    _execute(
        facade,
        "review.study_attach",
        {
            "project_id": project_id,
            "study_id": study["study_id"],
            "record_id": record["record_id"],
            "relationship": "primary",
            "rationale": "Same user-reviewed study identity.",
        },
    )
    studies = _execute(
        facade, "review.studies", {"project_id": project_id, "review_id": "review-1"}
    )
    assert studies["studies"][0]["report_count"] == 1

    form = _execute(
        facade,
        "review.form_create",
        {
            "project_id": project_id,
            "name": "Outcome form",
            "fields": [
                {"name": "n", "datatype": "integer", "required": True, "minimum": 1},
                {"name": "effect", "datatype": "number", "unit": "points"},
            ],
            "author": "Reviewer",
        },
    )
    _execute(
        facade,
        "review.form_record",
        {
            "project_id": project_id,
            "form_id": form["form_id"],
            "record_id": record["record_id"],
            "values": {
                "n": {"value": 20, "missingness": "present"},
                "effect": {
                    "value": None,
                    "missingness": "not_reported",
                    "unit": "points",
                    "original_text": "",
                },
            },
            "reviewer": "Reviewer",
        },
    )
    values = _execute(
        facade,
        "review.form_values",
        {"project_id": project_id, "form_id": form["form_id"]},
    )
    assert values["values"][0]["values"]["effect"]["missingness"] == "not_reported"

    source = _execute(
        facade,
        "library.import",
        {
            "project_id": project_id,
            "title": "Source",
            "media_type": "text/plain",
            "data_base64": base64.b64encode(b"verified source text").decode(),
        },
    )
    note = _execute(
        facade,
        "evidence.note",
        {
            "project_id": project_id,
            "source_id": source["source_id"],
            "title": "Interpretation",
            "body": "Initial human interpretation.",
        },
    )
    _execute(
        facade,
        "evidence.note_revise",
        {
            "project_id": project_id,
            "note_id": note["note_id"],
            "title": "Interpretation",
            "body": "Revised human interpretation.",
            "actor": "Researcher",
            "rationale": "Clarify wording.",
        },
    )
    note_history = _execute(
        facade,
        "evidence.note_history",
        {"project_id": project_id, "note_id": note["note_id"]},
    )
    assert [item["revision"] for item in note_history["revisions"]] == [1, 2]

    gap = _execute(
        facade,
        "review.gap_add",
        {
            "project_id": project_id,
            "question": "What is missing?",
            "searches": [
                {"database": "Synthetic DB", "date": "2026-10-23", "strategy": "term"}
            ],
            "limitations": "Only a synthetic search was run.",
        },
    )
    _execute(
        facade,
        "review.gap_update",
        {
            "project_id": project_id,
            "gap_id": gap["id"],
            "status": "addressed",
            "priority": "high",
            "rationale": "A new synthetic report was added.",
            "actor": "Reviewer",
        },
    )
    gaps = _execute(facade, "review.gaps", {"project_id": project_id})
    assert gaps["records"][0]["status"] == "addressed"
    assert gaps["records"][0]["priority"] == "high"


def test_facade_writing_claim_and_portable_exports(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    project = _execute(
        facade,
        "project.create",
        {"title": "Writing", "question": "Question", "design": "observational"},
    )
    project_id = project["project_id"]
    source = _execute(
        facade,
        "library.import",
        {
            "project_id": project_id,
            "title": "Source",
            "media_type": "text/plain",
            "data_base64": base64.b64encode(b"The observed value increased.").decode(),
        },
    )
    anchor = _execute(
        facade,
        "evidence.anchor",
        {
            "project_id": project_id,
            "source_id": source["source_id"],
            "quote": "The observed value increased.",
            "start": 0,
            "end": 29,
        },
    )
    for section, body in {
        "Abstract": "The observed value increased.",
        "Methods": "Synthetic methods.",
        "Results": "Synthetic results.",
        "Discussion": "Synthetic discussion.",
    }.items():
        _execute(
            facade,
            "writing.section_save",
            {
                "project_id": project_id,
                "manuscript_id": "paper",
                "section": section,
                "body": body,
                "citations": {},
            },
        )
    claim = _execute(
        facade,
        "writing.claim_add",
        {
            "project_id": project_id,
            "manuscript_id": "paper",
            "section": "Abstract",
            "statement": "The observed value increased.",
            "statement_start": 0,
            "statement_end": 29,
            "actor": "Researcher",
            "rationale": "Exact source quotation supports this descriptive statement.",
            "anchor_id": anchor["anchor_id"],
        },
    )
    assert claim["classification"] == "evidence_backed"
    checked = _execute(
        facade, "writing.claim_check", {"project_id": project_id, "manuscript_id": "paper"}
    )
    assert checked["claims"][0]["status"] == "current"

    manuscript = _execute(
        facade,
        "writing.manuscript_export",
        {"project_id": project_id, "manuscript_id": "paper", "format": "markdown"},
    )
    assert base64.b64decode(manuscript["data_base64"]).startswith(b"# Manuscript paper")
    packet = _execute(
        facade,
        "writing.submission_export",
        {
            "project_id": project_id,
            "manuscript_id": "paper",
            "journal": "Synthetic Journal",
            "filename": "paper.rw-submission.zip",
            "allow_incomplete": True,
            "supplied_metadata": {"authors": ["Researcher"]},
        },
    )
    assert packet["submission_performed"] is False
    assert Path(packet["path"]).is_file()
