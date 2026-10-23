"""Human-checkable PRISMA 2020 reporting from reconciled persisted review events.

This produces a conservative textual diagram and accounting table. It does not
convert incomplete or ambiguous screening records into authoritative counts.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Any

from .errors import require

COUNTS = (
    ("records_identified", "Records identified"),
    ("duplicates_removed", "Duplicate records removed"),
    ("removed_automation", "Records removed by automation"),
    ("removed_other", "Records removed for other reasons"),
    ("records_screened_started", "Records with screening activity"),
    ("records_excluded_title", "Records excluded at title/abstract screening"),
    ("reports_sought", "Reports sought for retrieval"),
    ("reports_not_retrieved", "Reports not retrieved"),
    ("reports_assessed", "Reports with completed eligibility assessment"),
    ("reports_excluded_full_text", "Reports excluded at full text"),
    ("reports_included", "Reports included in review"),
    ("studies_included", "Distinct studies included in review"),
    ("unresolved_title", "Unresolved screening"),
    ("unresolved_full_text", "Unresolved full-text status"),
    ("missing_retrieval_status", "Missing retrieval decisions"),
)


def prisma_export(accounting: Mapping[str, Any], *,
                  format_name: str = "markdown") -> dict[str, Any]:
    """Export only explicit counts and an integrity caveat from review.prisma.

    CSV is designed for automated review of exported counts. Mermaid is a
    diagnostic diagram and avoids suggesting a PRISMA-validated publication.
    """
    require(format_name in {"markdown", "csv", "mermaid"}, "Unsupported PRISMA output format")
    review_id = accounting.get("review_id")
    require(isinstance(review_id, str) and bool(review_id), "Missing persisted review identity")
    for key, _ in COUNTS:
        value = accounting.get(key)
        require(type(value) is int and value >= 0, f"Invalid persisted PRISMA count: {key}",
                "INTEGRITY_FAILURE")
    complete = accounting.get("complete_prisma_2020") is True
    lines: list[str]
    if format_name == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["review_id", "metric", "count", "reconciled"])
        for key, _ in COUNTS:
            writer.writerow([review_id, key, accounting[key], str(complete).lower()])
        result = stream.getvalue()
    elif format_name == "mermaid":
        # Static node descriptions prevent accidental Markdown/Mermaid injection
        # through imported research names and arbitrary user metadata.
        lines = ["flowchart TD",
                 f"  A[\"Records identified: {accounting['records_identified']}\"]",
                 f"  B[\"Duplicates removed: {accounting['duplicates_removed']}\"]",
                 f"  C[\"Records screened: {accounting['records_screened_started']}\"]",
                 f"  D[\"Title or abstract exclusions: {accounting['records_excluded_title']}\"]",
                 f"  E[\"Reports sought: {accounting['reports_sought']}\"]",
                 f"  F[\"Not retrieved: {accounting['reports_not_retrieved']}\"]",
                 f"  G[\"Reports assessed: {accounting['reports_assessed']}\"]",
                 f"  H[\"Full text exclusions: {accounting['reports_excluded_full_text']}\"]",
                 f"  I[\"Reports included: {accounting['reports_included']}\"]",
                 f"  J[\"Distinct studies included: {accounting['studies_included']}\"]",
                 "  A --> B", "  A --> C", "  C --> D", "  C --> E",
                 "  E --> F", "  E --> G", "  G --> H", "  G --> I", "  I --> J"]
        if not complete:
            lines.append("  K[\"INCOMPLETE: counts require reconciliation\"]")
            lines.append("  J --> K")
        result = "\n".join(lines) + "\n"
    else:
        lines = ["# PRISMA 2020 event accounting", "", f"Review ID: `{review_id}`", "",
                 "Status: reconciled" if complete else "Status: INCOMPLETE — human review required",
                 "",
                 "| Persisted measurement | Count |", "| --- | ---: |"]
        lines += [f"| {description} | {accounting[key]} |" for key, description in COUNTS]
        lines += ["", "These values are derived from recorded ResearchWeave screening events.",
                  "This export is a diagnostic PRISMA summary and does not certify methodology."]
        if not complete:
            lines.append("Unresolved decisions, missing retrievals or source reconciliation "
                         "must be fixed.")
        result = "\n".join(lines) + "\n"
    return {"review_id": review_id, "format": format_name, "text": result,
            "complete_prisma_2020": complete,
            "warning": "" if complete else "Persisted PRISMA accounting is incomplete."}
