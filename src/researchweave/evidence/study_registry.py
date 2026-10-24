"""Stable review-study identities that can own several imported reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, new_id, now_utc
from .storage import ProjectStore


class StudyRegistryService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _tables(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS review_studies ("
            "id TEXT PRIMARY KEY, review_id TEXT NOT NULL, label TEXT NOT NULL, "
            "metadata_json TEXT NOT NULL, created_at TEXT NOT NULL, "
            "UNIQUE(review_id,label))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS review_study_reports ("
            "study_id TEXT NOT NULL REFERENCES review_studies(id), "
            "record_id TEXT NOT NULL REFERENCES review_records(id), "
            "relationship TEXT NOT NULL CHECK(relationship IN "
            "('primary','secondary','protocol','correction','other')), "
            "rationale TEXT NOT NULL, linked_at TEXT NOT NULL, "
            "PRIMARY KEY(study_id,record_id), UNIQUE(record_id))"
        )

    def create(
        self,
        review_id: str,
        label: str,
        metadata: Mapping[str, Any] | None = None,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(review_id.strip()) and len(review_id) <= 255, "Review ID is required")
        require(bool(label.strip()) and len(label) <= 500, "Study label is required")
        metadata_dict = dict(metadata or {})
        require(len(metadata_dict) <= 100, "Study metadata has too many fields", "RESOURCE_LIMIT")
        study_id = new_id()

        def persist(conn: Any) -> None:
            self._tables(conn)
            try:
                conn.execute(
                    "INSERT INTO review_studies VALUES (?,?,?,?,?)",
                    (
                        study_id,
                        review_id.strip(),
                        label.strip(),
                        canonical_json(metadata_dict),
                        now_utc(),
                    ),
                )
            except Exception as exc:
                raise EvidenceError(
                    "CONFLICT",
                    "Study label already exists in this review",
                    "Use the existing study identity or choose a distinct label.",
                ) from exc

        _, revision = self.store.mutate(
            "review.study_create",
            {"study_id": study_id, "review_id": review_id, "label": label.strip()},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "study_id": study_id,
            "review_id": review_id,
            "label": label.strip(),
            "project_revision": revision,
        }

    def attach_report(
        self,
        study_id: str,
        record_id: str,
        relationship: str,
        rationale: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(
            relationship in {"primary", "secondary", "protocol", "correction", "other"},
            "Unknown study-report relationship",
        )
        require(
            bool(rationale.strip()) and len(rationale) <= 5000,
            "Study/report linkage rationale is required",
        )

        def persist(conn: Any) -> str:
            self._tables(conn)
            study = conn.execute("SELECT * FROM review_studies WHERE id=?", (study_id,)).fetchone()
            require(study is not None, "Review study not found", "NOT_FOUND")
            record = conn.execute(
                "SELECT * FROM review_records WHERE id=?", (record_id,)
            ).fetchone()
            require(record is not None, "Review record not found", "NOT_FOUND")
            require(
                record["review_id"] == study["review_id"],
                "Study and report belong to different reviews",
                "CONFLICT",
            )
            existing = conn.execute(
                "SELECT study_id FROM review_study_reports WHERE record_id=?",
                (record_id,),
            ).fetchone()
            require(existing is None, "Report is already assigned to a study", "CONFLICT")
            conn.execute(
                "INSERT INTO review_study_reports VALUES (?,?,?,?,?)",
                (
                    study_id,
                    record_id,
                    relationship,
                    rationale.strip(),
                    now_utc(),
                ),
            )
            return str(study["review_id"])

        review_id, revision = self.store.mutate(
            "review.study_attach_report",
            {
                "study_id": study_id,
                "record_id": record_id,
                "relationship": relationship,
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "study_id": study_id,
            "record_id": record_id,
            "review_id": review_id,
            "relationship": relationship,
            "project_revision": revision,
        }

    def detach_report(
        self,
        study_id: str,
        record_id: str,
        rationale: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(
            bool(rationale.strip()) and len(rationale) <= 5000, "Detachment rationale is required"
        )

        def persist(conn: Any) -> None:
            require(
                conn.execute(
                    "SELECT 1 FROM review_study_reports WHERE study_id=? AND record_id=?",
                    (study_id, record_id),
                ).fetchone()
                is not None,
                "Study/report linkage not found",
                "NOT_FOUND",
            )
            conn.execute(
                "DELETE FROM review_study_reports WHERE study_id=? AND record_id=?",
                (study_id, record_id),
            )

        _, revision = self.store.mutate(
            "review.study_detach_report",
            {
                "study_id": study_id,
                "record_id": record_id,
                "rationale": rationale.strip(),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "study_id": study_id,
            "record_id": record_id,
            "detached": True,
            "project_revision": revision,
        }

    def studies(self, review_id: str) -> list[dict[str, Any]]:
        exists = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_studies'"
        ).fetchone()
        if exists is None:
            return []
        output = []
        for study in self.store.conn.execute(
            "SELECT * FROM review_studies WHERE review_id=? ORDER BY created_at,id",
            (review_id,),
        ):
            reports = [
                {
                    **dict(row),
                    "reference_id": reference["reference_id"],
                }
                for row in self.store.conn.execute(
                    "SELECT * FROM review_study_reports WHERE study_id=? "
                    "ORDER BY linked_at,record_id",
                    (study["id"],),
                )
                for reference in [
                    self.store.conn.execute(
                        "SELECT reference_id FROM review_records WHERE id=?",
                        (row["record_id"],),
                    ).fetchone()
                ]
            ]
            output.append(
                {
                    "study_id": study["id"],
                    "review_id": study["review_id"],
                    "label": study["label"],
                    "metadata": json.loads(study["metadata_json"]),
                    "created_at": study["created_at"],
                    "reports": reports,
                    "report_count": len(reports),
                }
            )
        return output

    def reconcile_unassigned(self, review_id: str) -> dict[str, Any]:
        """Report imported review records lacking an explicit study assignment."""
        assigned = set()
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_study_reports'"
        ).fetchone()
        if table is not None:
            assigned = {
                str(row["record_id"])
                for row in self.store.conn.execute(
                    "SELECT rsr.record_id FROM review_study_reports rsr "
                    "JOIN review_records rr ON rr.id=rsr.record_id "
                    "WHERE rr.review_id=?",
                    (review_id,),
                )
            }
        records = [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT id,reference_id,study_id FROM review_records WHERE review_id=? ORDER BY id",
                (review_id,),
            )
        ]
        unassigned = [row for row in records if str(row["id"]) not in assigned]
        return {
            "review_id": review_id,
            "records": len(records),
            "assigned": len(records) - len(unassigned),
            "unassigned": unassigned,
            "study_identity_inferred": False,
        }
