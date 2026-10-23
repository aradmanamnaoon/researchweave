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
    "rob2-compatible-v1": (
        "randomization",
        "deviations",
        "missing_outcomes",
        "outcome_measurement",
        "reported_result_selection",
    ),
    "robins-i-compatible-v1": (
        "confounding",
        "participant_selection",
        "exposure_classification",
        "deviations",
        "missing_data",
        "outcome_measurement",
        "reported_result_selection",
    ),
}
JUDGMENTS = {"low", "some_concerns", "high", "unclear"}
BIAS_TEMPLATES: dict[str, dict[str, Any]] = {
    "randomized-v1": {
        "label": "Randomized study appraisal",
        "methodology": "general randomized-study domains",
        "version": 1,
        "official_instrument": False,
    },
    "observational-v1": {
        "label": "Observational study appraisal",
        "methodology": "general observational-study domains",
        "version": 1,
        "official_instrument": False,
    },
    "rob2-compatible-v1": {
        "label": "RoB 2 compatible workflow",
        "methodology": "Cochrane RoB 2 domain structure compatibility",
        "version": 1,
        "official_instrument": False,
    },
    "robins-i-compatible-v1": {
        "label": "ROBINS-I compatible workflow",
        "methodology": "ROBINS-I domain structure compatibility",
        "version": 1,
        "official_instrument": False,
    },
}

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
 source_id TEXT NOT NULL REFERENCES sources(id), created_at TEXT NOT NULL,
 record_id TEXT REFERENCES review_records(id), study_id TEXT, uncertainty TEXT
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
CREATE TABLE IF NOT EXISTS synthesis_gap_updates (
 id TEXT PRIMARY KEY, gap_id TEXT NOT NULL REFERENCES synthesis_gaps(id),
 status TEXT NOT NULL CHECK(status IN ('open','addressed')),
 priority TEXT NOT NULL CHECK(priority IN ('low','medium','high','critical')),
 rationale TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS synthesis_gap_updates_gap ON synthesis_gap_updates(gap_id,created_at);
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
    record_id: str | None = None
    uncertainty: str | None = None


class SynthesisService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _tables(conn: Any) -> None:
        for sql in SCHEMA.strip().split(";"):
            if sql.strip():
                conn.execute(sql)
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(synthesis_findings)")
        }
        if "record_id" not in columns:
            conn.execute("ALTER TABLE synthesis_findings ADD COLUMN record_id TEXT")
        if "study_id" not in columns:
            conn.execute("ALTER TABLE synthesis_findings ADD COLUMN study_id TEXT")
        if "uncertainty" not in columns:
            conn.execute("ALTER TABLE synthesis_findings ADD COLUMN uncertainty TEXT")

    def _has_table(self, name: str) -> bool:
        return self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    @staticmethod
    def bias_templates() -> list[dict[str, Any]]:
        """Describe supported appraisal structures without claiming official certification."""
        return [
            {"id": template, **BIAS_TEMPLATES[template],
             "domains": list(ASSESSMENT_DOMAINS[template]),
             "judgments": sorted(JUDGMENTS),
             "definitive_judgments_require_verified_anchor": True}
            for template in sorted(ASSESSMENT_DOMAINS)
        ]

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
            uncertainty = answer.get("uncertainty")
            require(
                uncertainty is None
                or uncertainty in {"low", "moderate", "high", "unknown"},
                f"Invalid uncertainty for {domain}",
            )
            anchor_id = answer.get("anchor_id")
            require(anchor_id is None or isinstance(anchor_id, str),
                    f"Invalid anchor for {domain}")
            require(answer.get("judgment") == "unclear" or bool(anchor_id),
                    f"Definitive judgment for {domain} requires a verified source anchor")
            if anchor_id:
                anchor = self.store.conn.execute(
                    "SELECT a.verified,s.deleted FROM anchors a "
                    "JOIN sources s ON s.id=a.source_id WHERE a.id=?",
                    (anchor_id,),
                ).fetchone()
                require(
                    anchor is not None and bool(anchor["verified"]) and not bool(anchor["deleted"]),
                    f"Risk-of-bias anchor for {domain} is missing or unverified",
                    "INTEGRITY_FAILURE",
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
            "framework_certification": "compatible_workflow_not_official_instrument",
            "template_metadata": BIAS_TEMPLATES[template],
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
        require(
            finding.uncertainty is None
            or isinstance(finding.uncertainty, str) and len(finding.uncertainty) <= 4000,
            "Finding uncertainty must be bounded text",
        )
        finding_id = new_id()

        def persist(conn: Any) -> tuple[str, str | None]:
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
            study_id: str | None = None
            if finding.record_id is not None:
                record = conn.execute(
                    "SELECT study_id FROM review_records WHERE id=?", (finding.record_id,)
                ).fetchone()
                require(record is not None, "Finding review record not found", "NOT_FOUND")
                registry = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='review_study_reports'"
                ).fetchone()
                if registry is not None:
                    linked = conn.execute(
                        "SELECT study_id FROM review_study_reports WHERE record_id=?",
                        (finding.record_id,),
                    ).fetchone()
                    if linked is not None:
                        study_id = str(linked["study_id"])
                if study_id is None and record["study_id"] is not None:
                    study_id = str(record["study_id"])
            conn.execute(
                "INSERT INTO synthesis_findings("
                "id,question,population,outcome,measure,unit,timepoint,direction,statement,"
                "anchor_id,source_id,created_at,record_id,study_id,uncertainty) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    finding.record_id,
                    study_id,
                    finding.uncertainty,
                ),
            )
            return str(anchor["source_id"]), study_id

        persisted, revision = self.store.mutate(
            "evidence.synthesis.add_finding",
            {"anchor_id": finding.anchor_id, "statement_hash": sha256(finding.statement.encode())},
            persist,
            expected_revision=expected_revision,
        )
        source_id, study_id = persisted
        return {"id": finding_id, "source_id": source_id, "record_id": finding.record_id,
                "study_id": study_id, "revision": revision}

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
            identified_studies = {str(r["study_id"]) for r in members if r.get("study_id")}
            identified_records = {str(r["record_id"]) for r in members if r.get("record_id")}
            identity_complete = all(r.get("record_id") for r in members)
            if len(directions) <= 1:
                classification = "same_reported_direction"
            elif not identity_complete:
                classification = "identity_unresolved_directional_difference"
            elif len(identified_studies) > 1:
                classification = "between_study_potential_conflict"
            elif len(identified_studies) == 1 or len(identified_records) > 1:
                classification = "within_study_or_report_disagreement"
            else:
                classification = "potential_disagreement"
            comparisons.append(
                {
                    "population": key[0],
                    "outcome": key[1],
                    "measure": key[2],
                    "unit": key[3],
                    "timepoint": key[4],
                    "classification": classification,
                    "directions": directions,
                    "findings": members,
                    "identity_complete": identity_complete,
                    "study_ids": sorted(identified_studies),
                    "record_ids": sorted(identified_records),
                    "interpretation": (
                        "Directional differences require human review of study identity, "
                        "heterogeneity, measurement and risk of bias"
                    ),
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

    def update_gap(
        self,
        gap_id: str,
        status: str,
        priority: str,
        rationale: str,
        actor: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(status in {"open", "addressed"}, "Unknown evidence-gap status")
        require(priority in {"low", "medium", "high", "critical"},
                "Unknown evidence-gap priority")
        require(bool(rationale.strip()) and len(rationale) <= 5000,
                "Gap update rationale is required")
        require(bool(actor.strip()) and len(actor) <= 255, "Gap update actor is required")
        require(
            self._has_table("synthesis_gaps")
            and self.store.conn.execute(
                "SELECT 1 FROM synthesis_gaps WHERE id=?", (gap_id,)
            ).fetchone() is not None,
            "Evidence gap not found",
            "NOT_FOUND",
        )
        update_id = new_id()

        def persist(conn: Any) -> None:
            self._tables(conn)
            conn.execute(
                "INSERT INTO synthesis_gap_updates VALUES (?,?,?,?,?,?,?)",
                (
                    update_id,
                    gap_id,
                    status,
                    priority,
                    rationale.strip(),
                    actor.strip(),
                    now_utc(),
                ),
            )
            conn.execute(
                "UPDATE synthesis_gaps SET status=? WHERE id=?", (status, gap_id)
            )

        _, revision = self.store.mutate(
            "evidence.synthesis.update_gap",
            {
                "gap_id": gap_id,
                "status": status,
                "priority": priority,
                "actor": actor.strip(),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "update_id": update_id,
            "gap_id": gap_id,
            "status": status,
            "priority": priority,
            "revision": revision,
        }

    def gaps(self) -> list[dict[str, Any]]:
        if not self._has_table("synthesis_gaps"):
            return []
        updates_exist = self._has_table("synthesis_gap_updates")
        output = []
        for row in self.store.conn.execute(
            "SELECT * FROM synthesis_gaps ORDER BY created_at,id"
        ):
            updates = (
                [
                    dict(item)
                    for item in self.store.conn.execute(
                        "SELECT * FROM synthesis_gap_updates WHERE gap_id=? "
                        "ORDER BY rowid",
                        (row["id"],),
                    )
                ]
                if updates_exist
                else []
            )
            output.append({
                **dict(row),
                "searches": json.loads(row["search_json"]),
                "updates": updates,
                "priority": updates[-1]["priority"] if updates else "unprioritized",
                "interpretation": "Evidence not identified; absence not established",
            })
        return output

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
        validated: list[dict[str, Any]] = []
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
                    "SELECT f.id,f.statement,f.anchor_id,f.source_id,f.population,f.outcome,"
                    "f.measure,f.unit,f.timepoint,f.direction FROM synthesis_findings f "
                    "JOIN anchors a ON a.id=f.anchor_id JOIN sources s ON s.id=f.source_id "
                    "WHERE f.id=? AND a.verified=1 AND s.deleted=0",
                    (finding_id,),
                ).fetchone()
                require(record is not None, "Unverified or missing finding", "INTEGRITY_FAILURE")
                evidence.append(dict(record))
            comparable: dict[tuple[str, str, str, str, str], set[str]] = {}
            for item in evidence:
                key = (
                    str(item["population"]), str(item["outcome"]), str(item["measure"]),
                    str(item["unit"]), str(item["timepoint"]),
                )
                comparable.setdefault(key, set()).add(str(item["direction"]))
            contradictions = [
                {"population": key[0], "outcome": key[1], "measure": key[2],
                 "unit": key[3], "timepoint": key[4], "directions": sorted(directions)}
                for key, directions in sorted(comparable.items()) if len(directions) > 1
            ]
            warnings = []
            if not evidence:
                warnings.append("UNSUPPORTED_NARRATIVE_NO_FINDINGS")
            if contradictions:
                warnings.append("UNRESOLVED_COMPARABLE_FINDING_CONTRADICTION")
            if evidence:
                warnings.append("EVIDENCE_STRENGTH_NOT_AUTOMATICALLY_ASSESSED")
            validated.append(
                {
                    "heading": heading,
                    "narrative": narrative,
                    "evidence": evidence,
                    "contradictions": contradictions,
                    "warnings": warnings,
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
            "unresolved_contradictions": sum(
                len(section["contradictions"]) for section in validated
            ),
            "unsupported_sections": sum(1 for section in validated if not section["evidence"]),
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

    def export_outline_markdown(self, outline_id: str) -> str:
        outline = self.outline(outline_id)
        lines = [
            f"# {outline['title']}",
            "",
            "Scientific conclusions are not automatically verified; each evidence entry "
            "retains its source and anchor identifiers.",
            "",
        ]
        for section in outline["sections"]:
            lines.extend([f"## {section['heading']}", "", section["narrative"], ""])
            if section["evidence"]:
                lines.extend(["Evidence:", ""])
                for evidence in section["evidence"]:
                    lines.append(
                        f"- {evidence['statement']} "
                        f"[source={evidence['source_id']}; anchor={evidence['anchor_id']}]"
                    )
                lines.append("")
            else:
                lines.extend(["- UNCITED_INTERPRETATION", ""])
            if section.get("warnings"):
                lines.extend(["Warnings:", ""])
                lines.extend(f"- {warning}" for warning in section["warnings"])
                lines.append("")
        return "\n".join(lines)
