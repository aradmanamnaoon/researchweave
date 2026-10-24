"""Five independent, offline, persisted ResearchWeave research acceptance journeys.

Each trace records executed public commands and real, checked persistent outcomes;
unstable UUIDs are intentionally kept out of normalized trace snapshots.
"""

from __future__ import annotations

import base64
import json
import shutil
import sqlite3
from pathlib import Path

from researchweave.evidence import build_evidence_facade


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class Journey:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.facade = build_evidence_facade(workspace, allow_local_writes=True)
        self.trace: list[dict[str, object]] = []

    def call(self, operation: str, **arguments: object) -> dict:
        result = self.facade.execute(operation, arguments, {})
        self.trace.append({"operation": operation, "status": result["status"]})
        assert result["status"] == "ok", json.dumps(result, ensure_ascii=False)
        return dict(result["data"])

    def denied(self, operation: str, code: str, **arguments: object) -> None:
        result = self.facade.execute(operation, arguments, {})
        assert result["status"] == "failed" and result["error"]["code"] == code
        self.trace.append({"operation": operation, "status": "failed", "code": code})

    def emit(self, name: str, directory: Path) -> None:
        directory.mkdir(exist_ok=True)
        (directory / f"{name}.json").write_text(
            json.dumps(
                {"journey": name, "steps": self.trace, "verified": True},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def test_journey_1_beginner_literature_brief(tmp_path: Path) -> None:
    j = Journey(tmp_path / "ws")
    project_id = j.call(
        "project.create", title="Beginner", question="What is memory?", design="exploratory"
    )["project_id"]
    guidance = j.call(
        "question.feedback",
        question="How do observations change?",
        framework="PICO",
        fields={"population": "Synthetic observations"},
    )
    assert guidance
    ids = []
    for index in range(3):
        source = j.call(
            "library.import",
            project_id=project_id,
            title=f"Source {index}",
            media_type="text/plain",
            data_base64=b64(f"Research observation {index} is a synthetic fixture."),
        )
        ids.append(source["source_id"])
    bibliography = j.call(
        "library.bibliography_import",
        project_id=project_id,
        format="bibtex",
        data_base64=b64(
            "@article{a,title={Synthetic Study},author={Doe, Ada},"
            "year={2025},doi={10.1000/synthetic}}"
        ),
    )
    reference_id = bibliography["references"][0]["id"]
    doi_result = j.call("reference.validate", project_id=project_id, reference_id=reference_id)
    assert doi_result["syntax"] == "valid" and doi_result["identity"] == "unknown"
    verified = j.call(
        "evidence.anchor",
        project_id=project_id,
        source_id=ids[0],
        quote="Research observation",
        start=0,
        end=20,
    )
    assert verified["quote_verified"]
    j.call(
        "evidence.note",
        project_id=project_id,
        source_id=ids[0],
        title="Reading note",
        body="Human-authored interpretation from source.",
    )
    notebook = j.call("evidence.notebook_export", project_id=project_id)
    assert ids[0] in notebook["text"] and "Reading note" in notebook["text"]
    reopened = build_evidence_facade(j.workspace)
    assert reopened.execute("project.integrity", {"project_id": project_id}, {})["data"]["ok"]
    assert reopened.execute("project.open", {"project_id": project_id}, {})["data"]["revision"] == 6
    j.trace.append({"operation": "project.reopen", "status": "ok"})
    j.emit("01_beginner_brief", tmp_path / "traces")


def test_journey_2_review_disagreement_and_reconciliation(tmp_path: Path) -> None:
    j = Journey(tmp_path / "ws")
    pid = j.call(
        "project.create", title="Review", question="Does a method work?", design="systematic_review"
    )["project_id"]
    refs = j.call(
        "library.bibliography_import",
        project_id=pid,
        format="ris",
        data_base64=b64(
            "TY  - JOUR\nTI  - Trial Alpha\nER  - \nTY  - JOUR\nTI  - Trial Beta\nER  - \n"
        ),
    )["references"]
    run_id = j.call(
        "review.search_begin",
        project_id=pid,
        review_id="r",
        provider="synthetic",
        query="method AND outcome",
        expected_records=2,
    )["run_id"]
    register = j.call(
        "review.register",
        project_id=pid,
        review_id="r",
        reference_id=refs[0]["id"],
        study_id="study-alpha",
    )
    rid = register["record_id"]
    j.call(
        "review.search_hit",
        project_id=pid,
        run_id=run_id,
        reference_id=refs[0]["id"],
        disposition="retained",
        actor="reviewer",
    )
    j.call(
        "review.search_hit",
        project_id=pid,
        run_id=run_id,
        reference_id=refs[1]["id"],
        disposition="duplicate",
        actor="reviewer",
        rationale="Confirmed duplicate during source screening",
    )
    j.call("review.search_finalize", project_id=pid, run_id=run_id)
    j.call(
        "review.screen",
        project_id=pid,
        review_id="r",
        record_id=rid,
        reviewer="reviewer-a",
        stage="title_abstract",
        decision="include",
    )
    blinded = j.call(
        "review.status", project_id=pid, review_id="r", record_id=rid, stage="title_abstract"
    )
    assert blinded["status"] == "pending_second_vote" and blinded["votes"] == []
    j.call(
        "review.screen",
        project_id=pid,
        review_id="r",
        record_id=rid,
        reviewer="reviewer-b",
        stage="title_abstract",
        decision="exclude",
        reason="Wrong outcome",
    )
    assert (
        j.call(
            "review.status", project_id=pid, review_id="r", record_id=rid, stage="title_abstract"
        )["status"]
        == "conflict"
    )
    j.call(
        "review.adjudicate",
        project_id=pid,
        review_id="r",
        record_id=rid,
        stage="title_abstract",
        decision="include",
        adjudicator="third-reviewer",
        reason="Original protocol includes this outcome",
    )
    j.call(
        "review.retrieval",
        project_id=pid,
        review_id="r",
        record_id=rid,
        outcome="retrieved",
        reason="Saved local text",
        actor="third-reviewer",
    )
    j.call("review.advance", project_id=pid, review_id="r", record_id=rid)
    report = j.call("review.prisma", project_id=pid, review_id="r")
    assert report["records_identified"] == 2 and report["duplicates_removed"] == 1
    csv = j.call("review.prisma_export", project_id=pid, review_id="r", format="csv")
    assert "records_identified,2" in csv["text"]
    bibliography = j.call("library.references", project_id=pid)
    assert len(bibliography["records"]) == 2
    assert build_evidence_facade(j.workspace).execute("project.integrity", {"project_id": pid}, {})[
        "data"
    ]["ok"]
    j.emit("02_review_disagreement", tmp_path / "traces")


def test_journey_3_citation_failure_preserves_raw_record(tmp_path: Path) -> None:
    j = Journey(tmp_path / "ws")
    pid = j.call(
        "project.create", title="Citation", question="Can it be identified?", design="exploratory"
    )["project_id"]
    raw = "@article{unknown,title={Unconfirmed Discovery},doi={10.},author={Anonymous}}"
    result = j.call(
        "library.bibliography_import", project_id=pid, format="bibtex", data_base64=b64(raw)
    )
    ref = result["references"][0]
    identity = j.call("reference.validate", project_id=pid, reference_id=ref["id"])
    assert identity["identity"] == "unknown" and identity["verified"] is False
    assert "10." in ref["raw"]
    j.denied(
        "library.bibliography_import",
        "INVALID_INPUT",
        project_id=pid,
        format="bibtex",
        data_base64=b64("@article{broken,title={unclosed}"),
    )
    assert (
        build_evidence_facade(j.workspace).execute("project.open", {"project_id": pid}, {})["data"][
            "revision"
        ]
        == 1
    )
    with sqlite3.connect(j.workspace / pid / "data" / "project.sqlite") as conn:
        assert conn.execute("SELECT raw FROM reference").fetchone()[0] == raw
    j.trace.append({"operation": "reference.raw_preservation", "status": "ok"})
    j.emit("03_citation_integrity_failure", tmp_path / "traces")


def test_journey_4_native_backup_survives_and_rejects_corruption(tmp_path: Path) -> None:
    j = Journey(tmp_path / "ws")
    pid = j.call(
        "project.create", title="Backup", question="Do files survive?", design="exploratory"
    )["project_id"]
    imported = j.call(
        "library.import",
        project_id=pid,
        title="Source",
        media_type="text/plain",
        data_base64=b64("Synthetic backup data."),
    )
    j.call("project.archive", project_id=pid, filename="backup.rwproj")
    archive = j.workspace / "exports" / "backup.rwproj"
    before = j.call("project.archive_verify", filename="backup.rwproj")
    destination = tmp_path / "elsewhere"
    (destination / "exports").mkdir(parents=True)
    shutil.copyfile(archive, destination / "exports" / "backup.rwproj")
    second = Journey(destination)
    restored = second.call("project.restore", filename="backup.rwproj")
    assert restored["project_id"] == pid
    assert second.call("project.integrity", project_id=pid)["ok"]
    assert second.call("project.open", project_id=pid)["revision"] == 1
    assert (
        second.call("library.source_text", project_id=pid, source_id=imported["source_id"])["text"]
        == "Synthetic backup data."
    )
    assert before["manifest_sha256"] == restored["manifest_sha256"]
    second.denied("project.restore", "CONFLICT", filename="backup.rwproj")
    j.trace += second.trace
    j.emit("04_backup_survival", tmp_path / "traces")


def test_journey_5_migration_loss_preview_undo_and_reopen(tmp_path: Path) -> None:
    j = Journey(tmp_path / "ws")
    pid = j.call(
        "project.create", title="Migration", question="What is lost?", design="qualitative"
    )["project_id"]
    files = [
        {
            "filename": "Notion.md",
            "data_base64": b64(
                "---\ntitle: Research note\nsource: external\n---\n"
                "A note with [[unsupported-link]]."
            ),
        },
        {"filename": "فارسی.md", "data_base64": b64("# Synthetic Persian note\nمتن")},
    ]
    preview = j.call("migration.markdown_preview", files=files)
    assert preview["mapped"] == 2 and preview["writes"] == 0
    assert preview["records"][0]["warnings"]
    assert j.call("project.open", project_id=pid)["revision"] == 0
    imported = j.call("migration.markdown_import", project_id=pid, files=files)
    assert imported["receipt"]["mapped"] == 2
    first = imported["source_ids"][0]
    assert (
        "source: external" in j.call("library.source_text", project_id=pid, source_id=first)["text"]
    )
    assert (
        j.call("migration.markdown_undo", project_id=pid, batch_id=imported["batch_id"])[
            "soft_deleted"
        ]
        == 2
    )
    j.denied("migration.markdown_undo", "NOT_FOUND", project_id=pid, batch_id=imported["batch_id"])
    assert build_evidence_facade(j.workspace).execute("project.integrity", {"project_id": pid}, {})[
        "data"
    ]["ok"]
    with sqlite3.connect(j.workspace / pid / "data" / "project.sqlite") as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources WHERE deleted=0").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 2
    j.emit("05_migration_loss_audit", tmp_path / "traces")
