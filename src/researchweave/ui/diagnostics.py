"""Deterministic read-only project integrity and methodological readiness audit.

This report checks recorded data consistency and highlights work to review.
It does not certify that research designs, methods or conclusions are correct.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .contracts import Project, UIError
from .evidence import inspect_anchor
from .research_guides import protocol_completion

IssueSeverity = Literal["error", "warning", "info"]
MAX_REPORTED_FINDINGS = 400
MAX_DATASET_AUDIT_ROWS = 50_000
SENSITIVE = ("password", "token", "api_key", "secret", "private_key")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: IssueSeverity
    title: str
    location: str
    message: str
    recovery: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class QualityMetric:
    name: str
    value: int | float | str
    interpretation: str
    unit: str = ""

    def as_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


class AuditReport:
    def __init__(self, project: Project) -> None:
        self.project_id = project.id
        self.revision = project.revision
        self.title = project.title
        self.issues: list[Finding] = []
        self.metrics: list[QualityMetric] = []

    def add(
        self, code: str, severity: IssueSeverity, title: str, location: str,
        message: str, recovery: str,
    ) -> None:
        if len(self.issues) < MAX_REPORTED_FINDINGS:
            self.issues.append(
                Finding(code, severity, title, location, message, recovery)
            )

    def measure(self, name: str, value: int | float | str,
                interpretation: str, unit: str = "") -> None:
        self.metrics.append(QualityMetric(name, value, interpretation, unit))

    def export(self) -> dict[str, Any]:
        codes = Counter(finding.severity for finding in self.issues)
        return {
            "schema_version": 1,
            "project_id": self.project_id,
            "project_revision": self.revision,
            "project_title": self.title,
            "status": (
                "integrity-issues" if codes["error"] else
                "review-recommended" if codes["warning"] else
                "no-detected-integrity-issues"
            ),
            "summary": {
                "errors": codes["error"], "warnings": codes["warning"],
                "information": codes["info"],
                "findings_shown": len(self.issues),
                "findings_truncated": len(self.issues) >= MAX_REPORTED_FINDINGS,
            },
            "metrics": [item.as_dict() for item in self.metrics],
            "findings": [item.as_dict() for item in self.issues],
            "checks": [
                "source-sha256", "duplicate-text", "screening-inclusion",
                "annotation-spans", "evidence-links", "claim-links",
                "dataset-rectangularity", "variable-missingness",
                "activity-sequence", "protocol-completeness",
            ],
            "limitations": [
                "This is a metadata and local structural integrity audit only.",
                "A hash match never establishes scientific validity or a reliable citation.",
                "Checking ethics compliance, consent and confidential data requires humans.",
                "Only serialized project records were checked, not external raw files.",
            ],
        }


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def audit_project(project: Project) -> dict[str, Any]:
    report = AuditReport(project)
    report.measure(
        "project revision", project.revision,
        "Stored optimistic concurrency revision",
    )
    report.measure("sources", len(project.sources), "Project source records")
    report.measure("screening decisions", len(project.votes),
                   "Saved screening decisions, not PRISMA stages")
    report.measure("annotations", len(project.annotations),
                   "Direct local text-span annotations")
    report.measure("evidence excerpts", len(project.evidence),
                   "Anchored excerpts with source hashes")
    report.measure("draft claims", len(project.claims),
                   "Claims needing human scientific assessment")
    report.measure("datasets", len(project.datasets),
                   "Imported local preview tables")

    source_by_id = {source.id: source for source in project.sources}
    source_hashes = Counter(_digest(source.text) for source in project.sources)
    duplicate_hashes = {digest for digest, count in source_hashes.items() if count > 1}
    bad_source_hashes = 0
    for source in project.sources:
        current_hash = _digest(source.text)
        if source.content_hash and current_hash != source.content_hash:
            bad_source_hashes += 1
            report.add(
                "SOURCE_HASH_MISMATCH", "error", "Source text hash changed",
                f"source:{source.id}",
                "Source bytes no longer match recorded SHA-256.",
                "Restore the expected text or import a new immutable source version.",
            )
        if current_hash in duplicate_hashes:
            report.add(
                "DUPLICATE_SOURCE", "warning", "Duplicate source text",
                f"source:{source.id}",
                "This record has content identical to another source entry.",
                "Compare records, citations and identifiers before deduplicating.",
            )
        if not source.verified:
            report.add(
                "SOURCE_UNVERIFIED", "info", "Source metadata unverified",
                f"source:{source.id}",
                "Record has not been marked as bibliographically verified.",
                "Read original full text and verify author, title and publication details.",
            )
    report.measure("source hash mismatches", bad_source_hashes,
                   "Checksum disagreements requiring correction")
    report.measure("duplicate-text groups", len(duplicate_hashes),
                   "Same content stored under multiple source records")

    votes_by_source: dict[str, int] = {}
    for vote in project.votes:
        votes_by_source[vote.source_id] = votes_by_source.get(vote.source_id, 0) + 1
        if vote.source_id not in source_by_id:
            report.add(
                "ORPHAN_VOTE", "error", "Screening vote source missing",
                f"screening:{vote.source_id}",
                "This decision references a source not present in the project.",
                "Restore the original source and rescreen it.",
            )
        if vote.decision == "exclude" and not vote.reason.strip():
            report.add(
                "EXCLUSION_REASON_MISSING", "warning",
                "Excluded record lacks a reason",
                f"screening:{vote.source_id}",
                "An exclusion decision has no documented rationale.",
                "Record a protocol-aligned exclusion reason.",
            )
    for source_id, count in votes_by_source.items():
        if count > 1:
            report.add(
                "MULTIPLE_SCREENING_VOTES", "warning",
                "Multiple decisions for a source",
                f"screening:{source_id}",
                f"{count} records currently refer to the same source.",
                "Review decision history and adjudicate conflicts explicitly.",
            )

    bad_annotations = 0
    for annotation in project.annotations:
        annotation_source = source_by_id.get(annotation.source_id)
        if (annotation_source is None
                or not 0 <= annotation.start < annotation.end <= len(annotation_source.text)
                or annotation_source.text[annotation.start:annotation.end] != annotation.quote):
            bad_annotations += 1
            report.add(
                "ANNOTATION_INVALID", "error", "Annotation no longer matches source",
                f"annotation:{annotation.id}",
                "Saved source offsets or quoted text are inconsistent.",
                "Check the original text, offset and quote before recoding.",
            )
    report.measure("invalid annotations", bad_annotations,
                   "Coded passages that do not match source records")

    evidence_by_id = {evidence.id: evidence for evidence in project.evidence}
    invalid_anchors = 0
    for anchor in project.evidence:
        if anchor.source_id not in source_by_id:
            invalid_anchors += 1
            report.add(
                "EVIDENCE_ORPHAN", "error", "Evidence source missing",
                f"evidence:{anchor.id}",
                "Evidence record references an unknown source.",
                "Restore the original source before relying on the quote.",
            )
            continue
        integrity = inspect_anchor(project, anchor)
        if integrity["integrity"] != "matched":
            invalid_anchors += 1
            report.add(
                "EVIDENCE_INTEGRITY", "error", "Evidence quotation mismatch",
                f"evidence:{anchor.id}",
                "Source hash, offsets or quoted bytes disagree with saved evidence.",
                "Re-verify the original passage and create a new linked record.",
            )
    report.measure("broken evidence anchors", invalid_anchors,
                   "Source-linked excerpts failing integrity checks")

    unsupported_claims = 0
    for claim in project.claims:
        if not claim.supporting_evidence:
            unsupported_claims += 1
            report.add(
                "CLAIM_NO_SUPPORT", "warning", "Draft claim lacks evidence",
                f"claim:{claim.id}",
                "No supporting anchor has been linked to this statement.",
                "Attach a verified relevant source excerpt or remove the claim.",
            )
        for identifier in claim.supporting_evidence + claim.challenging_evidence:
            if identifier not in evidence_by_id:
                report.add(
                    "CLAIM_ORPHAN_REFERENCE", "error", "Claim anchor missing",
                    f"claim:{claim.id}",
                    "A linked evidence identifier is absent from the project.",
                    "Restore the anchor and review the claim.",
                )
        if claim.challenging_evidence:
            report.add(
                "CLAIM_CHALLENGED", "info", "Claim has conflicting evidence",
                f"claim:{claim.id}",
                "The draft records material that may challenge its conclusion.",
                "Keep and discuss contradictory evidence in the manuscript.",
            )
    report.measure("claims without support", unsupported_claims,
                   "Draft statements without source-linked evidence")

    for dataset in project.datasets:
        expected_columns = len(dataset.columns)
        if len(set(dataset.columns)) != expected_columns:
            report.add(
                "DUPLICATE_COLUMN", "error", "Duplicate dataset variable names",
                f"dataset:{dataset.id}",
                "Column labels are not unique.",
                "Disambiguate variable names with explicit units or identifiers.",
            )
        if len(dataset.rows) > MAX_DATASET_AUDIT_ROWS:
            report.add(
                "DATASET_SIZE_LIMIT", "warning", "Dataset exceeds audit row limit",
                f"dataset:{dataset.id}",
                "Complete row-level checks were not performed.",
                "Validate this table with a streaming production data adapter.",
            )
        for index, row in enumerate(dataset.rows[:MAX_DATASET_AUDIT_ROWS]):
            if len(row) != expected_columns:
                report.add(
                    "RAGGED_DATASET", "error", "Dataset row width mismatch",
                    f"dataset:{dataset.id}:row:{index + 1}",
                    "This row has a different number of cells than the header.",
                    "Reimport the original data after validating rectangularity.",
                )
                if len(report.issues) >= MAX_REPORTED_FINDINGS:
                    break
        missing = sum(
            1 for row in dataset.rows if any(not str(value).strip() for value in row)
        )
        report.measure(
            f"missing-cell rows in {dataset.name}", missing,
            "Number of records with at least one empty string cell", "rows",
        )
        if missing:
            report.add(
                "MISSING_DATA", "info", "Dataset contains missing values",
                f"dataset:{dataset.id}",
                f"{missing} data rows contain at least one empty cell.",
                "Document missingness assumptions and transformations.",
            )
    expected = 1
    for event in project.activity:
        if event.sequence != expected:
            report.add(
                "AUDIT_SEQUENCE", "warning", "Activity history sequence gap",
                f"activity:{event.sequence}",
                "Saved activity history is not a contiguous sequence.",
                "Review the activity log and retained event history.",
            )
            expected = event.sequence
        expected += 1
    if project.protocol:
        template_id = project.protocol.get("template_id")
        values = project.protocol.get("values")
        if isinstance(template_id, str) and isinstance(values, dict):
            try:
                completion = protocol_completion(template_id, values)
            except UIError:
                report.add(
                    "PROTOCOL_TEMPLATE_UNKNOWN", "error", "Protocol template missing",
                    "protocol",
                    "Project draft uses an unknown research design template.",
                    "Select a supported template and manually migrate the draft.",
                )
            else:
                if completion["required_missing"]:
                    report.add(
                        "PROTOCOL_INCOMPLETE", "warning",
                        "Research protocol needs required fields",
                        "protocol",
                        "Required protocol fields remain empty.",
                        "Complete these fields before scientific review.",
                    )
        else:
            report.add(
                "PROTOCOL_INVALID", "error", "Protocol structure is invalid",
                "protocol", "Draft protocol has missing or malformed data.",
                "Restore a valid protocol record.",
            )
    if any(
        keyword in project.notebook.casefold()[:2000]
        for keyword in SENSITIVE
    ):
        report.add(
            "POTENTIAL_SECRET_IN_NOTES", "warning", "Potential secret label in notes",
            "notebook",
            "A credential-related keyword appears in local notebook text.",
            "Review locally before exporting or syncing. No sensitive contents are shown.",
        )
    return report.export()
