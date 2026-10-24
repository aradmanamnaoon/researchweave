"""Audit-friendly review screening, adjudication and conservative PRISMA arithmetic."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .errors import EvidenceError, require
from .models import new_id, now_utc
from .storage import ProjectStore

STAGES = {"title_abstract", "full_text"}
DECISIONS = {"include", "exclude", "unsure"}


class ReviewService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def register(
        self,
        review_id: str,
        reference_id: str,
        study_id: str | None,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(review_id), "Review ID is required")
        require(bool(reference_id), "Reference ID is required")
        record_id = str(new_id())

        def insert(conn: Any) -> str:
            require(
                conn.execute("SELECT 1 FROM reference WHERE id=?", (reference_id,)).fetchone()
                is not None,
                "Reference does not exist",
                "NOT_FOUND",
            )
            try:
                conn.execute(
                    "INSERT INTO review_records(id,review_id,reference_id,study_id) "
                    "VALUES (?,?,?,?)",
                    (record_id, review_id, reference_id, study_id),
                )
            except Exception as exc:
                raise EvidenceError(
                    "CONFLICT",
                    "This reference is already registered",
                    "Use the existing review record.",
                ) from exc
            return record_id

        _, revision = self.store.mutate(
            "review.register",
            {"review_id": review_id, "reference_id": reference_id},
            insert,
            expected_revision=expected_revision,
        )
        return {"record_id": record_id, "review_id": review_id, "revision": revision}

    def begin_search(
        self,
        review_id: str,
        provider: str,
        query: str,
        expected_records: int,
        filters: Mapping[str, str] | None = None,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(
            bool(review_id.strip()) and bool(provider.strip()) and bool(query.strip()),
            "Search provenance fields are required",
        )
        require(0 <= expected_records <= 100_000, "Invalid source hit count")
        from .models import canonical_json

        run_id = new_id()
        encoded = canonical_json(dict(filters or {}))

        def insert(conn: Any) -> None:
            conn.execute(
                "INSERT INTO review_search_runs VALUES (?,?,?,?,?,?,?, ?,0)",
                (run_id, review_id, provider, query, encoded, now_utc(), None, expected_records),
            )

        _, revision = self.store.mutate(
            "review.search_begin",
            {"run_id": run_id, "provider": provider, "query": query, "expected": expected_records},
            insert,
            expected_revision=expected_revision,
        )
        return {"run_id": run_id, "revision": revision}

    def record_hit(
        self,
        run_id: str,
        reference_id: str,
        disposition: str,
        actor: str,
        rationale: str = "",
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(
            disposition in {"retained", "duplicate", "removed_automation", "removed_other"},
            "Invalid hit disposition",
        )
        require(bool(actor.strip()), "Actor is required")
        require(
            disposition == "retained" or bool(rationale.strip()),
            "Removed/duplicate records require a rationale",
        )
        hit_id = new_id()

        def insert(conn: Any) -> str | None:
            run = conn.execute(
                "SELECT review_id,expected_records,finalized FROM review_search_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            require(
                run is not None and not run["finalized"],
                "Search run missing or finalized",
                "CONFLICT",
            )
            require(
                conn.execute(
                    "SELECT COUNT(*) FROM review_search_hits WHERE run_id=?", (run_id,)
                ).fetchone()[0]
                < run["expected_records"],
                "Recorded hits exceed source count",
                "CONFLICT",
            )
            require(
                conn.execute("SELECT 1 FROM reference WHERE id=?", (reference_id,)).fetchone()
                is not None,
                "Reference not found",
                "NOT_FOUND",
            )
            row = conn.execute(
                "SELECT id FROM review_records WHERE review_id=? AND reference_id=?",
                (run["review_id"], reference_id),
            ).fetchone()
            record_id = row["id"] if row else None
            if disposition == "retained" and record_id is None:
                record_id = new_id()
                conn.execute(
                    "INSERT INTO review_records(id,review_id,reference_id) VALUES (?,?,?)",
                    (record_id, run["review_id"], reference_id),
                )
            conn.execute(
                "INSERT INTO review_search_hits VALUES (?,?,?,?,?,?,?,?)",
                (hit_id, run_id, reference_id, record_id, disposition, rationale, actor, now_utc()),
            )
            return record_id

        record_id, revision = self.store.mutate(
            "review.search_hit",
            {
                "run_id": run_id,
                "reference_id": reference_id,
                "disposition": disposition,
                "rationale": rationale,
            },
            insert,
            expected_revision=expected_revision,
        )
        return {"hit_id": hit_id, "record_id": record_id, "revision": revision}

    def finalize_search(
        self, run_id: str, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        def update(conn: Any) -> int:
            run = conn.execute(
                "SELECT expected_records,finalized FROM review_search_runs WHERE id=?", (run_id,)
            ).fetchone()
            require(run is not None and not run["finalized"], "Search run unavailable", "CONFLICT")
            count = conn.execute(
                "SELECT COUNT(*) FROM review_search_hits WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            require(count == run["expected_records"], "Search hit count not reconciled", "CONFLICT")
            conn.execute("UPDATE review_search_runs SET finalized=1 WHERE id=?", (run_id,))
            return int(count)

        count, revision = self.store.mutate(
            "review.search_finalize",
            {"run_id": run_id},
            update,
            expected_revision=expected_revision,
        )
        return {"run_id": run_id, "reconciled_records": count, "revision": revision}

    def retrieval(
        self,
        review_id: str,
        record_id: str,
        outcome: str,
        reason: str,
        actor: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(outcome in {"retrieved", "not_retrieved"}, "Invalid retrieval outcome")
        require(bool(reason.strip()) and bool(actor.strip()), "Retrieval requires reason and actor")
        require(
            self.status(review_id, record_id, "title_abstract").get("decision") == "include",
            "Only included reports may be sought",
            "CONFLICT",
        )

        def insert(conn: Any) -> None:
            require(
                conn.execute(
                    "SELECT 1 FROM review_records WHERE id=? AND review_id=?",
                    (record_id, review_id),
                ).fetchone()
                is not None,
                "Review report not found",
                "NOT_FOUND",
            )
            conn.execute(
                "INSERT INTO review_retrieval VALUES (?,?,?,?,?,?)",
                (record_id, review_id, outcome, reason, actor, now_utc()),
            )

        _, revision = self.store.mutate(
            "review.retrieval",
            {"record_id": record_id, "outcome": outcome, "reason": reason, "actor": actor},
            insert,
            expected_revision=expected_revision,
        )
        return {"record_id": record_id, "outcome": outcome, "revision": revision}

    def vote(
        self,
        review_id: str,
        record_id: str,
        reviewer: str,
        stage: str,
        decision: str,
        reason: str = "",
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(stage in STAGES and decision in DECISIONS, "Invalid screening stage/decision")
        require(bool(reviewer.strip()) and len(reviewer) <= 255, "Invalid reviewer")
        require(decision != "exclude" or bool(reason.strip()), "Exclusions require a reason")

        def insert(conn: Any) -> None:
            row = conn.execute(
                "SELECT stage FROM review_records WHERE id=? AND review_id=?",
                (record_id, review_id),
            ).fetchone()
            require(row is not None, "Review record not found", "NOT_FOUND")
            require(row["stage"] == stage, "Vote does not match screening stage", "CONFLICT")
            require(
                conn.execute(
                    "SELECT COUNT(*) FROM votes WHERE review_id=? AND record_id=? AND stage=?",
                    (review_id, record_id, stage),
                ).fetchone()[0]
                < 2,
                "Screening round already has two reviewers",
                "CONFLICT",
            )
            try:
                conn.execute(
                    "INSERT INTO votes VALUES (?,?,?,?,?,?,?)",
                    (review_id, record_id, reviewer, stage, decision, reason, now_utc()),
                )
            except Exception as exc:
                raise EvidenceError(
                    "CONFLICT",
                    "Reviewer has already voted",
                    "Use adjudication rather than overwriting a vote.",
                ) from exc

        _, revision = self.store.mutate(
            "review.screen",
            {
                "review_id": review_id,
                "record_id": record_id,
                "reviewer": reviewer,
                "stage": stage,
                "decision": decision,
                "reason": reason,
            },
            insert,
            expected_revision=expected_revision,
        )
        return {
            "record_id": record_id,
            "revision": revision,
            "status": self.status(review_id, record_id, stage)["status"],
        }

    def status(
        self, review_id: str, record_id: str, stage: str, *, reveal_before_complete: bool = False
    ) -> dict[str, Any]:
        require(stage in STAGES, "Invalid screening stage")
        rows = self.store.conn.execute(
            "SELECT reviewer,decision,reason FROM votes WHERE review_id=? AND record_id=? "
            "AND stage=? ORDER BY reviewer",
            (review_id, record_id, stage),
        ).fetchall()
        adjudication = self.store.conn.execute(
            "SELECT decision,reason,adjudicator FROM adjudications WHERE review_id=? "
            "AND record_id=? AND stage=?",
            (review_id, record_id, stage),
        ).fetchone()
        if len(rows) < 2:
            # Reviewer identity and choices are sealed until both vote.
            return {
                "status": "pending_second_vote" if rows else "unassessed",
                "votes_recorded": len(rows),
                "votes": [],
            }
        votes = [
            {"reviewer": row["reviewer"], "decision": row["decision"], "reason": row["reason"]}
            for row in rows
        ]
        if adjudication:
            return {
                "status": "adjudicated",
                "decision": adjudication["decision"],
                "reason": adjudication["reason"],
                "votes": votes,
            }
        if rows[0]["decision"] == rows[1]["decision"] and rows[0]["decision"] in {
            "include",
            "exclude",
        }:
            return {"status": "agreed", "decision": rows[0]["decision"], "votes": votes}
        return {"status": "conflict", "votes": votes}

    def adjudicate(
        self,
        review_id: str,
        record_id: str,
        stage: str,
        decision: str,
        adjudicator: str,
        reason: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(
            decision in {"include", "exclude"} and stage in STAGES,
            "Invalid adjudication stage/decision",
        )
        require(
            bool(adjudicator.strip()) and bool(reason.strip()),
            "Adjudication requires identity and written rationale",
        )
        require(
            self.status(review_id, record_id, stage)["status"] == "conflict",
            "Adjudication requires two conflicting reviewer votes",
            "CONFLICT",
        )

        def insert(conn: Any) -> None:
            conn.execute(
                "INSERT INTO adjudications VALUES (?,?,?,?,?,?,?)",
                (review_id, record_id, stage, decision, reason, adjudicator, now_utc()),
            )

        _, revision = self.store.mutate(
            "review.adjudicate",
            {
                "review_id": review_id,
                "record_id": record_id,
                "decision": decision,
                "adjudicator": adjudicator,
                "reason": reason,
            },
            insert,
            expected_revision=expected_revision,
        )
        return {"record_id": record_id, "revision": revision, "decision": decision}

    def reverse_adjudication(
        self,
        review_id: str,
        record_id: str,
        stage: str,
        actor: str,
        reason: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Undo an adjudication while preserving the original decision in audit history."""
        require(stage in STAGES, "Invalid adjudication stage")
        require(
            bool(actor.strip()) and bool(reason.strip()),
            "Reversal requires identity and written rationale",
        )

        def persist(conn: Any) -> dict[str, str]:
            row = conn.execute(
                "SELECT * FROM adjudications WHERE review_id=? AND record_id=? AND stage=?",
                (review_id, record_id, stage),
            ).fetchone()
            require(row is not None, "Adjudication not found", "NOT_FOUND")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS adjudication_reversals ("
                "id TEXT PRIMARY KEY,review_id TEXT NOT NULL,record_id TEXT NOT NULL,"
                "stage TEXT NOT NULL,decision TEXT NOT NULL,reason TEXT NOT NULL,"
                "adjudicator TEXT NOT NULL,adjudicated_at TEXT NOT NULL,"
                "reversed_by TEXT NOT NULL,reversal_reason TEXT NOT NULL,reversed_at TEXT NOT NULL)"
            )
            reversal_id = new_id()
            reversed_at = now_utc()
            conn.execute(
                "INSERT INTO adjudication_reversals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    reversal_id,
                    review_id,
                    record_id,
                    stage,
                    row["decision"],
                    row["reason"],
                    row["adjudicator"],
                    row["recorded_at"],
                    actor.strip(),
                    reason.strip(),
                    reversed_at,
                ),
            )
            conn.execute(
                "DELETE FROM adjudications WHERE review_id=? AND record_id=? AND stage=?",
                (review_id, record_id, stage),
            )
            return {
                "reversal_id": reversal_id,
                "previous_decision": str(row["decision"]),
                "reversed_at": reversed_at,
            }

        result, revision = self.store.mutate(
            "review.adjudication_reverse",
            {
                "review_id": review_id,
                "record_id": record_id,
                "stage": stage,
                "actor": actor.strip(),
                "reason": reason.strip(),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {**result, "record_id": record_id, "stage": stage, "revision": revision}

    def adjudication_history(self, review_id: str, record_id: str, stage: str) -> dict[str, Any]:
        require(stage in STAGES, "Invalid adjudication stage")
        current = self.store.conn.execute(
            "SELECT * FROM adjudications WHERE review_id=? AND record_id=? AND stage=?",
            (review_id, record_id, stage),
        ).fetchone()
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='adjudication_reversals'"
        ).fetchone()
        reversals = (
            [
                dict(row)
                for row in self.store.conn.execute(
                    "SELECT * FROM adjudication_reversals WHERE review_id=? AND record_id=? "
                    "AND stage=? ORDER BY reversed_at,id",
                    (review_id, record_id, stage),
                )
            ]
            if table is not None
            else []
        )
        return {
            "review_id": review_id,
            "record_id": record_id,
            "stage": stage,
            "current": dict(current) if current is not None else None,
            "reversals": reversals,
        }

    def advance(
        self, review_id: str, record_id: str, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        status = self.status(review_id, record_id, "title_abstract")
        require(status.get("decision") == "include", "Only included reports advance", "CONFLICT")
        retrieval = self.store.conn.execute(
            "SELECT outcome FROM review_retrieval WHERE record_id=? AND review_id=?",
            (record_id, review_id),
        ).fetchone()
        require(
            retrieval is not None and retrieval["outcome"] == "retrieved",
            "Full text must be retrieved before eligibility screening",
            "CONFLICT",
        )

        def update(conn: Any) -> None:
            conn.execute(
                "UPDATE review_records SET stage='full_text' "
                "WHERE id=? AND review_id=? AND stage='title_abstract'",
                (record_id, review_id),
            )
            require(
                conn.execute("SELECT changes()").fetchone()[0] == 1,
                "Report already advanced or not found",
                "CONFLICT",
            )

        _, revision = self.store.mutate(
            "review.advance",
            {"review_id": review_id, "record_id": record_id},
            update,
            expected_revision=expected_revision,
        )
        return {"stage": "full_text", "revision": revision}

    def prisma(self, review_id: str) -> dict[str, Any]:
        """Stage counts from persistent votes; explicitly expose unresolved items.

        No assumption that unknown full-text retrieval equates to assessed eligibility.
        """
        records = self.store.conn.execute(
            "SELECT id,study_id,stage FROM review_records WHERE review_id=? ORDER BY id",
            (review_id,),
        ).fetchall()
        search_runs = self.store.conn.execute(
            "SELECT id,expected_records,finalized FROM review_search_runs WHERE review_id=?",
            (review_id,),
        ).fetchall()
        source_hits = self.store.conn.execute(
            "SELECT h.disposition FROM review_search_hits h JOIN review_search_runs r "
            "ON r.id=h.run_id WHERE r.review_id=?",
            (review_id,),
        ).fetchall()
        source_count = sum(r["expected_records"] for r in search_runs)
        removals = Counter(h["disposition"] for h in source_hits)
        identified = source_count if search_runs else len(records)
        title_states: Counter[str] = Counter()
        full_states: Counter[str] = Counter()
        included_studies: set[str] = set()
        registry_table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_study_reports'"
        ).fetchone()
        registry_studies = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_studies'"
        ).fetchone()
        registry_map: dict[str, str] = {}
        registry_active = False
        if registry_table is not None and registry_studies is not None:
            registry_map = {
                str(row["record_id"]): str(row["study_id"])
                for row in self.store.conn.execute(
                    "SELECT rsr.record_id,rsr.study_id FROM review_study_reports rsr "
                    "JOIN review_studies rs ON rs.id=rsr.study_id WHERE rs.review_id=?",
                    (review_id,),
                )
            }
            registry_active = bool(
                self.store.conn.execute(
                    "SELECT 1 FROM review_studies WHERE review_id=? LIMIT 1", (review_id,)
                ).fetchone()
            )
        unresolved_study_identity = 0
        for record in records:
            title = self.status(review_id, record["id"], "title_abstract")
            title_states[title.get("decision", title["status"])] += 1
            if record["stage"] == "full_text":
                full = self.status(review_id, record["id"], "full_text")
                full_states[full.get("decision", full["status"])] += 1
                if full.get("decision") == "include":
                    if registry_active:
                        explicit_study = registry_map.get(str(record["id"]))
                        if explicit_study is None:
                            unresolved_study_identity += 1
                            included_studies.add(str(record["id"]))
                        else:
                            included_studies.add(explicit_study)
                    else:
                        included_studies.add(record["study_id"] or record["id"])
        screened = identified - title_states["unassessed"]
        excluded_title = title_states["exclude"]
        retrievals = self.store.conn.execute(
            "SELECT outcome FROM review_retrieval WHERE review_id=?", (review_id,)
        ).fetchall()
        retrieval_counts = Counter(r["outcome"] for r in retrievals)
        full_sought = (
            len(retrievals)
            if search_runs
            else sum(1 for row in records if row["stage"] == "full_text")
        )
        included_reports = full_states["include"]
        excluded_full = full_states["exclude"]
        unresolved_title = identified - excluded_title - title_states["include"]
        unresolved_full = full_sought - excluded_full - included_reports
        all_finalized = bool(search_runs) and all(r["finalized"] for r in search_runs)
        hit_counts_match = len(source_hits) == source_count
        screened_total = len(records)
        full_completed = (
            full_sought == retrieval_counts["retrieved"] + retrieval_counts["not_retrieved"]
            and retrieval_counts["retrieved"] == included_reports + excluded_full
        )
        title_completed = title_states["include"] + title_states["exclude"] == screened_total
        count_reconciled = identified == len(source_hits) and len(records) == identified - sum(
            removals[k] for k in ("duplicate", "removed_automation", "removed_other")
        )
        complete = (
            all_finalized
            and hit_counts_match
            and count_reconciled
            and title_completed
            and full_completed
            and full_sought == title_states["include"]
            and unresolved_study_identity == 0
        )
        return {
            "review_id": review_id,
            "records_identified": identified,
            "duplicates_removed": removals["duplicate"],
            "removed_automation": removals["removed_automation"],
            "removed_other": removals["removed_other"],
            "records_screened_started": screened,
            "records_excluded_title": excluded_title,
            "reports_sought": full_sought,
            "reports_not_retrieved": retrieval_counts["not_retrieved"],
            "reports_assessed": included_reports + excluded_full,
            "reports_excluded_full_text": excluded_full,
            "reports_included": included_reports,
            "studies_included": len(included_studies),
            "study_registry_used": registry_active,
            "unresolved_study_identity": unresolved_study_identity,
            "unresolved_title": unresolved_title,
            "unresolved_full_text": unresolved_full,
            "missing_retrieval_status": (
                max(0, title_states["include"] - full_sought) if search_runs else full_sought
            ),
            "complete_prisma_2020": complete,
            "warning": (
                ""
                if complete
                else "PRISMA identification, screening, retrieval "
                "or assessment counts remain unreconciled."
            ),
            "source_search_runs": len(search_runs),
        }
