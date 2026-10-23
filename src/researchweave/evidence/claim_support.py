"""Explicit manuscript claims linked to exact verified evidence anchors."""

from __future__ import annotations

from typing import Any

from .errors import require
from .library import LibraryService
from .models import new_id, now_utc, sha256
from .storage import ProjectStore


class ClaimSupportService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.library = LibraryService(store)

    @staticmethod
    def _table(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS manuscript_claims ("
            "id TEXT PRIMARY KEY, manuscript_id TEXT NOT NULL, section TEXT NOT NULL, "
            "section_revision INTEGER NOT NULL, statement TEXT NOT NULL, "
            "statement_start INTEGER NOT NULL, statement_end INTEGER NOT NULL, "
            "anchor_id TEXT REFERENCES anchors(id), classification TEXT NOT NULL, "
            "actor TEXT NOT NULL, rationale TEXT NOT NULL, created_at TEXT NOT NULL)"
        )

    def add(
        self,
        manuscript_id: str,
        section: str,
        statement: str,
        statement_start: int,
        statement_end: int,
        actor: str,
        rationale: str,
        *,
        anchor_id: str | None = None,
        interpretation: bool = False,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(statement) and len(statement) <= 10_000, "Claim statement is required")
        require(bool(actor.strip()) and len(actor) <= 255, "Claim actor is required")
        require(bool(rationale.strip()) and len(rationale) <= 5000, "Claim rationale is required")
        row = self.store.conn.execute(
            "SELECT * FROM manuscripts WHERE id=? AND section=? "
            "ORDER BY revision DESC LIMIT 1",
            (manuscript_id, section),
        ).fetchone()
        require(row is not None, "Manuscript section not found", "NOT_FOUND")
        body = str(row["body"])
        require(
            0 <= statement_start < statement_end <= len(body)
            and body[statement_start:statement_end] == statement,
            "Claim span does not match the current manuscript revision",
            "INTEGRITY_FAILURE",
        )
        if interpretation:
            require(anchor_id is None, "Interpretive claims cannot be marked evidence-backed")
            classification = "human_interpretation"
        else:
            require(anchor_id is not None, "Evidence-backed claim requires an exact anchor")
            anchor = self.store.conn.execute(
                "SELECT a.*,s.deleted FROM anchors a JOIN sources s ON s.id=a.source_id "
                "WHERE a.id=?",
                (anchor_id,),
            ).fetchone()
            require(
                anchor is not None and bool(anchor["verified"]) and not bool(anchor["deleted"]),
                "Claim anchor is missing, unverified or deleted",
                "INTEGRITY_FAILURE",
            )
            source_text = self.library.source_text(str(anchor["source_id"]))
            require(
                sha256(source_text.encode()) == anchor["body_hash"]
                and source_text[anchor["start"]:anchor["end"]] == anchor["quote"],
                "Claim anchor is stale",
                "INTEGRITY_FAILURE",
            )
            classification = "evidence_backed"
        claim_id = new_id()

        def persist(conn: Any) -> None:
            self._table(conn)
            conn.execute(
                "INSERT INTO manuscript_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    claim_id,
                    manuscript_id,
                    section,
                    row["revision"],
                    statement,
                    statement_start,
                    statement_end,
                    anchor_id,
                    classification,
                    actor.strip(),
                    rationale.strip(),
                    now_utc(),
                ),
            )

        _, revision = self.store.mutate(
            "writing.claim_add",
            {
                "claim_id": claim_id,
                "manuscript_id": manuscript_id,
                "section": section,
                "section_revision": row["revision"],
                "anchor_id": anchor_id,
                "classification": classification,
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "claim_id": claim_id,
            "classification": classification,
            "section_revision": row["revision"],
            "project_revision": revision,
            "scientific_truth_verified": False,
        }

    def check(self, manuscript_id: str) -> dict[str, Any]:
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='manuscript_claims'"
        ).fetchone()
        if table is None:
            return {
                "claims": [],
                "issues": [],
                "registered_claims": 0,
                "claim_coverage_complete": False,
                "scientific_truth_verified": False,
            }
        claims = [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT * FROM manuscript_claims WHERE manuscript_id=? ORDER BY created_at,id",
                (manuscript_id,),
            )
        ]
        issues: list[dict[str, Any]] = []
        checked: list[dict[str, Any]] = []
        for claim in claims:
            current = self.store.conn.execute(
                "SELECT * FROM manuscripts WHERE id=? AND section=? "
                "ORDER BY revision DESC LIMIT 1",
                (manuscript_id, claim["section"]),
            ).fetchone()
            if current is None:
                issues.append({"claim_id": claim["id"], "code": "CLAIM_SECTION_MISSING"})
                checked.append({**claim, "status": "stale_section"})
                continue
            same_revision = current["revision"] == claim["section_revision"]
            span_matches = (
                claim["statement_end"] <= len(current["body"])
                and current["body"][claim["statement_start"]:claim["statement_end"]]
                == claim["statement"]
            )
            if not same_revision or not span_matches:
                issues.append({"claim_id": claim["id"], "code": "CLAIM_STALE_AFTER_EDIT"})
                checked.append({**claim, "status": "stale_manuscript"})
                continue
            if claim["classification"] == "evidence_backed":
                anchor = self.store.conn.execute(
                    "SELECT a.*,s.deleted FROM anchors a JOIN sources s ON s.id=a.source_id "
                    "WHERE a.id=?",
                    (claim["anchor_id"],),
                ).fetchone()
                if anchor is None or not anchor["verified"] or anchor["deleted"]:
                    issues.append({"claim_id": claim["id"], "code": "CLAIM_ANCHOR_INVALID"})
                    checked.append({**claim, "status": "invalid_anchor"})
                    continue
                source_text = self.library.source_text(str(anchor["source_id"]))
                if (
                    sha256(source_text.encode()) != anchor["body_hash"]
                    or source_text[anchor["start"]:anchor["end"]] != anchor["quote"]
                ):
                    issues.append({"claim_id": claim["id"], "code": "CLAIM_ANCHOR_STALE"})
                    checked.append({**claim, "status": "stale_anchor"})
                    continue
            checked.append({**claim, "status": "current"})
        return {
            "claims": checked,
            "issues": issues,
            "registered_claims": len(claims),
            "claim_coverage_complete": False,
            "scientific_truth_verified": False,
        }
