"""Privacy-aware traceable qualitative/quantitative displays."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .errors import AnalysisError, require
from .models import Dataset, digest
from .qualitative import CodingProject


def _source_index(project: CodingProject) -> dict[str, str]:
    sources: dict[str, str] = {}
    for key, transcript in project.transcripts.items():
        require(key == transcript.source_id, "Transcript identifier conflict", "INTEGRITY_FAILURE")
        sources[key] = transcript.case_id
    return sources


def case_code_matrix(
    project: CodingProject, *, coders: list[str] | None = None, accepted_only: bool = False
) -> dict[str, Any]:
    """Count event occurrences by case/code, retaining annotation indices for audit."""
    require(bool(project.transcripts), "No transcripts in coding project")
    if accepted_only:
        # Base CodingProject lacks adjudication state: never imply code acceptance.
        raise AnalysisError("UNSUPPORTED", "Acceptance state requires adjudication ledger")
    if coders is not None:
        require(bool(coders) and len(set(coders)) == len(coders), "Duplicate or empty coder set")
    index = _source_index(project)
    counts: dict[str, dict[str, int]] = {}
    traces: dict[str, dict[str, list[int]]] = {}
    for source in project.transcripts.values():
        counts.setdefault(source.case_id, {key: 0 for key in project.codes})
        traces.setdefault(source.case_id, {key: [] for key in project.codes})
    for ordinal, annotation in enumerate(project.annotations):
        require(
            project.verify(annotation), "Annotation has stale source anchor", "INTEGRITY_FAILURE"
        )
        require(annotation.code_id in project.codes, "Annotation references unknown code")
        if coders is not None and annotation.coder not in coders:
            continue
        case = index[annotation.source_id]
        counts[case][annotation.code_id] += 1
        traces[case][annotation.code_id].append(ordinal)
    return {
        "case_counts": counts,
        "annotation_indices": traces,
        "n_cases": len(counts),
        "n_annotations": sum(sum(row.values()) for row in counts.values()),
        "coding_source_hashes": {
            key: transcript.checksum for key, transcript in project.transcripts.items()
        },
        "assumption": "Occurrences are coding events, not independent statistical units",
    }


def joint_display(
    dataset: Dataset,
    project: CodingProject,
    *,
    case_column: str,
    measure_column: str,
    code_id: str,
    min_reporting_cases: int = 3,
    allow_quotes: bool = False,
    include_private: bool = False,
) -> dict[str, Any]:
    """Traceable aggregate by presence of code; redact quotations by default.

    Reject small cells and mapping multiplicity; no inferential significance claims.
    """
    require(
        case_column in dataset.columns and measure_column in dataset.columns,
        "Unknown quantitative case identifier or outcome",
    )
    require(code_id in project.codes, "Code does not exist")
    require(3 <= min_reporting_cases <= 50, "Minimum disclosure threshold must be 3..50")
    require(case_column != measure_column, "Case identifier cannot be the outcome")
    restricted = {v.name for v in dataset.variables if v.private}
    require(
        include_private or (case_column not in restricted and measure_column not in restricted),
        "Dataset contains private fields; host consent required",
        "PERMISSION_DENIED",
    )
    require(
        not allow_quotes or include_private,
        "Direct participant excerpts require explicit disclosure approval",
        "PERMISSION_DENIED",
    )
    grouped = case_code_matrix(project)
    qualitative_cases = grouped["case_counts"]
    observed: dict[str, tuple[str, Any]] = {}
    for row in dataset.records:
        if row[case_column] is None:
            continue
        identifier = str(row[case_column])
        require(identifier not in observed, "Duplicate quantitative case ID", "SCHEMA_MISMATCH")
        observed[identifier] = (identifier, row[measure_column])
    require(bool(observed), "No quantitative case IDs")
    mismatch = sorted(set(qualitative_cases) - set(observed))
    require(not mismatch, "Qualitative case IDs lack quantitative mapping", "SCHEMA_MISMATCH")
    from .models import finite_number

    arms: dict[str, list[tuple[str, float]]] = {"coded": [], "not_coded": []}
    for identifier, values in qualitative_cases.items():
        raw = observed[identifier][1]
        if raw is None:
            continue
        value = finite_number(raw, name=measure_column)
        arm = "coded" if values[code_id] > 0 else "not_coded"
        arms[arm].append((identifier, value))
    require(
        all(len(arm) >= min_reporting_cases for arm in arms.values()),
        "One or more reporting cells contain too few cases",
        "PRIVACY_THRESHOLD",
    )
    import numpy as np

    output = {
        label: {
            "n_cases": len(arm),
            "mean": float(np.mean([value for _, value in arm])),
            "min": float(min(value for _, value in arm)),
            "max": float(max(value for _, value in arm)),
        }
        for label, arm in arms.items()
    }
    excerpts = []
    if allow_quotes:
        for index, annotation in enumerate(project.annotations):
            if annotation.code_id != code_id:
                continue
            require(project.verify(annotation), "Quote source changed", "INTEGRITY_FAILURE")
            excerpts.append(
                {
                    "source_id": annotation.source_id,
                    "source_hash": annotation.source_hash,
                    "span": [annotation.start, annotation.end],
                    "quote": annotation.quote,
                    "annotation_index": index,
                }
            )
    return {
        "code_id": code_id,
        "case_column": case_column,
        "measure_column": measure_column,
        "groups": output,
        "n_qualitative_cases": len(qualitative_cases),
        "n_quantitative_cases": len(observed),
        "n_excluded_missing_measure": sum(row[measure_column] is None for row in dataset.records),
        "codebook_ids": sorted(project.codes),
        "excerpts": excerpts,
        "source_revision": dataset.revision,
        "coding_hash": digest(project.to_json()),
        "privacy_minimum_cases": min_reporting_cases,
        "limitation": ("Descriptive comparison; coding and sampling do not support causal claims"),
    }


def code_cooccurrence(
    project: CodingProject, *, coder: str | None = None, min_shared_codepoints: int = 1
) -> dict[str, Any]:
    """Count overlapping coded intervals within the same unchanged transcript."""
    require(min_shared_codepoints >= 1, "Positive overlap required")
    annotations = [
        (i, annotation)
        for i, annotation in enumerate(project.annotations)
        if coder is None or annotation.coder == coder
    ]
    counts: Counter[tuple[str, str]] = Counter()
    examples: dict[str, list[tuple[int, int]]] = {}
    for index, first in annotations:
        require(project.verify(first), "Stale first annotation", "INTEGRITY_FAILURE")
        for second_index, second in annotations:
            if (
                second_index <= index
                or first.source_id != second.source_id
                or (first.code_id == second.code_id)
            ):
                continue
            require(project.verify(second), "Stale second annotation", "INTEGRITY_FAILURE")
            span = max(0, min(first.end, second.end) - max(first.start, second.start))
            if span >= min_shared_codepoints:
                pair = tuple(sorted((first.code_id, second.code_id)))
                counts[pair] += 1
                examples.setdefault("|".join(pair), []).append((index, second_index))
    return {
        "pairs": [
            {
                "code_ids": list(pair),
                "n_overlapping_pairs": count,
                "annotation_pairs": examples["|".join(pair)],
            }
            for pair, count in sorted(counts.items())
        ],
        "n_annotations": len(annotations),
        "overlap_unit": "Unicode code points in same transcript",
        "warning": "Event co-occurrence counts do not estimate respondent-level prevalence",
    }
