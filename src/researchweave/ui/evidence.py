"""Source-anchored claim drafting with immutable source checksum verification.

These local demonstration records expose citation traceability but cannot
certify factual truth or replace publisher-specific metadata verification.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from .contracts import Project, Source, UIError, new_id, utc_now

MAX_EVIDENCE_QUOTE = 8_000
MAX_CLAIM = 4_000
MAX_EVIDENCE_PER_PROJECT = 5_000
MAX_CLAIMS_PER_PROJECT = 5_000


@dataclass
class EvidenceAnchor:
    """Unverified yet inspectable excerpt tied to one source version."""

    id: str
    source_id: str
    source_sha256: str
    start: int
    end: int
    quote: str
    note: str = ""
    created_at: str = field(default_factory=utc_now)
    created_by: str = "local-user"
    evidence_type: str = "direct_quote"


@dataclass
class ClaimRecord:
    """Claim draft with explicit IDs rather than invented citation keys."""

    id: str
    text: str
    supporting_evidence: list[str] = field(default_factory=list)
    challenging_evidence: list[str] = field(default_factory=list)
    status: str = "draft-unverified"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_source(project: Project, source_id: str) -> Source:
    source = next((item for item in project.sources if item.id == source_id), None)
    if source is None:
        raise UIError("NOT_FOUND", "Evidence source was not found.",
                      "Select an existing source from the library.")
    return source


def get_anchor(project: Project, anchor_id: str) -> EvidenceAnchor:
    anchor = next((item for item in project.evidence if item.id == anchor_id), None)
    if anchor is None:
        raise UIError("NOT_FOUND", "Evidence anchor was not found.",
                      "Choose a saved source quotation.")
    return anchor


def add_anchor(
    project: Project,
    *,
    source_id: str,
    start: int,
    end: int,
    note: str = "",
) -> EvidenceAnchor:
    if len(project.evidence) >= MAX_EVIDENCE_PER_PROJECT:
        raise UIError("RESOURCE_LIMIT", "Evidence anchor limit reached.",
                      "Split the analysis into separate projects.")
    source = get_source(project, source_id)
    if (isinstance(start, bool) or isinstance(end, bool)
            or not isinstance(start, int) or not isinstance(end, int)
            or not 0 <= start < end <= len(source.text)
            or end - start > MAX_EVIDENCE_QUOTE):
        raise UIError("INVALID_INPUT", "Evidence text span is outside the source.",
                      "Select a passage of no more than 8,000 characters.")
    if not isinstance(note, str) or len(note) > 4_000:
        raise UIError("INVALID_INPUT", "Evidence note is too long.",
                      "Keep the note under 4,000 characters.")
    digest = _digest(source.text)
    if source.content_hash and source.content_hash != digest:
        raise UIError("INTEGRITY_FAILURE", "Source text no longer matches its recorded hash.",
                      "Restore the original source or inspect the edited source.")
    anchor = EvidenceAnchor(
        id=new_id(),
        source_id=source_id,
        source_sha256=digest,
        start=start,
        end=end,
        quote=source.text[start:end],
        note=note,
    )
    project.evidence.append(anchor)
    return anchor


def inspect_anchor(project: Project, anchor: EvidenceAnchor) -> dict[str, Any]:
    source = get_source(project, anchor.source_id)
    current_hash = _digest(source.text)
    checks = {
        "source_hash_matches": current_hash == anchor.source_sha256,
        "source_metadata_hash_matches": (
            not source.content_hash or current_hash == source.content_hash
        ),
        "offsets_valid": (
            0 <= anchor.start < anchor.end <= len(source.text)
        ),
        "quote_matches": (
            0 <= anchor.start < anchor.end <= len(source.text)
            and source.text[anchor.start:anchor.end] == anchor.quote
        ),
    }
    integrity_ok = all(checks.values())
    return {
        "anchor_id": anchor.id,
        "source_id": source.id,
        "source_title": source.title,
        "source_label": source.source_label,
        "quote": anchor.quote,
        "span_start": anchor.start,
        "span_end": anchor.end,
        "source_sha256": anchor.source_sha256,
        "checks": checks,
        "integrity": "matched" if integrity_ok else "failed",
        "source_metadata_verified": source.verified,
        "scientific_claim_verified": False,
        "note": (
            "A matching source span verifies provenance integrity only, "
            "not whether this source actually supports a scientific claim."
        ),
    }


def create_claim(
    project: Project,
    text: str,
    *,
    supporting_evidence: list[str],
    challenging_evidence: list[str] | None = None,
) -> ClaimRecord:
    if len(project.claims) >= MAX_CLAIMS_PER_PROJECT:
        raise UIError("RESOURCE_LIMIT", "Claim list exceeds project limits.",
                      "Use a smaller project or export drafts.")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_CLAIM:
        raise UIError("INVALID_INPUT", "Claim must contain 1–4,000 characters.",
                      "Write a focused testable statement.")
    contradictory = challenging_evidence or []
    if (not isinstance(supporting_evidence, list)
            or not isinstance(contradictory, list)
            or any(not isinstance(item, str) for item in supporting_evidence + contradictory)):
        raise UIError("INVALID_INPUT", "Evidence identifiers must be a list of strings.",
                      "Select saved evidence anchors.")
    if len(supporting_evidence) + len(contradictory) > 50:
        raise UIError("RESOURCE_LIMIT", "Too many evidence anchors for one claim.",
                      "Group supporting and challenging evidence into smaller claims.")
    references = supporting_evidence + contradictory
    if len(references) != len(set(references)):
        raise UIError("INVALID_INPUT", "Duplicate or conflicting evidence link.",
                      "Each evidence excerpt may appear once in a claim.")
    for identifier in references:
        get_anchor(project, identifier)
    claim = ClaimRecord(
        id=new_id(), text=text.strip(),
        supporting_evidence=list(supporting_evidence),
        challenging_evidence=list(contradictory),
    )
    project.claims.append(claim)
    return claim


def inspect_claim(project: Project, claim: ClaimRecord) -> dict[str, Any]:
    positive = [
        inspect_anchor(project, get_anchor(project, item))
        for item in claim.supporting_evidence
    ]
    negative = [
        inspect_anchor(project, get_anchor(project, item))
        for item in claim.challenging_evidence
    ]
    anchor_integrity = all(
        record["integrity"] == "matched" for record in positive + negative
    )
    warning_list = []
    if not positive:
        warning_list.append("This claim has no source-linked supporting evidence.")
    if negative:
        warning_list.append("This claim has recorded challenging evidence.")
    if not anchor_integrity:
        warning_list.append("At least one linked source span fails integrity checks.")
    if positive and all(not item["source_metadata_verified"] for item in positive):
        warning_list.append("Supporting sources have unverified bibliographic metadata.")
    return {
        "claim": asdict(claim),
        "supporting": positive,
        "challenging": negative,
        "integrity": "matched" if anchor_integrity else "failed",
        "human_assessment_required": True,
        "claims_scientific_truth": False,
        "warnings": warning_list,
    }


def draft_manuscript_reference(project: Project, claim_id: str) -> dict[str, Any]:
    """Produce a clearly unverified citation placeholder for manual writing."""
    claim = next((item for item in project.claims if item.id == claim_id), None)
    if claim is None:
        raise UIError("NOT_FOUND", "Claim was not found.",
                      "Choose a saved draft claim.")
    result = inspect_claim(project, claim)
    if result["integrity"] != "matched":
        raise UIError("INTEGRITY_FAILURE", "Claim source links no longer match.",
                      "Review each evidence quote before citing it.")
    if not claim.supporting_evidence:
        raise UIError("INVALID_INPUT", "Claim has no linked support.",
                      "Add a verifiable primary-source excerpt.")
    sources = []
    for anchor_id in claim.supporting_evidence:
        source = get_source(project, get_anchor(project, anchor_id).source_id)
        if source.id not in sources:
            sources.append(source.id)
    return {
        "claim_id": claim.id,
        "draft_text": claim.text,
        "source_ids": sources,
        "citation_placeholder": "[Verify full bibliographic citation before submission]",
        "approved_reference": False,
        "ready_for_publication": False,
        "note": "No bibliography metadata or scientific conclusion was invented.",
    }
