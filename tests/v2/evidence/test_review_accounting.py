"""Reconciled source identification, retrieval and multiple reports per study."""

from __future__ import annotations

import base64
import sqlite3
from pathlib import Path

import pytest

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.storage import SCHEMA_SQL, ProjectStore


def call(facade, operation: str, **args):
    result = facade.execute(operation, args, {})
    assert result["status"] == "ok", result
    return result["data"]


def test_search_retrieval_prisma_reopen(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path / "ws", allow_local_writes=True)
    project = call(facade, "project.create", title="Review",
                   question="Do synthetic studies agree?", design="systematic_review")
    project_id = project["project_id"]
    entries = "".join(f"TY  - JOUR\nTI  - Synthetic report {i}\nER  - \n"
                      for i in range(4))
    refs = call(facade, "library.bibliography_import", project_id=project_id,
                format="ris", data_base64=base64.b64encode(entries.encode()).decode())
    ids = [r["id"] for r in refs["references"]]
    run_id = call(facade, "review.search_begin", project_id=project_id,
                  review_id="r", provider="mock-database", query="cognitive outcomes",
                  expected_records=4)["run_id"]
    for i, reference_id in enumerate(ids):
        hit = call(facade, "review.search_hit", project_id=project_id,
                   run_id=run_id, reference_id=reference_id,
                   disposition="duplicate" if i == 3 else "retained", actor="reviewer",
                   rationale="Duplicate export" if i == 3 else "")
        if i != 3:
            record_id = hit["record_id"]
            for reviewer in ("a", "b"):
                call(facade, "review.screen", project_id=project_id, review_id="r",
                     record_id=record_id, reviewer=reviewer, stage="title_abstract",
                     decision="include")
            call(facade, "review.retrieval", project_id=project_id, review_id="r",
                 record_id=record_id, outcome="not_retrieved" if i == 2 else "retrieved",
                 reason="Unavailable" if i == 2 else "Open text", actor="reviewer")
            if i != 2:
                call(facade, "review.advance", project_id=project_id,
                     review_id="r", record_id=record_id)
                for reviewer in ("a", "b"):
                    call(facade, "review.screen", project_id=project_id, review_id="r",
                         record_id=record_id, reviewer=reviewer, stage="full_text",
                         decision="include")
    call(facade, "review.search_finalize", project_id=project_id, run_id=run_id)
    with ProjectStore(tmp_path / "ws" / project_id) as store:
        report = store.conn.execute("SELECT * FROM review_search_runs").fetchone()
        assert report["original_query"] == "cognitive outcomes"
        assert store.audit()["ok"]
    result = call(facade, "review.prisma", project_id=project_id, review_id="r")
    assert result["records_identified"] == 4
    assert result["duplicates_removed"] == 1
    assert result["reports_sought"] == 3
    assert result["reports_not_retrieved"] == 1
    assert result["reports_included"] == 2
    assert result["complete_prisma_2020"] is True


def test_unfinalized_search_does_not_claim_prisma_completion(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path / "ws", allow_local_writes=True)
    project_id = call(facade, "project.create", title="Review", question="Audit?",
                      design="systematic_review")["project_id"]
    run_id = call(facade, "review.search_begin", project_id=project_id,
                  review_id="r", provider="test", query="subject", expected_records=2)["run_id"]
    refused = facade.execute("review.search_finalize",
                             {"project_id": project_id, "run_id": run_id}, {})
    assert refused["error"]["code"] == "CONFLICT"
    assert call(facade, "review.prisma", project_id=project_id,
                review_id="r")["complete_prisma_2020"] is False


def test_explicit_v1_migration_preserves_data_and_backup(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    (root / "data").mkdir(parents=True)
    (root / "objects").mkdir()
    db = root / "data" / "project.sqlite"
    with sqlite3.connect(db) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute("PRAGMA user_version=1")
        connection.execute("INSERT INTO migrations VALUES (1,'synthetic')")
        connection.execute("INSERT INTO project VALUES "
                           "('legacy','Original','Original question','exploratory',"
                           "'en','private',0,'synthetic')")
    with pytest.raises(EvidenceError) as incompatible:
        ProjectStore(root)
    assert incompatible.value.code == "SCHEMA_MISMATCH"
    receipt = ProjectStore.migrate_v1(root)
    assert receipt["from_version"] == 1 and receipt["to_version"] == 2
    assert Path(str(receipt["backup"])).is_file()
    with sqlite3.connect(str(receipt["backup"])) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
    with ProjectStore(root) as reopened:
        assert reopened.info().title == "Original"
        assert reopened.conn.execute("SELECT COUNT(*) FROM review_search_runs").fetchone()[0] == 0
        assert reopened.audit()["ok"]
    with pytest.raises(EvidenceError) as duplicate:
        ProjectStore.migrate_v1(root)
    assert duplicate.value.code == "SCHEMA_MISMATCH"
