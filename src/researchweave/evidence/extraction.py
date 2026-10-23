"""Typed extraction of research outcome fields and their evidence trace.

Form validation preserves null semantics and reported units, rather than
silently coercing missingness into zero or pooling distinct effect measures.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from .errors import require
from .models import canonical_json, new_id, now_utc
from .storage import ProjectStore

Missingness = Literal["present", "not_reported", "not_applicable", "not_extracted"]


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    name: str
    datatype: Literal["number", "integer", "string", "boolean", "category"]
    required: bool = False
    permitted_values: tuple[str, ...] = ()
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        require(self.name.isidentifier() and len(self.name) <= 128,
                "Extraction field needs a stable identifier")
        require(self.minimum is None or self.maximum is None or
                self.minimum <= self.maximum, "Invalid extraction numeric bounds")
        require(self.datatype != "category" or bool(self.permitted_values),
                "Category fields require listed permitted values")


@dataclass(frozen=True, slots=True)
class ExtractedValue:
    field: str
    value: str | int | float | bool | None
    missingness: Missingness = "present"
    unit: str | None = None
    original_text: str = ""


def validate_field(field: FieldDefinition, extracted: ExtractedValue) -> dict[str, Any]:
    require(extracted.field == field.name, "Field name does not match schema")
    require(extracted.missingness in {"present", "not_reported", "not_applicable",
                                      "not_extracted"}, "Unknown missingness state")
    if extracted.missingness != "present":
        require(extracted.value is None, "Missing data must have null value")
        require(not field.required, "Required extraction field is missing")
        return {"field": field.name, "value": None,
                "missingness": extracted.missingness, "unit": field.unit,
                "original_text": extracted.original_text}
    require(extracted.value is not None, "Present extraction has null value")
    value = extracted.value
    if field.datatype == "boolean":
        require(type(value) is bool, "Boolean field expects true/false")
    elif field.datatype == "integer":
        require(type(value) is int, "Integer field requires an integer")
    elif field.datatype == "number":
        require(type(value) in {int, float}, "Numeric field requires a number")
        require(isinstance(value, (int, float)) and math.isfinite(value),
                "Numeric extraction must be finite")
    else:
        require(isinstance(value, str), "Text/category field requires string")
        require(isinstance(value, str) and len(value) <= 100_000,
                "Text extraction exceeds limit", "RESOURCE_LIMIT")
        if field.datatype == "category":
            require(value in field.permitted_values, "Category outside allowed values")
    if field.datatype in {"number", "integer"}:
        if field.minimum is not None:
            require(isinstance(value, (int, float)) and value >= field.minimum,
                    "Value below field minimum")
        if field.maximum is not None:
            require(isinstance(value, (int, float)) and value <= field.maximum,
                    "Value above field maximum")
    require(extracted.unit == field.unit or extracted.unit is None,
            "Unit mismatch; conversions must be explicit")
    return {"field": field.name, "value": value, "missingness": "present",
            "unit": field.unit, "original_text": extracted.original_text}


class ExtractionService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def create_entry(self, record_id: str, schema: FieldDefinition,
                     extracted: ExtractedValue, reviewer: str,
                     anchor_id: str | None = None, *,
                     expected_revision: int | None = None) -> dict[str, Any]:
        require(bool(reviewer.strip()) and len(reviewer) <= 255, "Reviewer is required")
        parsed = validate_field(schema, extracted)
        entry_id = new_id()

        def insert(conn: Any) -> None:
            require(conn.execute("SELECT 1 FROM review_records WHERE id=?", (record_id,))
                    .fetchone() is not None, "Review record does not exist", "NOT_FOUND")
            if anchor_id is not None:
                require(conn.execute("SELECT verified FROM anchors WHERE id=?",
                                     (anchor_id,)).fetchone() is not None,
                        "Unknown evidence anchor", "NOT_FOUND")
            conn.execute("INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?)",
                         (entry_id, record_id, schema.name, canonical_json(parsed),
                          schema.unit, anchor_id, reviewer, now_utc()))

        _, revision = self.store.mutate("review.extract", {
            "record_id": record_id, "field": schema.name, "entry_id": entry_id,
            "anchor_id": anchor_id, "reviewer": reviewer,
        }, insert, expected_revision=expected_revision)
        return {"entry_id": entry_id, "field": schema.name, "value": parsed,
                "revision": revision, "verified_anchor": anchor_id is not None}

    def matrix(self, review_id: str) -> list[dict[str, Any]]:
        rows = self.store.conn.execute(
            "SELECT e.record_id,e.field_name,e.value_json,e.unit,e.source_anchor,e.reviewer,"
            "r.study_id,r.reference_id FROM extractions e "
            "JOIN review_records r ON r.id=e.record_id "
            "WHERE r.review_id=? ORDER BY r.study_id,e.record_id,e.field_name,e.recorded_at",
            (review_id,),
        ).fetchall()
        return [{"record_id": r["record_id"], "study_id": r["study_id"],
                 "reference_id": r["reference_id"], "field": r["field_name"],
                 "extracted": json.loads(r["value_json"]), "unit": r["unit"],
                 "source_anchor": r["source_anchor"], "reviewer": r["reviewer"]}
                for r in rows]
