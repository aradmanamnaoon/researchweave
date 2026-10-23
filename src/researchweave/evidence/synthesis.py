"""Human-reviewed risk appraisal, contradiction, gap and synthesis workflows.

All conclusions are user-authored; this module never infers scientific truth from text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from .errors import require
from .models import canonical_json, new_id, now_utc, sha256
from .storage import ProjectStore

ASSESSMENT_DOMAINS: dict[str, tuple[str, ...]] = {
    "randomized-v1": (
        "randomization",
        "deviations",
        "missing_outcomes",
        "outcome_measurement",
        "reported_result_selection",
    ),
    "observational-v1": (
        "confounding",
        "participant_selection",
        "exposure_measurement",
        "missing_data",
        "outcome_measurement",
        "reporting",
    ),
}
JUDGMENTS = {"low", "some_concerns", "high", "unclear"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS synthesis_appraisals (
 id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES review_records(id),
 template TEXT NOT NULL, assessor TEXT NOT NULL, response_json TEXT NOT NULL,
 response_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS synthesis_appraisals_record ON synthesis_appraisals(record_id);
CREATE TABLE IF NOT EXISTS synthesis_findings (
 id TEXT PRIMARY KEY, question TEXT NOT NULL, population TEXT NOT NULL,
 outcome TEXT NOT NULL, measure TEXT NOT NULL, unit TEXT NOT NULL,
 timepoint TEXT NOT NULL, direction TEXT NOT NULL
 CHECK(direction IN ('positive','negative','null','mixed')),
 statement TEXT NOT NULL, anchor_id TEXT NOT NULL REFERENCES anchors(id),
 source_id TEXT NOT NULL REFERENCES sources(id), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS synthesis_findings_question ON synthesis_findings(question);
CREATE TABLE IF NOT EXISTS synthesis_gaps (
 id TEXT PRIMARY KEY, question TEXT NOT NULL, search_json TEXT NOT NULL,
 limitations TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','addressed')),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS synthesis_outlines (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, sections_json TEXT NOT NULL,
 content_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Finding:
    question: str
    population: str
    outcome: str
    measure: str
    unit: str
    timepoint: str
    direction: Literal["positive", "negative", "null", "mixed"]
    statement: str
    anchor_id: str


class SynthesisService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _tables(conn: Any) -> None:
        for sql in SCHEMA.strip().split(";"):
            if sql.strip():
                conn.execute(sql)

    def _has_table(self, name: str) -> bool:
        return self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    def assess_bias(
        self,
        record_id: str,
        template: str,
        assessor: str,
        responses: dict[str, dict[str, str]],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(template in ASSESSMENT_DOMAINS, "Unknown appraisal template")
        require(bool(assessor.strip()), "Assessor must be identified")
        domains = ASSESSMENT_DOMAINS[template]
        require(set(responses) == set(domains), "Every appraisal domain must have a response")
        for domain, answer in responses.items():
            require(
                isinstance(answer, dict) and answer.get("judgment") in JUDGMENTS,
                f"Invalid judgment for {domain}",
            )
            require(
                isinstance(answer.get("explanation"), str) and bool(answer["explanation"].strip()),
                f"Missing explanation for {domain}",
            )
        document = canonical_json(responses)
        appraisal_id = new_id()

        def persist(conn: Any) -> None:
            self._tables(conn)
            require(
                conn.execute("SELECT 1 FROM review_records WHERE id=?", (record_id,)).fetchone()
                is not None,
                "Review record unavailable",
                "NOT_FOUND",
            )
            conn.execute(
                "INSERT INTO synthesis_appraisals VALUES (?,?,?,?,?,?,?)",
                (
                    appraisal_id,
                    record_id,
                    template,
                    assessor,
                    document,
                    sha256(document.encode()),
                    now_utc(),
                ),
            )

        _, revision = self.store.mutate(
            "evidence.synthesis.assess_bias",
            {
                "record_id": record_id,
                "template": template,
                "response_hash": sha256(document.encode()),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "id": appraisal_id,
            "revision": revision,
            "domains": responses,
            "overall": "requires_manual_interpretation",
            "medical_decision_support": False,
        }

    def appraisals(self, record_id: str) -> list[dict[str, Any]]:
        if not self._has_table("synthesis_appraisals"):
            return []
        return [
            {**dict(r), "responses": json.loads(r["response_json"])}
            for r in self.store.conn.execute(
                "SELECT * FROM synthesis_appraisals WHERE record_id=? ORDER BY created_at,id",
                (record_id,),
            )
        ]

    def add_finding(
        self, finding: Finding, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        for name in (
            "question",
            "population",
            "outcome",
            "measure",
            "unit",
            "timepoint",
            "statement",
            "anchor_id",
        ):
            value = getattr(finding, name)
            require(
                isinstance(value, str) and bool(value.strip()) and len(value) <= 4000,
                f"{name} is required and must be bounded",
            )
        require(finding.direction in {"positive", "negative", "null", "mixed"}, "Invalid direction")
        finding_id = new_id()

        def persist(conn: Any) -> str:
            self._tables(conn)
            anchor = conn.execute(
                "SELECT a.source_id,a.verified,s.deleted FROM anchors a "
                "JOIN sources s ON s.id=a.source_id WHERE a.id=?",
                (finding.anchor_id,),
            ).fetchone()
            require(
                anchor is not None and anchor["verified"] == 1 and not anchor["deleted"],
                "Finding requires a verified anchor from an active source",
                "INTEGRITY_FAILURE",
            )
            conn.execute(
                "INSERT INTO synthesis_findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    finding_id,
                    finding.question,
                    finding.population,
                    finding.outcome,
                    finding.measure,
                    finding.unit,
                    finding.timepoint,
                    finding.direction,
                    finding.statement,
                    finding.anchor_id,
                    anchor["source_id"],
                    now_utc(),
                ),
            )
            return str(anchor["source_id"])

        source_id, revision = self.store.mutate(
            "evidence.synthesis.add_finding",
            {"anchor_id": finding.anchor_id, "statement_hash": sha256(finding.statement.encode())},
            persist,
            expected_revision=expected_revision,
        )
        return {"id": finding_id, "source_id": source_id, "revision": revision}

    def compare(self, question: str) -> dict[str, Any]:
        require(bool(question.strip()), "Question required")
        if not self._has_table("synthesis_findings"):
            return {"question": question, "groups": [], "incompatible_groups_not_pooled": False}
        rows = [
            dict(row)
            for row in self.store.conn.execute(
                "SELECT f.* FROM synthesis_findings f JOIN anchors a ON a.id=f.anchor_id "
                "JOIN sources s ON s.id=f.source_id "
                "WHERE f.question=? AND a.verified=1 AND s.deleted=0 ORDER BY f.id",
                (question,),
            )
        ]
        cohorts: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = (row["population"], row["outcome"], row["measure"], row["unit"], row["timepoint"])
            cohorts.setdefault(key, []).append(row)
        comparisons = []
        for key, members in sorted(cohorts.items()):
            directions = sorted({r["direction"] for r in members})
            comparisons.append(
                {
                    "population": key[0],
                    "outcome": key[1],
                    "measure": key[2],
                    "unit": key[3],
                    "timepoint": key[4],
                    "classification": (
                        "potential_disagreement"
                        if len(directions) > 1
                        else "same_reported_direction"
                    ),
                    "directions": directions,
                    "findings": members,
                    "interpretation": "Requires human review of heterogeneity and bias",
                }
            )
        return {
            "question": question,
            "groups": comparisons,
            "incompatible_groups_not_pooled": len(comparisons) > 1,
        }

    def register_gap(
        self,
        question: str,
        searches: list[dict[str, str]],
        limitations: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(
            bool(question.strip()) and bool(limitations.strip()),
            "Question and limitations required",
        )
        require(0 < len(searches) <= 100, "At least one bounded search is required")
        for search in searches:
            require(
                isinstance(search, dict)
                and all(
                    isinstance(search.get(field), str) and search[field].strip()
                    for field in ("database", "date", "strategy")
                ),
                "Each search needs database, date and reproducible strategy",
            )
        gap_id = new_id()
        document = canonical_json(searches)

        def persist(conn: Any) -> None:
            self._tables(conn)
            conn.execute(
                "INSERT INTO synthesis_gaps VALUES (?,?,?,?,?,?)",
                (gap_id, question, document, limitations, "open", now_utc()),
            )

        _, revision = self.store.mutate(
            "evidence.synthesis.register_gap",
            {"question": question, "search_sha256": sha256(document.encode())},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "id": gap_id,
            "revision": revision,
            "status": "open",
            "interpretation": (
                "No evidence identified by the documented searches; absence is not proven"
            ),
        }

    def gaps(self) -> list[dict[str, Any]]:
        if not self._has_table("synthesis_gaps"):
            return []
        return [
            {
                **dict(row),
                "searches": json.loads(row["search_json"]),
                "interpretation": "Evidence not identified; absence not established",
            }
            for row in self.store.conn.execute(
                "SELECT * FROM synthesis_gaps ORDER BY created_at,id"
            )
        ]

    def compose(
        self,
        title: str,
        sections: list[dict[str, Any]],
        *,
        save: bool = True,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(title.strip()) and 0 < len(sections) <= 100, "Title and sections required")
        # Preview must not alter project state or schema.
        validated = []
        for section in sections:
            heading, narrative = section.get("heading"), section.get("narrative")
            ids = section.get("finding_ids", [])
            require(
                isinstance(heading, str)
                and bool(heading.strip())
                and isinstance(narrative, str)
                and len(narrative) <= 10000,
                "Invalid section heading or narrative",
            )
            require(
                isinstance(ids, list) and len(ids) <= 200 and len(ids) == len(set(ids)),
                "Invalid finding references",
            )
            evidence = []
            for finding_id in ids:
                record = self.store.conn.execute(
                    "SELECT f.id,f.statement,f.anchor_id,f.source_id FROM synthesis_findings f "
                    "JOIN anchors a ON a.id=f.anchor_id JOIN sources s ON s.id=f.source_id "
                    "WHERE f.id=? AND a.verified=1 AND s.deleted=0",
                    (finding_id,),
                ).fetchone()
                require(record is not None, "Unverified or missing finding", "INTEGRITY_FAILURE")
                evidence.append(dict(record))
            validated.append(
                {
                    "heading": heading,
                    "narrative": narrative,
                    "evidence": evidence,
                    "attribution_status": "anchored_findings_with_unverified_narrative"
                    if evidence
                    else "UNCITED_INTERPRETATION",
                }
            )
        document = canonical_json(validated)
        result = {
            "title": title,
            "sections": validated,
            "content_hash": sha256(document.encode()),
            "scientific_conclusions_verified": False,
        }
        if save:
            outline_id = new_id()

            def persist(conn: Any) -> None:
                self._tables(conn)
                conn.execute(
                    "INSERT INTO synthesis_outlines VALUES (?,?,?,?,?)",
                    (outline_id, title, document, result["content_hash"], now_utc()),
                )

            _, revision = self.store.mutate(
                "evidence.synthesis.compose",
                {"title": title, "hash": result["content_hash"]},
                persist,
                expected_revision=expected_revision,
            )
            result.update({"id": outline_id, "revision": revision})
        return result

    def outline(self, outline_id: str) -> dict[str, Any]:
        require(self._has_table("synthesis_outlines"), "Outline not found", "NOT_FOUND")
        row = self.store.conn.execute(
            "SELECT * FROM synthesis_outlines WHERE id=?", (outline_id,)
        ).fetchone()
        require(row is not None, "Outline not found", "NOT_FOUND")
        return {**dict(row), "sections": json.loads(row["sections_json"])}
