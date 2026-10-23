"""Persisted structured research questions without generated hypotheses."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import EvidenceError, require
from .models import canonical_json, new_id, now_utc, sha256
from .protocols import ALLOWED_FRAMEWORKS, question_feedback
from .storage import ProjectStore


class ResearchQuestionService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _table(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS research_questions ("
            "id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), "
            "question TEXT NOT NULL, framework TEXT NOT NULL, fields_json TEXT NOT NULL, "
            "rationale TEXT NOT NULL, author TEXT NOT NULL, recorded_at TEXT NOT NULL, "
            "content_sha256 TEXT NOT NULL, PRIMARY KEY(id,version))"
        )

    def create(
        self,
        question: str,
        framework: str,
        fields: Mapping[str, str],
        author: str,
        *,
        rationale: str = "Initial structured question",
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(framework in ALLOWED_FRAMEWORKS, "Unknown research question framework")
        require(bool(author.strip()) and len(author) <= 255, "Question author is required")
        require(
            bool(rationale.strip()) and len(rationale) <= 5000,
            "Question rationale is required",
        )
        feedback = question_feedback(question, framework, fields)
        require(
            feedback["ready_to_record"],
            "Structured research question is incomplete",
            "INVALID_INPUT",
        )
        normalized_fields = {str(key): str(value).strip() for key, value in fields.items()}
        document = {
            "question": question.strip(),
            "framework": framework,
            "fields": normalized_fields,
            "rationale": rationale.strip(),
            "author": author.strip(),
        }
        digest = sha256(canonical_json(document).encode())
        question_id = new_id()

        def persist(conn: Any) -> None:
            self._table(conn)
            conn.execute(
                "INSERT INTO research_questions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    question_id,
                    1,
                    document["question"],
                    framework,
                    canonical_json(normalized_fields),
                    document["rationale"],
                    document["author"],
                    now_utc(),
                    digest,
                ),
            )

        _, revision = self.store.mutate(
            "question.create",
            {
                "question_id": question_id,
                "version": 1,
                "framework": framework,
                "content_sha256": digest,
                "hypotheses_generated": 0,
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "question_id": question_id,
            "version": 1,
            "framework": framework,
            "content_sha256": digest,
            "hypotheses_generated": 0,
            "project_revision": revision,
        }

    def amend(
        self,
        question_id: str,
        question: str,
        framework: str,
        fields: Mapping[str, str],
        author: str,
        rationale: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(author.strip()) and len(author) <= 255, "Question author is required")
        require(bool(rationale.strip()) and len(rationale) <= 5000,
                "Question amendment rationale is required")
        feedback = question_feedback(question, framework, fields)
        require(feedback["ready_to_record"], "Structured research question is incomplete")
        prior = self.latest(question_id)
        normalized_fields = {str(key): str(value).strip() for key, value in fields.items()}
        version = int(prior["version"]) + 1
        document = {
            "question": question.strip(),
            "framework": framework,
            "fields": normalized_fields,
            "rationale": rationale.strip(),
            "author": author.strip(),
        }
        digest = sha256(canonical_json(document).encode())
        require(
            digest != prior["content_sha256"],
            "Question amendment does not change content",
            "CONFLICT",
        )

        def persist(conn: Any) -> None:
            conn.execute(
                "INSERT INTO research_questions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    question_id,
                    version,
                    document["question"],
                    framework,
                    canonical_json(normalized_fields),
                    document["rationale"],
                    document["author"],
                    now_utc(),
                    digest,
                ),
            )

        _, revision = self.store.mutate(
            "question.amend",
            {
                "question_id": question_id,
                "version": version,
                "framework": framework,
                "content_sha256": digest,
                "hypotheses_generated": 0,
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "question_id": question_id,
            "version": version,
            "content_sha256": digest,
            "hypotheses_generated": 0,
            "project_revision": revision,
        }

    def history(self, question_id: str) -> list[dict[str, Any]]:
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_questions'"
        ).fetchone()
        if table is None:
            return []
        rows = self.store.conn.execute(
            "SELECT * FROM research_questions WHERE id=? ORDER BY version",
            (question_id,),
        ).fetchall()
        return [
            {
                "question_id": row["id"],
                "version": row["version"],
                "question": row["question"],
                "framework": row["framework"],
                "fields": json.loads(row["fields_json"]),
                "rationale": row["rationale"],
                "author": row["author"],
                "recorded_at": row["recorded_at"],
                "content_sha256": row["content_sha256"],
                "hypotheses_generated": 0,
            }
            for row in rows
        ]

    def latest(self, question_id: str) -> dict[str, Any]:
        history = self.history(question_id)
        if not history:
            raise EvidenceError(
                "NOT_FOUND",
                "Structured research question not found",
                "Choose an existing question.",
            )
        return history[-1]
