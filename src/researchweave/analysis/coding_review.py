"""Coded evidence review, provenance-preserving adjudication and stable relocation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .errors import require
from .models import digest, utc_now
from .qualitative import Annotation, CodingProject, Transcript


@dataclass(frozen=True)
class CodingDecision:
    decision_id: str
    original_annotation_index: int
    disposition: Literal["accept", "reject", "needs_review"]
    reviewer: str
    rationale: str
    source_hash: str
    timestamp: str


@dataclass(frozen=True)
class RelocationProposal:
    source_id: str
    original_hash: str
    revised_hash: str
    start: int | None
    end: int | None
    exact_quote: str
    status: Literal["unique", "ambiguous", "missing"]
    candidate_count: int
    confidence: str


@dataclass
class CodingReviewLedger:
    """Append-only in-memory event log with deterministic conflict detection."""

    project: CodingProject
    events: list[CodingDecision] = field(default_factory=list)

    def _annotation(self, ordinal: int) -> Annotation:
        require(
            0 <= ordinal < len(self.project.annotations), "Annotation does not exist", "NOT_FOUND"
        )
        return self.project.annotations[ordinal]

    def decide(
        self, annotation_index: int, disposition: str, *, reviewer: str, rationale: str
    ) -> CodingDecision:
        annotation = self._annotation(annotation_index)
        require(
            self.project.verify(annotation), "Original source text differs", "INTEGRITY_FAILURE"
        )
        require(disposition in ("accept", "reject", "needs_review"), "Unknown disposition")
        require(
            bool(reviewer.strip()) and bool(rationale.strip()),
            "Decision must carry reviewer and reason",
        )
        # Multiple reviews can be appended, but the same reviewer cannot vote twice on one anchor.
        require(
            not any(
                event.original_annotation_index == annotation_index and event.reviewer == reviewer
                for event in self.events
            ),
            "Duplicate reviewer decision",
            "CONFLICT",
        )
        sequence = len(self.events)
        identity = digest(
            {
                "project_hash": digest(self.project.to_json()),
                "sequence": sequence,
                "annotation_index": annotation_index,
                "disposition": disposition,
                "reviewer": reviewer,
                "rationale": rationale,
            }
        )
        event = CodingDecision(
            identity,
            annotation_index,
            disposition,
            reviewer,
            rationale,
            annotation.source_hash,
            utc_now(),
        )
        self.events.append(event)
        return event

    def consensus(self, *, minimum_reviewers: int = 2) -> dict[int, dict[str, Any]]:
        """Only unanimous independent reviewers produce final acceptance/rejection."""
        require(2 <= minimum_reviewers <= 20, "Reviewer threshold must be between 2 and 20")
        grouped: dict[int, list[CodingDecision]] = {}
        for event in self.events:
            grouped.setdefault(event.original_annotation_index, []).append(event)
        summary = {}
        for index in range(len(self.project.annotations)):
            votes = grouped.get(index, [])
            require(
                len({event.reviewer for event in votes}) == len(votes),
                "Duplicate reviewer identities in ledger",
                "INTEGRITY_FAILURE",
            )
            if len(votes) < minimum_reviewers:
                status = "requires_review"
            elif all(event.disposition == "accept" for event in votes):
                status = "accepted"
            elif all(event.disposition == "reject" for event in votes):
                status = "rejected"
            else:
                status = "conflict"
            summary[index] = {
                "status": status,
                "votes": len(votes),
                "reviewers": [event.reviewer for event in votes],
                "dispositions": [event.disposition for event in votes],
            }
        return summary

    def export_json(self) -> dict[str, Any]:
        return {
            "schema": "researchweave.coding_decisions.v1",
            "project_hash": digest(self.project.to_json()),
            "events": [asdict(event) for event in self.events],
            "event_hash": digest([asdict(event) for event in self.events]),
        }

    @classmethod
    def load_json(cls, project: CodingProject, obj: dict[str, Any]) -> CodingReviewLedger:
        require(
            obj.get("schema") == "researchweave.coding_decisions.v1",
            "Unknown event schema",
            "SCHEMA_MISMATCH",
        )
        require(
            obj.get("project_hash") == digest(project.to_json()),
            "Underlying transcript/codebook has changed",
            "INTEGRITY_FAILURE",
        )
        require(
            obj.get("event_hash") == digest(obj.get("events")),
            "Decision ledger checksum mismatch",
            "INTEGRITY_FAILURE",
        )
        ledger = cls(project)
        for data in obj["events"]:
            event = CodingDecision(**data)
            anchor = ledger._annotation(event.original_annotation_index)
            require(
                event.source_hash == anchor.source_hash and project.verify(anchor),
                "Decision source invalid",
                "INTEGRITY_FAILURE",
            )
            require(
                not any(
                    prior.reviewer == event.reviewer
                    and prior.original_annotation_index == event.original_annotation_index
                    for prior in ledger.events
                ),
                "Duplicate review event",
                "INTEGRITY_FAILURE",
            )
            ledger.events.append(event)
        return ledger


def propose_relocation(annotation: Annotation, revised: Transcript) -> RelocationProposal:
    """Find unchanged quote in revised text; refuse ambiguous or absent matches.

    Does not silently shift offsets on edit or claim semantic correspondence.
    """
    require(
        annotation.source_id == revised.source_id,
        "Relocation source identifier differs",
        "SCHEMA_MISMATCH",
    )
    quote = annotation.quote
    require(bool(quote), "Cannot relocate empty quotation")
    matches: list[int] = []
    search_from = 0
    while True:
        index = revised.text.find(quote, search_from)
        if index < 0:
            break
        matches.append(index)
        require(len(matches) <= 1000, "Too many anchor candidates", "RESOURCE_LIMIT")
        search_from = index + 1
    status: Literal["unique", "ambiguous", "missing"] = (
        "unique" if len(matches) == 1 else "ambiguous" if matches else "missing"
    )
    return RelocationProposal(
        annotation.source_id,
        annotation.source_hash,
        revised.checksum,
        matches[0] if status == "unique" else None,
        matches[0] + len(quote) if status == "unique" else None,
        quote,
        status,
        len(matches),
        "exact-text match only" if matches else "none",
    )


def apply_relocation(
    proposal: RelocationProposal,
    *,
    reviewer_approved: bool,
    code_id: str,
    coder: str,
    unit_id: str,
    revised: Transcript,
) -> Annotation:
    require(reviewer_approved, "Relocation requires user review", "NEEDS_APPROVAL")
    require(proposal.status == "unique", "Ambiguous/absent quote cannot be relocated")
    require(
        revised.checksum == proposal.revised_hash and revised.source_id == proposal.source_id,
        "Revised source hash changed",
        "INTEGRITY_FAILURE",
    )
    require(
        revised.text[proposal.start : proposal.end] == proposal.exact_quote,
        "Revised quotation no longer matches",
        "INTEGRITY_FAILURE",
    )
    return Annotation(
        proposal.source_id,
        revised.checksum,
        proposal.start,
        proposal.end,
        proposal.exact_quote,
        code_id,
        coder,
        unit_id,
    )


def disagreements(
    project: CodingProject, *, coder_a: str, coder_b: str, unit_ids: list[str]
) -> list[dict[str, Any]]:
    """Disagreements over declared unit IDs; refuse duplicated unit/coder labels."""
    require(
        coder_a != coder_b and bool(coder_a) and bool(coder_b),
        "Two different named coders required",
    )
    require(
        len(set(unit_ids)) == len(unit_ids) and unit_ids,
        "Explicit distinct coding-unit IDs required",
    )
    labels: dict[str, dict[str, str]] = {coder_a: {}, coder_b: {}}
    for annotation in project.annotations:
        if annotation.coder not in labels or annotation.unit_id not in unit_ids:
            continue
        require(project.verify(annotation), "Annotation anchor differs", "INTEGRITY_FAILURE")
        mapping = labels[annotation.coder]
        require(
            annotation.unit_id not in mapping,
            "Multiple labels per coder/unit require explicit multi-label adjudication",
        )
        mapping[annotation.unit_id] = annotation.code_id
    require(
        set(labels[coder_a]) == set(unit_ids) and set(labels[coder_b]) == set(unit_ids),
        "Both coders must label each declared unit",
        "SCHEMA_MISMATCH",
    )
    return [
        {"unit_id": unit, "coder_a": labels[coder_a][unit], "coder_b": labels[coder_b][unit]}
        for unit in unit_ids
        if labels[coder_a][unit] != labels[coder_b][unit]
    ]
