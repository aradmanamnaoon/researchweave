"""Independent reviewer screening with explicit disagreement adjudication.

Screening is a local software demonstration, not a full PRISMA 2020 workflow.
Reviewer aliases are self-reported and are not authenticated identities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, cast

from .contracts import Project, UIError, utc_now

Decision = Literal["include", "exclude", "unsure"]
MAX_REVIEW_EVENTS = 20_000
MAX_REVIEWERS = 12


@dataclass
class ScreeningDecision:
    source_id: str
    reviewer: str
    decision: Decision
    reason: str = ""
    timestamp: str = field(default_factory=utc_now)


@dataclass
class Adjudication:
    source_id: str
    adjudicator: str
    final_decision: Decision
    rationale: str
    timestamp: str = field(default_factory=utc_now)


def _source_ids(project: Project) -> set[str]:
    return {item.id for item in project.sources}


def _alias(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 60:
        raise UIError("INVALID_INPUT", "Reviewer alias must be 1–60 characters.",
                      "Choose a short reviewer alias.")
    name = value.strip()
    if not name or any(ord(character) < 32 for character in name):
        raise UIError("INVALID_INPUT", "Reviewer alias contains invalid characters.",
                      "Use readable letters or numbers.")
    return name


def _decision(value: str) -> Decision:
    if value not in ("include", "exclude", "unsure"):
        raise UIError("INVALID_INPUT", "Unknown screening decision.",
                      "Select include, exclude or unsure.")
    return cast(Decision, value)


def submit_decision(
    project: Project, *, source_id: str, reviewer: str,
    decision: str, reason: str = "",
) -> ScreeningDecision:
    if source_id not in _source_ids(project):
        raise UIError("NOT_FOUND", "Screening source was not found.",
                      "Select an existing source.")
    alias = _alias(reviewer)
    selected = _decision(decision)
    if not isinstance(reason, str) or len(reason) > 1200:
        raise UIError("INVALID_INPUT", "Screening rationale exceeds limits.",
                      "Write a short reason.")
    if selected == "exclude" and not reason.strip():
        raise UIError("INVALID_INPUT", "Exclusion requires a reason.",
                      "Record the study's predefined exclusion criterion.")
    if len(project.screening_decisions) >= MAX_REVIEW_EVENTS:
        raise UIError("RESOURCE_LIMIT", "Screening event capacity reached.",
                      "Archive this review before continuing.")
    if len({item.reviewer for item in project.screening_decisions} | {alias}) > MAX_REVIEWERS:
        raise UIError("RESOURCE_LIMIT", "Too many reviewer aliases.",
                      "Keep a bounded local reviewer roster.")
    if any(item.source_id == source_id and item.reviewer == alias
           for item in project.screening_decisions):
        raise UIError("CONFLICT", "Reviewer has already screened this source.",
                      "Existing decisions are retained; use a separate adjudication.")
    if any(item.source_id == source_id for item in project.adjudications):
        raise UIError("CONFLICT", "Source was already adjudicated.",
                      "Review the existing final decision before making changes.")
    result = ScreeningDecision(source_id, alias, selected, reason.strip())
    project.screening_decisions.append(result)
    return result


def adjudicate(
    project: Project, *, source_id: str, adjudicator: str,
    final_decision: str, rationale: str,
) -> Adjudication:
    alias = _alias(adjudicator)
    selected = _decision(final_decision)
    if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 1200:
        raise UIError("INVALID_INPUT", "Adjudication requires a written rationale.",
                      "Explain how disagreement was resolved.")
    if any(item.source_id == source_id for item in project.adjudications):
        raise UIError("CONFLICT", "Source already has an adjudication.",
                      "Preserve the existing record and inspect its rationale.")
    decisions = [item for item in project.screening_decisions
                 if item.source_id == source_id]
    if len(decisions) < 2 or len({item.decision for item in decisions}) < 2:
        raise UIError("INVALID_INPUT", "No independent reviewer conflict to adjudicate.",
                      "Obtain two distinct reviewer decisions first.")
    if alias in {item.reviewer for item in decisions}:
        raise UIError("PERMISSION_DENIED", "Adjudicator participated in this screening.",
                      "Use a separate adjudicator alias to record an independent decision.")
    result = Adjudication(source_id, alias, selected, rationale.strip())
    project.adjudications.append(result)
    return result


def _computed_status(
    decisions: list[ScreeningDecision], adjudication: Adjudication | None,
) -> tuple[str, str]:
    if adjudication:
        return "adjudicated", adjudication.final_decision
    if not decisions:
        return "pending", ""
    if len(decisions) < 2:
        return "awaiting-second", ""
    if any(item.decision == "unsure" for item in decisions):
        return "conflict", ""
    choices = {item.decision for item in decisions}
    if len(choices) > 1:
        return "conflict", ""
    return "agreed", next(iter(choices))


def review_queue(project: Project, *, reveal_all: bool = False,
                 reviewer: str = "") -> dict[str, Any]:
    """Hide peer decisions while an identified reviewer has not voted.

    Reviewer aliases are provided by the local UI; this is a convenience
    blindness barrier and must not be represented as secure identity control.
    """
    if reviewer:
        reviewer = _alias(reviewer)
    records = []
    for source in project.sources:
        prior = [item for item in project.screening_decisions
                 if item.source_id == source.id]
        resolved = next((item for item in project.adjudications
                         if item.source_id == source.id), None)
        status, final = _computed_status(prior, resolved)
        peer_hidden = bool(
            reviewer and not reveal_all and
            not any(item.reviewer == reviewer for item in prior)
        )
        visible = [] if peer_hidden else [asdict(item) for item in prior]
        records.append({
            "source_id": source.id,
            "title": source.title,
            "status": "needs-your-review" if peer_hidden and prior else status,
            "computed_status": status if not peer_hidden else "blinded",
            "final_decision": final if not peer_hidden else "",
            "review_count": len(prior) if not peer_hidden else None,
            "decisions": visible,
            "adjudication": asdict(resolved) if resolved and not peer_hidden else None,
            "source_metadata_verified": source.verified,
        })
    return {
        "total_sources": len(records),
        "records": records,
        "blinded": bool(reviewer and not reveal_all),
        "authentication_guaranteed": False,
        "limitations": (
            "Aliases do not authenticate users. "
            "Use a trusted reviewer service for real blinded studies."
        ),
    }


def screening_flow(project: Project) -> dict[str, Any]:
    """Compute only grounded screening counts; never invent upstream PRISMA phases."""
    queue = review_queue(project, reveal_all=True)
    counts = {name: 0 for name in (
        "pending", "awaiting-second", "conflict", "agreed", "adjudicated",
    )}
    included = excluded = unsure = 0
    excluded_reasons: dict[str, int] = {}
    for source in queue["records"]:
        status = source["computed_status"]
        counts[status] += 1
        final = source["final_decision"]
        if final == "include":
            included += 1
        elif final == "exclude":
            excluded += 1
            if source["adjudication"]:
                why = source["adjudication"]["rationale"]
            else:
                why = next((item["reason"] for item in source["decisions"]
                            if item["decision"] == "exclude"), "")
            excluded_reasons[why or "Unspecified rationale"] = (
                excluded_reasons.get(why or "Unspecified rationale", 0) + 1
            )
        elif final == "unsure":
            unsure += 1
    screened = counts["agreed"] + counts["adjudicated"]
    if included + excluded + unsure != screened:
        raise UIError("INTEGRITY_FAILURE", "Screening outcome count is inconsistent.",
                      "Inspect reviewer decisions and adjudications.")
    return {
        "phase": "source-screening-only",
        "local_source_records": len(project.sources),
        "decision_events": len(project.screening_decisions),
        "adjudication_events": len(project.adjudications),
        "status_counts": counts,
        "screened_with_final_outcome": screened,
        "included": included,
        "excluded": excluded,
        "unsure_after_adjudication": unsure,
        "excluded_reasons": excluded_reasons,
        "records_identified_via_databases": None,
        "records_removed_before_screening": None,
        "reports_sought_for_retrieval": None,
        "reports_not_retrieved": None,
        "studies_included_in_review": None,
        "note": (
            "These are derived local screening events. This partial accounting "
            "does not constitute a complete PRISMA 2020 flow diagram."
        ),
    }
