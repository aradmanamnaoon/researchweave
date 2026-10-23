"""Conservative PRISMA 2020 audit report from persisted review events.

This is an accounting/reporting aid, not a claim that a review follows every
PRISMA reporting item. It refuses publication-ready status while recorded
identification, screening, retrieval, exclusion, or study/report counts remain
unreconciled.
"""

from __future__ import annotations

import html
from collections import Counter
from typing import Any

from .errors import require
from .reviews import ReviewService
from .storage import ProjectStore

COUNT_KEYS = (
    "records_identified", "duplicates_removed", "removed_automation", "removed_other",
    "records_screened_started", "records_excluded_title", "reports_sought",
    "reports_not_retrieved", "reports_assessed", "reports_excluded_full_text",
    "reports_included", "studies_included", "unresolved_title", "unresolved_full_text",
    "missing_retrieval_status",
)


def _validate_accounting(accounting: dict[str, Any]) -> None:
    for key in COUNT_KEYS:
        require(type(accounting.get(key)) is int and accounting[key] >= 0,
                f"Invalid PRISMA accounting value: {key}", "INTEGRITY_FAILURE")
    identified = accounting["records_identified"]
    removals = (accounting["duplicates_removed"] + accounting["removed_automation"]
                + accounting["removed_other"])
    require(removals <= identified, "PRISMA removals exceed identified records",
            "INTEGRITY_FAILURE")
    require(accounting["reports_assessed"] == (
        accounting["reports_included"] + accounting["reports_excluded_full_text"]
    ), "PRISMA assessed reports do not reconcile", "INTEGRITY_FAILURE")
    require(accounting["studies_included"] <= accounting["reports_included"],
            "Included studies exceed included reports", "INTEGRITY_FAILURE")


