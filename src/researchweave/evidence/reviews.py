"""Audit-friendly review screening, adjudication and conservative PRISMA arithmetic."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .errors import EvidenceError, require
from .models import new_id, now_utc
from .storage import ProjectStore

STAGES = {"title_abstract", "full_text"}
DECISIONS = {"include", "exclude", "unsure"}


class ReviewService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def register(self, review_id: str, reference_id: str, study_id: str | None,
                 *, expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(review_id), "Review ID is required")
        require(bool(reference_id), "Reference ID is required")
        record_id = new_id()

        def insert(conn: Any) -> str:
            require(conn.execute("SELECT 1 FROM reference WHERE id=?", (reference_id,)).fetchone()
                    is not None, "Reference does not exist", "NOT_FOUND")
            try:
                conn.execute("INSERT INTO review_records(id,review_id,reference_id,study_id) "
                             "VALUES (?,?,?,?)", (record_id, review_id, reference_id, study_id))
            except Exception as exc:
                raise EvidenceError("CONFLICT", "This reference is already registered",
                                    "Use the existing review record.") from exc
            return record_id

        _, revision = self.store.mutate("review.register",
                                        {"review_id": review_id, "reference_id": reference_id},
                                        insert, expected_revision=expected_revision)
        return {"record_id": record_id, "review_id": review_id, "revision": revision}

    def vote(self, review_id: str, record_id: str, reviewer: str, stage: str,
             decision: str, reason: str = "", *,
             expected_revision: int | None = None) -> dict[str, Any]:
        require(stage in STAGES and decision in DECISIONS, "Invalid screening stage/decision")
        require(bool(reviewer.strip()) and len(reviewer) <= 255, "Invalid reviewer")
        require(decision != "exclude" or reason.strip(), "Exclusions require a reason")

        def insert(conn: Any) -> None:
            row = conn.execute("SELECT stage FROM review_records WHERE id=? AND review_id=?",
                               (record_id, review_id)).fetchone()
            require(row is not None, "Review record not found", "NOT_FOUND")
            require(row["stage"] == stage, "Vote does not match screening stage",
                    "CONFLICT")
            require(conn.execute("SELECT COUNT(*) FROM votes WHERE review_id=? "
                                 "AND record_id=? AND stage=?", (review_id, record_id, stage))
                    .fetchone()[0] < 2, "Screening round already has two reviewers", "CONFLICT")
            try:
                conn.execute("INSERT INTO votes VALUES (?,?,?,?,?,?,?)",
                             (review_id, record_id, reviewer, stage, decision, reason,
                              now_utc()))
            except Exception as exc:
                raise EvidenceError("CONFLICT", "Reviewer has already voted",
                                    "Use adjudication rather than overwriting a vote.") from exc

        _, revision = self.store.mutate("review.screen",
                                        {"review_id": review_id, "record_id": record_id,
                                         "reviewer": reviewer, "stage": stage,
                                         "decision": decision, "reason": reason},
                                        insert, expected_revision=expected_revision)
        return {"record_id": record_id, "revision": revision,
                "status": self.status(review_id, record_id, stage)["status"]}

    def status(self, review_id: str, record_id: str, stage: str,
               *, reveal_before_complete: bool = False) -> dict[str, Any]:
        require(stage in STAGES, "Invalid screening stage")
        rows = self.store.conn.execute(
            "SELECT reviewer,decision,reason FROM votes WHERE review_id=? AND record_id=? "
            "AND stage=? ORDER BY reviewer", (review_id, record_id, stage)).fetchall()
        adjudication = self.store.conn.execute(
            "SELECT decision,reason,adjudicator FROM adjudications WHERE review_id=? "
            "AND record_id=? AND stage=?", (review_id, record_id, stage)).fetchone()
        if len(rows) < 2:
            # Reviewer identity and choices are sealed until both vote.
            return {"status": "pending_second_vote" if rows else "unassessed",
                    "votes_recorded": len(rows), "votes": []}
        votes = [{"reviewer": row["reviewer"], "decision": row["decision"],
                  "reason": row["reason"]} for row in rows]
        if adjudication:
            return {"status": "adjudicated", "decision": adjudication["decision"],
                    "reason": adjudication["reason"], "votes": votes}
        if rows[0]["decision"] == rows[1]["decision"] and \
                rows[0]["decision"] in {"include", "exclude"}:
            return {"status": "agreed", "decision": rows[0]["decision"], "votes": votes}
        return {"status": "conflict", "votes": votes}

    def adjudicate(self, review_id: str, record_id: str, stage: str,
                   decision: str, adjudicator: str, reason: str, *,
                   expected_revision: int | None = None) -> dict[str, Any]:
        require(decision in {"include", "exclude"} and stage in STAGES,
                "Invalid adjudication stage/decision")
        require(bool(adjudicator.strip()) and bool(reason.strip()),
                "Adjudication requires identity and written rationale")
        require(self.status(review_id, record_id, stage)["status"] == "conflict",
                "Adjudication requires two conflicting reviewer votes", "CONFLICT")

        def insert(conn: Any) -> None:
            conn.execute("INSERT INTO adjudications VALUES (?,?,?,?,?,?,?)",
                         (review_id, record_id, stage, decision, reason, adjudicator, now_utc()))

        _, revision = self.store.mutate(
            "review.adjudicate", {"review_id": review_id, "record_id": record_id,
                                  "decision": decision, "adjudicator": adjudicator,
                                  "reason": reason}, insert, expected_revision=expected_revision)
        return {"record_id": record_id, "revision": revision, "decision": decision}

    def advance(self, review_id: str, record_id: str, *,
                expected_revision: int | None = None) -> dict[str, Any]:
        status = self.status(review_id, record_id, "title_abstract")
        require(status.get("decision") == "include", "Only included reports advance",
                "CONFLICT")

        def update(conn: Any) -> None:
            conn.execute("UPDATE review_records SET stage='full_text' "
                         "WHERE id=? AND review_id=? AND stage='title_abstract'",
                         (record_id, review_id))
            require(conn.execute("SELECT changes()").fetchone()[0] == 1,
                    "Report already advanced or not found", "CONFLICT")

        _, revision = self.store.mutate("review.advance",
                                        {"review_id": review_id, "record_id": record_id},
                                        update, expected_revision=expected_revision)
        return {"stage": "full_text", "revision": revision}

    def prisma(self, review_id: str) -> dict[str, Any]:
        """Stage counts from persistent votes; explicitly expose unresolved items.

        No assumption that unknown full-text retrieval equates to assessed eligibility.
        """
        records = self.store.conn.execute(
            "SELECT id,study_id,stage FROM review_records WHERE review_id=? ORDER BY id",
            (review_id,)).fetchall()
        identified = len(records)
        title_states: Counter[str] = Counter()
        full_states: Counter[str] = Counter()
        included_studies: set[str] = set()
        for record in records:
            title = self.status(review_id, record["id"], "title_abstract")
            title_states[title.get("decision", title["status"])] += 1
            if record["stage"] == "full_text":
                full = self.status(review_id, record["id"], "full_text")
                full_states[full.get("decision", full["status"])] += 1
                if full.get("decision") == "include":
                    included_studies.add(record["study_id"] or record["id"])
        screened = identified - title_states["unassessed"]
        excluded_title = title_states["exclude"]
        full_sought = sum(1 for row in records if row["stage"] == "full_text")
        included_reports = full_states["include"]
        excluded_full = full_states["exclude"]
        unresolved_title = identified - excluded_title - title_states["include"]
        unresolved_full = full_sought - excluded_full - included_reports
        return {"review_id": review_id, "records_identified": identified,
                "duplicates_removed": 0, "records_screened_started": screened,
                "records_excluded_title": excluded_title,
                "reports_sought": full_sought,
                "reports_assessed": included_reports + excluded_full,
                "reports_excluded_full_text": excluded_full,
                "reports_included": included_reports,
                "studies_included": len(included_studies),
                "unresolved_title": unresolved_title,
                "unresolved_full_text": unresolved_full,
                "missing_retrieval_status": full_sought,
                "complete_prisma_2020": False,
                "warning": "Source-level identification, dedup removals and retrieval status "
                           "are not yet collected: full PRISMA diagram unavailable."}