class Prisma2020Service:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.review = ReviewService(store)

    def report(self, review_id: str) -> dict[str, Any]:
        require(bool(review_id.strip()) and len(review_id) <= 255, "Review ID is required")
        accounting = self.review.prisma(review_id)
        _validate_accounting(accounting)
        searches = [
            {"run_id": row["id"], "provider": row["provider"],
             "query": row["original_query"], "expected_records": row["expected_records"],
             "finalized": bool(row["finalized"]), "searched_at": row["searched_at"],
             "response_sha256": row["response_sha256"]}
            for row in self.store.conn.execute(
                "SELECT * FROM review_search_runs WHERE review_id=? ORDER BY searched_at,id",
                (review_id,),
            )
        ]
        reasons: Counter[str] = Counter()
        excluded_records: list[dict[str, Any]] = []
        records = self.store.conn.execute(
            "SELECT id FROM review_records WHERE review_id=? AND stage='full_text' ORDER BY id",
            (review_id,),
        ).fetchall()
        for row in records:
            state = self.review.status(review_id, row["id"], "full_text")
            if state.get("decision") != "exclude":
                continue
            adjudication = self.store.conn.execute(
                "SELECT reason FROM adjudications WHERE review_id=? AND record_id=? "
                "AND stage='full_text'",
                (review_id, row["id"]),
            ).fetchone()
            if adjudication is not None:
                reason = str(adjudication["reason"]).strip()
            else:
                vote_reasons = [
                    str(vote["reason"]).strip()
                    for vote in self.store.conn.execute(
                        "SELECT reason FROM votes WHERE review_id=? AND record_id=? "
                        "AND stage='full_text' AND decision='exclude' ORDER BY reviewer",
                        (review_id, row["id"]),
                    )
                    if str(vote["reason"]).strip()
                ]
                reason = vote_reasons[0] if vote_reasons and len(set(vote_reasons)) == 1 else ""
            label = reason or "UNSPECIFIED_EXCLUSION_REASON"
            reasons[label] += 1
            excluded_records.append({"record_id": row["id"], "reason": label})

        checklist = [
            {"item": "identification_sources", "complete": bool(searches)
             and all(search["finalized"] for search in searches)},
            {"item": "duplicate_and_other_removals", "complete": (
                accounting["duplicates_removed"] + accounting["removed_automation"]
                + accounting["removed_other"] <= accounting["records_identified"])},
            {"item": "title_abstract_screening_resolved",
             "complete": accounting["unresolved_title"] == 0},
            {"item": "retrieval_resolved",
             "complete": accounting["missing_retrieval_status"] == 0},
            {"item": "full_text_assessment_resolved",
             "complete": accounting["unresolved_full_text"] == 0},
            {"item": "full_text_exclusion_reasons",
             "complete": accounting["reports_excluded_full_text"] == len(excluded_records)
             and all(item["reason"] != "UNSPECIFIED_EXCLUSION_REASON"
                     for item in excluded_records)},
            {"item": "reports_and_studies_distinguished",
             "complete": accounting["studies_included"] <= accounting["reports_included"]},
        ]
        ready = bool(accounting["complete_prisma_2020"] and
                     all(item["complete"] for item in checklist))
        return {
            "review_id": review_id,
            "accounting": accounting,
            "searches": searches,
            "source_database_count": len({search["provider"] for search in searches}),
            "full_text_exclusions": excluded_records,
            "full_text_exclusion_reason_counts": dict(sorted(reasons.items())),
            "checklist": checklist,
            "publication_ready": ready,
            "prisma_2020_compliance_certified": False,
            "warning": (
                "Recorded flow is reconciled; independent PRISMA checklist review "
                "is still required."
                if ready
                else "Recorded PRISMA flow is incomplete or lacks required "
                "exclusion provenance."
            ),
        }

    def svg(self, review_id: str) -> dict[str, Any]:
        report = self.report(review_id)
        a = report["accounting"]
        labels = [
            ("Records identified", a["records_identified"]),
            ("Duplicates removed", a["duplicates_removed"]),
            ("Records screened", a["records_screened_started"]),
            ("Title/abstract exclusions", a["records_excluded_title"]),
            ("Reports sought", a["reports_sought"]),
            ("Reports not retrieved", a["reports_not_retrieved"]),
            ("Reports assessed", a["reports_assessed"]),
            ("Full-text exclusions", a["reports_excluded_full_text"]),
            ("Reports included", a["reports_included"]),
            ("Distinct studies included", a["studies_included"]),
        ]
        width, box_height, gap = 520, 54, 18
        height = 32 + len(labels) * (box_height + gap) + 54
        chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                  f'viewBox="0 0 {width} {height}">',
                  '<title>PRISMA 2020 recorded flow</title>',
                  '<desc>Diagnostic flow generated from persisted ResearchWeave '
                  'review events.</desc>']
        y = 24
        for index, (label, count) in enumerate(labels):
            chunks.append(f'<rect x="60" y="{y}" width="400" height="{box_height}" '
                          'rx="6" fill="white" stroke="black"/>')
            chunks.append(f'<text x="260" y="{y + 32}" text-anchor="middle" '
                          f'font-family="sans-serif" font-size="14">'
                          f'{html.escape(label)}: {count}</text>')
            if index < len(labels) - 1:
                chunks.append(f'<line x1="260" y1="{y + box_height}" x2="260" '
                              f'y2="{y + box_height + gap}" stroke="black"/>')
            y += box_height + gap
        status = "RECONCILED — independent checklist review still required" if report[
            "publication_ready"] else "INCOMPLETE — reconcile recorded review events"
        chunks.append(f'<text x="260" y="{height - 20}" text-anchor="middle" '
                      f'font-family="sans-serif" font-size="12">{html.escape(status)}</text>')
        chunks.append("</svg>")
        return {"format": "svg", "text": "".join(chunks),
                "publication_ready": report["publication_ready"],
                "prisma_2020_compliance_certified": False,
                "accounting": a}
