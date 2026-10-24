"""Durable research-workflow records used by the desktop facade.

The functions in this module are deliberately independent from Qt. They validate
and transform user-authored workflow state without inventing research findings,
citations, provider availability, or scientific conclusions.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from .contracts import Project, UIError, new_id, utc_now

FIELD_TYPES = frozenset(
    ("text", "integer", "float", "categorical", "boolean", "date", "source-passage")
)
VARIABLE_TYPES = frozenset(("numeric", "categorical", "boolean", "date", "text"))
VARIABLE_ROLES = frozenset(
    ("outcome", "predictor", "group", "confounder", "identifier", "weight", "other")
)
PROVIDER_MODES = frozenset(("manual", "local", "cloud-api"))
INTEGRATION_IDS = frozenset(("crossref", "openalex", "zotero", "osf", "sync-folder"))
MAX_FIELDS = 100
MAX_EXTRACTIONS = 10_000
MAX_RESULTS = 2_000
MAX_CODES = 1_000
MAX_REFERENCES = 10_000
MAX_AGENT_EVENTS = 5_000


def _clean_text(value: Any, name: str, limit: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise UIError(
            "INVALID_INPUT",
            f"{name} must be text under {limit} characters.",
            "Correct the field and try again.",
        )
    result = value.strip()
    if required and not result:
        raise UIError("INVALID_INPUT", f"{name} is required.", "Enter a value before continuing.")
    return result


def _string_list(value: Any, name: str, *, limit: int = 100, item_limit: int = 300) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise UIError(
            "INVALID_INPUT",
            f"{name} must be a bounded list.",
            "Reduce the number of entries and try again.",
        )
    items: list[str] = []
    for item in value:
        items.append(_clean_text(item, name, item_limit))
    return items


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UIError(
            "INVALID_INPUT",
            f"{name} must be an object.",
            "Review the structured fields and try again.",
        )
    return value


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _clone_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(value, ensure_ascii=False)))


def _clone_list(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(json.dumps(value, ensure_ascii=False)))


def _iso_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return False
    return True


def update_question_structure(project: Project, payload: Mapping[str, Any]) -> dict[str, str]:
    """Validate a beginner-friendly structured question without judging its validity."""
    allowed_types = {
        "descriptive",
        "association",
        "causal",
        "prediction",
        "qualitative",
        "systematic-review",
        "mixed-methods",
    }
    result = {
        "topic": _clean_text(payload.get("topic"), "Research topic", 500),
        "population_context": _clean_text(
            payload.get("population_context", ""), "Population or context", 800, required=False
        ),
        "exposure_phenomenon": _clean_text(
            payload.get("exposure_phenomenon", ""),
            "Exposure/intervention/phenomenon",
            800,
            required=False,
        ),
        "outcome_target": _clean_text(
            payload.get("outcome_target", ""), "Outcome or question target", 800, required=False
        ),
        "question_type": _clean_text(payload.get("question_type"), "Question type", 40),
        "editable_question": _clean_text(
            payload.get("editable_question"), "Editable research question", 1_500
        ),
    }
    if result["question_type"] not in allowed_types:
        raise UIError(
            "INVALID_INPUT",
            "Unsupported research question type.",
            "Choose a descriptive, association, causal, prediction, qualitative, "
            "systematic-review or mixed-methods question.",
        )
    project.question_structure = result
    project.question = result["editable_question"]
    return dict(result)


def protocol_history_entry(
    project: Project, *, action: str, previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Record a bounded protocol amendment without silently replacing its audit trail."""
    before = json.loads(json.dumps(previous, ensure_ascii=False))
    after = json.loads(json.dumps(current, ensure_ascii=False))
    entry = {
        "id": new_id(),
        "action": _clean_text(action, "Protocol history action", 80),
        "timestamp": utc_now(),
        "before_sha256": _canonical_hash(before),
        "after_sha256": _canonical_hash(after),
        "before": before,
        "after": after,
    }
    project.protocol_history.append(entry)
    project.protocol_history = project.protocol_history[-500:]
    return entry


@dataclass(frozen=True)
class ExtractionField:
    id: str
    name: str
    label: str
    field_type: str
    required: bool
    categories: tuple[str, ...] = ()
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["categories"] = list(self.categories)
        return value


def _extraction_field(raw: Mapping[str, Any], *, used_names: set[str]) -> ExtractionField:
    name = _clean_text(raw.get("name"), "Extraction field name", 80)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", name):
        raise UIError(
            "INVALID_INPUT",
            "Extraction field names need a simple identifier.",
            "Use letters, numbers and underscores, beginning with a letter.",
        )
    if name in used_names:
        raise UIError(
            "CONFLICT", "Extraction field names must be unique.", "Rename the duplicate field."
        )
    used_names.add(name)
    field_type = _clean_text(raw.get("field_type"), "Extraction field type", 40)
    if field_type not in FIELD_TYPES:
        raise UIError(
            "INVALID_INPUT",
            "Unsupported extraction field type.",
            "Choose text, integer, float, categorical, boolean, date or source-passage.",
        )
    categories: tuple[str, ...] = ()
    if field_type == "categorical":
        category_values = _string_list(
            raw.get("categories", []), "Categories", limit=100, item_limit=120
        )
        if not category_values or len(set(category_values)) != len(category_values):
            raise UIError(
                "INVALID_INPUT",
                "Categorical fields need unique categories.",
                "Provide one or more distinct category labels.",
            )
        categories = tuple(category_values)
    return ExtractionField(
        id=_clean_text(raw.get("id", new_id()), "Extraction field id", 60),
        name=name,
        label=_clean_text(
            raw.get("label", name.replace("_", " ").title()), "Extraction field label", 120
        ),
        field_type=field_type,
        required=bool(raw.get("required", False)),
        categories=categories,
        description=_clean_text(
            raw.get("description", ""), "Field description", 500, required=False
        ),
    )


def set_extraction_schema(
    project: Project, *, title: str, fields: list[Mapping[str, Any]]
) -> dict[str, Any]:
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
        raise UIError(
            "INVALID_INPUT",
            "Extraction schema needs 1–100 fields.",
            "Add at least one field and keep the form focused.",
        )
    used: set[str] = set()
    parsed = [_extraction_field(item, used_names=used) for item in fields]
    previous_version = int(project.extraction_schema.get("version", 0) or 0)
    schema = {
        "id": project.extraction_schema.get("id") or new_id(),
        "title": _clean_text(title, "Extraction form title", 160),
        "version": previous_version + 1,
        "fields": [item.as_dict() for item in parsed],
        "updated_at": utc_now(),
    }
    project.extraction_schema = schema
    return _clone_dict(schema)


def _validate_extraction_value(field: Mapping[str, Any], value: Any) -> Any:
    field_type = field["field_type"]
    if value in (None, ""):
        if field.get("required"):
            raise UIError(
                "INVALID_INPUT",
                f"{field['label']} is required.",
                "Complete required extraction fields before saving.",
            )
        return None
    if field_type in ("text", "source-passage"):
        return _clean_text(value, field["label"], 20_000)
    if field_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise UIError(
                "INVALID_INPUT", f"{field['label']} must be an integer.", "Enter a whole number."
            )
        return value
    if field_type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UIError(
                "INVALID_INPUT", f"{field['label']} must be numeric.", "Enter a finite number."
            )
        number = float(value)
        if not -1e300 < number < 1e300:
            raise UIError(
                "INVALID_INPUT",
                f"{field['label']} must be finite.",
                "Enter a finite numeric value.",
            )
        return number
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise UIError(
                "INVALID_INPUT",
                f"{field['label']} must be true or false.",
                "Choose one boolean value.",
            )
        return value
    if field_type == "date":
        text = _clean_text(value, field["label"], 10)
        if not _iso_date(text):
            raise UIError(
                "INVALID_INPUT",
                f"{field['label']} must use YYYY-MM-DD.",
                "Enter a valid calendar date.",
            )
        return text
    if field_type == "categorical":
        text = _clean_text(value, field["label"], 120)
        if text not in field.get("categories", []):
            raise UIError(
                "INVALID_INPUT",
                f"{field['label']} has an unknown category.",
                "Choose one of the configured categories.",
            )
        return text
    raise UIError(
        "INTEGRITY_FAILURE",
        "Extraction schema contains an unsupported field.",
        "Review or rebuild the extraction form.",
    )


def save_extraction(
    project: Project, *, source_id: str, values: Mapping[str, Any]
) -> dict[str, Any]:
    if len(project.extractions) >= MAX_EXTRACTIONS:
        raise UIError(
            "RESOURCE_LIMIT",
            "Extraction record limit reached.",
            "Archive or split the project before adding more records.",
        )
    schema = project.extraction_schema
    if not schema or not isinstance(schema.get("fields"), list):
        raise UIError(
            "NOT_FOUND",
            "No extraction form is configured.",
            "Build an extraction schema before recording study data.",
        )
    if not any(source.id == source_id for source in project.sources):
        raise UIError(
            "NOT_FOUND",
            "Extraction source is missing.",
            "Choose an imported source from the project library.",
        )
    allowed = {field["name"] for field in schema["fields"]}
    if any(key not in allowed for key in values):
        raise UIError(
            "INVALID_INPUT",
            "Extraction contains fields outside the schema.",
            "Remove unknown fields and retry.",
        )
    normalized = {
        field["name"]: _validate_extraction_value(field, values.get(field["name"]))
        for field in schema["fields"]
    }
    record = {
        "id": new_id(),
        "source_id": source_id,
        "schema_id": schema["id"],
        "schema_version": schema["version"],
        "values": normalized,
        "updated_at": utc_now(),
    }
    project.extractions.append(record)
    return _clone_dict(record)


def list_extractions(project: Project) -> dict[str, Any]:
    schema = _clone_dict(project.extraction_schema)
    return {
        "schema": schema or None,
        "records": _clone_list(project.extractions),
        "missing_required_warnings": [
            record["id"]
            for record in project.extractions
            if schema
            and any(
                field.get("required") and record.get("values", {}).get(field["name"]) in (None, "")
                for field in schema.get("fields", [])
            )
        ],
    }


def extraction_export(project: Project) -> dict[str, Any]:
    content = json.dumps(
        {
            "schema_version": 1,
            "extraction_schema": project.extraction_schema,
            "records": project.extractions,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return {
        "format": "application/json",
        "content": content,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def set_variable_metadata(
    project: Project, *, dataset_id: str, variable: str, metadata: Mapping[str, Any]
) -> dict[str, Any]:
    dataset = next((item for item in project.datasets if item.id == dataset_id), None)
    if dataset is None or variable not in dataset.columns:
        raise UIError(
            "NOT_FOUND",
            "Dataset variable was not found.",
            "Choose a column from the active dataset.",
        )
    variable_type = _clean_text(metadata.get("type"), "Variable type", 30)
    role = _clean_text(metadata.get("role"), "Variable role", 30)
    if variable_type not in VARIABLE_TYPES:
        raise UIError(
            "INVALID_INPUT",
            "Unsupported variable type.",
            "Choose numeric, categorical, boolean, date or text.",
        )
    if role not in VARIABLE_ROLES:
        raise UIError(
            "INVALID_INPUT",
            "Unsupported variable role.",
            "Choose outcome, predictor, group, confounder, identifier, weight or other.",
        )
    levels = _string_list(metadata.get("levels", []), "Variable levels", limit=500, item_limit=200)
    missing_codes = _string_list(
        metadata.get("missing_codes", []), "Missing codes", limit=100, item_limit=80
    )
    if len(set(levels)) != len(levels) or len(set(missing_codes)) != len(missing_codes):
        raise UIError(
            "INVALID_INPUT",
            "Variable levels and missing codes must be unique.",
            "Remove duplicate metadata entries.",
        )
    record = {
        "dataset_id": dataset_id,
        "variable": variable,
        "type": variable_type,
        "role": role,
        "units": _clean_text(metadata.get("units", ""), "Units", 120, required=False),
        "levels": levels,
        "missing_codes": missing_codes,
        "description": _clean_text(
            metadata.get("description", ""), "Description", 1_000, required=False
        ),
        "provenance": "manual user metadata",
        "updated_at": utc_now(),
    }
    project.variable_metadata[f"{dataset_id}:{variable}"] = record
    return _clone_dict(record)


class AnalysisBackend(Protocol):
    """Typed integration point for scientific methods owned outside the Qt layer."""

    def methods(self) -> list[Mapping[str, Any]]:
        """Return declared methods and typed argument contracts."""

    def run(self, method: str, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        """Run one scientific method and return a provenance-complete result."""


class AIBackend(Protocol):
    """Host-injected adapter for approved AI operations owned outside the Qt layer."""

    def capabilities(self) -> list[Mapping[str, Any]]:
        """Return AI operations that the trusted application host can route."""

    def execute_approved(
        self,
        project_id: str,
        action: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Execute one previously approved, fingerprint-bound desktop action."""

    def model_config(self) -> Mapping[str, Any]:
        """Read secret-free model profiles and the active selection."""

    def validate_model_profile(self, profile: Mapping[str, Any]) -> Mapping[str, Any]:
        """Validate one model profile without persisting it."""

    def save_model_profile(
        self,
        profile: Mapping[str, Any],
        *,
        activate: bool = True,
    ) -> Mapping[str, Any]:
        """Persist one validated secret-free model profile."""

    def activate_model(self, identifier: str | None) -> Mapping[str, Any]:
        """Select one saved model profile or disable model use."""

    def assistant_history(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        """Read one durable project assistant conversation."""

    def assistant_conversations(self, project_id: str) -> Mapping[str, Any]:
        """List durable assistant conversations for one project."""

    def assistant_send(
        self,
        project_id: str,
        prompt: str,
        *,
        conversation_id: str | None = None,
        profile_id: str | None = None,
        offline: bool,
        egress_acknowledged: bool,
        on_delta: Callable[[str], None] | None = None,
    ) -> Mapping[str, Any]:
        """Run one assistant turn inside the calling thread and stream real deltas."""

    def assistant_approve(
        self,
        project_id: str,
        conversation_id: str,
        *,
        offline: bool,
        egress_acknowledged: bool,
        on_delta: Callable[[str], None] | None = None,
    ) -> Mapping[str, Any]:
        """Execute exactly one persisted pending tool after trusted user approval."""

    def assistant_deny(self, project_id: str, conversation_id: str) -> Mapping[str, Any]:
        """Deny and clear exactly one persisted pending assistant tool request."""


def validate_analysis_result(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "method",
        "method_version",
        "inputs",
        "assumptions",
        "warnings",
        "estimates",
        "uncertainty",
        "diagnostics",
        "provenance",
    )
    missing = [name for name in required if name not in raw]
    if missing:
        raise UIError(
            "INTEGRITY_FAILURE",
            "Analysis backend returned incomplete provenance.",
            "The scientific adapter must provide method, inputs, assumptions, warnings, "
            "estimates, uncertainty, diagnostics and provenance.",
        )
    method = _clean_text(raw["method"], "Analysis method", 120)
    version = _clean_text(raw["method_version"], "Method version", 80)
    for key in ("inputs", "estimates", "uncertainty", "diagnostics", "provenance"):
        if not isinstance(raw[key], Mapping):
            raise UIError(
                "INTEGRITY_FAILURE",
                f"Analysis {key} must be structured.",
                "Repair the scientific adapter contract.",
            )
    assumptions = _string_list(
        raw["assumptions"], "Analysis assumptions", limit=100, item_limit=1_000
    )
    warnings = _string_list(raw["warnings"], "Analysis warnings", limit=100, item_limit=1_000)
    return {
        "id": new_id(),
        "method": method,
        "method_version": version,
        "inputs": dict(raw["inputs"]),
        "assumptions": assumptions,
        "warnings": warnings,
        "estimates": dict(raw["estimates"]),
        "uncertainty": dict(raw["uncertainty"]),
        "diagnostics": dict(raw["diagnostics"]),
        "provenance": dict(raw["provenance"]),
        "created_at": utc_now(),
    }


def store_analysis_result(project: Project, raw: Mapping[str, Any]) -> dict[str, Any]:
    if len(project.analysis_results) >= MAX_RESULTS:
        raise UIError(
            "RESOURCE_LIMIT",
            "Analysis result history limit reached.",
            "Archive old results before running more analyses.",
        )
    result = validate_analysis_result(raw)
    project.analysis_results.append(result)
    return _clone_dict(result)


def analysis_result_export(project: Project, result_id: str) -> dict[str, Any]:
    result = next((item for item in project.analysis_results if item.get("id") == result_id), None)
    if result is None:
        raise UIError(
            "NOT_FOUND", "Analysis result was not found.", "Choose a saved result from the project."
        )
    content = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    return {
        "format": "application/json",
        "content": content,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def upsert_code(
    project: Project,
    *,
    code_id: str = "",
    name: str,
    description: str = "",
    inclusion_rule: str = "",
    exclusion_rule: str = "",
    marker: str = "●",
) -> dict[str, Any]:
    clean_name = _clean_text(name, "Code name", 100)
    if any(
        item.get("name", "").casefold() == clean_name.casefold() and item.get("id") != code_id
        for item in project.codebook
    ):
        raise UIError(
            "CONFLICT", "A code with this name already exists.", "Choose a distinct code name."
        )
    record = {
        "id": code_id or new_id(),
        "name": clean_name,
        "description": _clean_text(description, "Code description", 1_000, required=False),
        "inclusion_rule": _clean_text(inclusion_rule, "Inclusion rule", 1_000, required=False),
        "exclusion_rule": _clean_text(exclusion_rule, "Exclusion rule", 1_000, required=False),
        "marker": _clean_text(marker, "Code marker", 8),
        "updated_at": utc_now(),
    }
    existing = next(
        (index for index, item in enumerate(project.codebook) if item.get("id") == record["id"]),
        None,
    )
    if existing is None:
        if len(project.codebook) >= MAX_CODES:
            raise UIError(
                "RESOURCE_LIMIT",
                "Codebook limit reached.",
                "Archive or merge codes before adding more.",
            )
        project.codebook.append(record)
    else:
        project.codebook[existing] = record
    return dict(record)


def merge_codes(
    project: Project, *, source_ids: list[str], target_id: str, conflict_note: str
) -> dict[str, Any]:
    ids = set(_string_list(source_ids, "Source code ids", limit=100, item_limit=60))
    if target_id in ids:
        ids.remove(target_id)
    target = next((item for item in project.codebook if item.get("id") == target_id), None)
    if target is None or not ids:
        raise UIError(
            "INVALID_INPUT",
            "Choose a target and at least one different source code.",
            "Review the codebook selection.",
        )
    known = {item.get("id") for item in project.codebook}
    if not ids <= known:
        raise UIError(
            "NOT_FOUND",
            "One or more source codes no longer exist.",
            "Refresh the codebook and retry.",
        )
    affected = 0
    source_names = {item["name"] for item in project.codebook if item.get("id") in ids}
    for annotation in project.annotations:
        if annotation.code in source_names:
            annotation.code = target["name"]
            affected += 1
    project.codebook = [item for item in project.codebook if item.get("id") not in ids]
    trace = {
        "id": new_id(),
        "action": "merge",
        "source_ids": sorted(ids),
        "target_id": target_id,
        "affected_annotations": affected,
        "conflict_note": _clean_text(conflict_note, "Conflict resolution note", 2_000),
        "timestamp": utc_now(),
    }
    project.recoding_trace.append(trace)
    project.recoding_trace = project.recoding_trace[-2_000:]
    return trace


def add_mixed_method_link(project: Project, payload: Mapping[str, Any]) -> dict[str, Any]:
    qualitative_refs = _string_list(
        payload.get("qualitative_refs", []), "Qualitative references", limit=200, item_limit=60
    )
    quantitative_refs = _string_list(
        payload.get("quantitative_refs", []), "Quantitative references", limit=200, item_limit=60
    )
    if not qualitative_refs or not quantitative_refs:
        raise UIError(
            "INVALID_INPUT",
            "Mixed-method links need qualitative and quantitative refs.",
            "Select at least one item from each method stream.",
        )
    relation = _clean_text(payload.get("relation"), "Convergence state", 30)
    if relation not in ("converges", "diverges", "complements", "uncertain"):
        raise UIError(
            "INVALID_INPUT",
            "Unknown mixed-method relation.",
            "Choose converges, diverges, complements or uncertain.",
        )
    record = {
        "id": new_id(),
        "qualitative_refs": qualitative_refs,
        "quantitative_refs": quantitative_refs,
        "relation": relation,
        "units": _clean_text(payload.get("units", ""), "Units", 200, required=False),
        "group_definition": _clean_text(
            payload.get("group_definition", ""), "Group definition", 1_000, required=False
        ),
        "evidence_origin": _clean_text(payload.get("evidence_origin"), "Evidence origin", 1_000),
        "interpretation": _clean_text(
            payload.get("interpretation", ""), "Interpretation", 2_000, required=False
        ),
        "warning": (
            "Linked evidence remains method-specific; do not aggregate incompatible scales, "
            "units or populations without an explicit scientific justification."
        ),
        "created_at": utc_now(),
    }
    project.mixed_method_links.append(record)
    project.mixed_method_links = project.mixed_method_links[-2_000:]
    return record


def upsert_reference(project: Project, payload: Mapping[str, Any]) -> dict[str, Any]:
    reference_id = _clean_text(payload.get("id", new_id()), "Reference id", 60)
    source_id = _clean_text(payload.get("source_id", ""), "Source id", 60, required=False)
    if source_id and not any(source.id == source_id for source in project.sources):
        raise UIError(
            "NOT_FOUND", "Linked source was not found.", "Choose a source from the current project."
        )
    doi = _clean_text(payload.get("doi", ""), "DOI", 200, required=False)
    if doi and not re.fullmatch(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", doi):
        raise UIError(
            "INVALID_INPUT",
            "DOI format is not valid.",
            "Correct the DOI manually; no DOI is inferred automatically.",
        )
    authors = _string_list(
        payload.get("authors", []), "Reference authors", limit=200, item_limit=300
    )
    title = _clean_text(payload.get("title"), "Reference title", 1_000)
    record = {
        "id": reference_id,
        "source_id": source_id,
        "title": title,
        "authors": authors,
        "year": _clean_text(payload.get("year", ""), "Publication year", 20, required=False),
        "container": _clean_text(
            payload.get("container", ""), "Journal or container", 500, required=False
        ),
        "doi": doi,
        "url": _clean_text(payload.get("url", ""), "Reference URL", 2_000, required=False),
        "verified": bool(payload.get("verified", False)),
        "verification_note": _clean_text(
            payload.get("verification_note", ""), "Verification note", 1_000, required=False
        ),
        "updated_at": utc_now(),
    }
    existing = next(
        (index for index, item in enumerate(project.references) if item.get("id") == reference_id),
        None,
    )
    if existing is None:
        if len(project.references) >= MAX_REFERENCES:
            raise UIError(
                "RESOURCE_LIMIT",
                "Reference limit reached.",
                "Archive or split the project before adding more references.",
            )
        project.references.append(record)
    else:
        project.references[existing] = record
    return record


def citation_text(project: Project, reference_id: str) -> dict[str, Any]:
    record = next((item for item in project.references if item.get("id") == reference_id), None)
    if record is None:
        raise UIError("NOT_FOUND", "Reference was not found.", "Choose an existing reference.")
    authors = record.get("authors") or []
    author_text = ", ".join(authors) if authors else "[author missing]"
    year = record.get("year") or "[year missing]"
    title = record.get("title") or "[title missing]"
    suffix = f" https://doi.org/{record['doi']}" if record.get("doi") else ""
    missing = [field for field in ("authors", "year", "title") if not record.get(field)]
    return {
        "text": f"{author_text} ({year}). {title}.{suffix}",
        "verified": bool(record.get("verified")),
        "missing_fields": missing,
        "warning": (
            "Citation metadata are user-entered and must be verified against the original source."
        ),
    }


def _action_fingerprint(record: Mapping[str, Any]) -> str:
    keys = (
        "operation",
        "target",
        "arguments",
        "changed_fields",
        "files",
        "network_destination",
        "data_egress",
        "destructive_effect",
    )
    return _canonical_hash({key: record.get(key) for key in keys})


def propose_action(project: Project, payload: Mapping[str, Any]) -> dict[str, Any]:
    if len(project.agent_actions) >= MAX_AGENT_EVENTS:
        raise UIError(
            "RESOURCE_LIMIT",
            "Agent timeline limit reached.",
            "Archive the project audit log before adding more events.",
        )
    operation = _clean_text(payload.get("operation"), "Operation", 200)
    target = _clean_text(payload.get("target"), "Action target", 1_000)
    arguments = dict(_mapping(payload.get("arguments", {}), "Operation arguments"))
    changed = dict(_mapping(payload.get("changed_fields", {}), "Changed fields"))
    files = _string_list(payload.get("files", []), "Action files", limit=200, item_limit=1_000)
    destination = _clean_text(
        payload.get("network_destination", ""), "Network destination", 1_000, required=False
    )
    data_egress = bool(payload.get("data_egress", False))
    destructive = bool(payload.get("destructive_effect", False))
    if data_egress and not destination:
        raise UIError(
            "INVALID_INPUT",
            "Data egress requires an explicit network destination.",
            "Specify the exact remote destination before requesting approval.",
        )
    record: dict[str, Any] = {
        "id": new_id(),
        "event": "proposed",
        "operation": operation,
        "target": target,
        "arguments": arguments,
        "changed_fields": changed,
        "files": files,
        "network_destination": destination,
        "data_egress": data_egress,
        "destructive_effect": destructive,
        "provider": _clean_text(payload.get("provider", "manual"), "Provider", 100),
        "model": _clean_text(payload.get("model", ""), "Model", 200, required=False),
        "input_refs": _string_list(
            payload.get("input_refs", []), "Input references", limit=500, item_limit=120
        ),
        "output_refs": [],
        "timestamp": utc_now(),
        "approval_id": "",
        "approval_fingerprint": "",
        "proposal_revision": project.revision + 1,
        "idempotency_key": "",
        "message": "Proposal only; no action has executed.",
    }
    fingerprint = _action_fingerprint(record)
    record["fingerprint"] = fingerprint
    record["idempotency_key"] = hashlib.sha256(
        f"{project.id}:{record['id']}:{fingerprint}".encode()
    ).hexdigest()
    project.agent_actions.append(record)
    return _clone_dict(record)


def _proposal(project: Project, action_id: str) -> dict[str, Any]:
    record = next((item for item in project.agent_actions if item.get("id") == action_id), None)
    if record is None:
        raise UIError(
            "NOT_FOUND",
            "Agent proposal was not found.",
            "Refresh the timeline and choose an existing proposal.",
        )
    return record


def approve_action(
    project: Project,
    *,
    action_id: str,
    expected_fingerprint: str,
) -> dict[str, Any]:
    record = _proposal(project, action_id)
    if record.get("event") != "proposed":
        raise UIError(
            "CONFLICT",
            "This proposal is no longer awaiting approval.",
            "Review its current timeline state.",
        )
    if project.revision != record.get("proposal_revision"):
        raise UIError(
            "STALE_REVISION",
            "The project changed after this action was proposed.",
            "Generate a new proposal against the current project state.",
        )
    if expected_fingerprint != record.get("fingerprint"):
        raise UIError(
            "PERMISSION_DENIED",
            "Approval scope does not match the proposed action.",
            "Review the exact target, changed fields, files and egress destination.",
        )
    approval_id = new_id()
    record["event"] = "approved"
    record["approval_id"] = approval_id
    record["approval_fingerprint"] = expected_fingerprint
    record["timestamp"] = utc_now()
    record["message"] = "Approved for this exact fingerprint only; execution remains separate."
    return _clone_dict(record)


def deny_action(project: Project, *, action_id: str, reason: str) -> dict[str, Any]:
    record = _proposal(project, action_id)
    if record.get("event") != "proposed":
        raise UIError(
            "CONFLICT",
            "This proposal is no longer awaiting a decision.",
            "Review its current timeline state.",
        )
    record["event"] = "denied"
    record["timestamp"] = utc_now()
    record["message"] = _clean_text(reason, "Denial reason", 1_000)
    return _clone_dict(record)


def record_action_execution(
    project: Project,
    *,
    action_id: str,
    approval_id: str,
    event: str,
    output_refs: list[str] | None = None,
    message: str = "",
) -> dict[str, Any]:
    record = _proposal(project, action_id)
    if event not in ("started", "completed", "failed", "canceled"):
        raise UIError(
            "INVALID_INPUT",
            "Unknown agent execution event.",
            "Use started, completed, failed or canceled.",
        )
    if not record.get("approval_id") or approval_id != record.get("approval_id"):
        raise UIError(
            "PERMISSION_DENIED",
            "Execution approval does not match this action.",
            "Approve the exact proposal before execution.",
        )
    if record.get("approval_fingerprint") != _action_fingerprint(record):
        raise UIError(
            "PERMISSION_DENIED",
            "Approved action scope changed after approval.",
            "Discard it and create a new proposal.",
        )
    record["event"] = event
    record["timestamp"] = utc_now()
    record["output_refs"] = _string_list(
        output_refs or [], "Output references", limit=500, item_limit=120
    )
    record["message"] = _clean_text(message, "Execution message", 1_000, required=False)
    return _clone_dict(record)


def configure_provider(project: Project, payload: Mapping[str, Any]) -> dict[str, Any]:
    mode = _clean_text(payload.get("mode"), "Provider mode", 30)
    if mode not in PROVIDER_MODES:
        raise UIError(
            "INVALID_INPUT", "Unsupported provider mode.", "Choose manual, local or cloud-api."
        )
    provider_id = _clean_text(payload.get("provider_id", mode), "Provider id", 100)
    protocol = _clean_text(
        payload.get("protocol", "openai-compatible"),
        "Provider protocol",
        40,
    )
    if protocol not in ("openai-compatible", "anthropic", "gemini"):
        raise UIError(
            "INVALID_INPUT",
            "Unsupported provider protocol.",
            "Choose OpenAI-compatible, Anthropic or Gemini.",
        )
    endpoint = _clean_text(payload.get("endpoint", ""), "Provider endpoint", 2_000, required=False)
    model = _clean_text(payload.get("model", ""), "Model identifier", 256, required=False)
    credential_env = _clean_text(
        payload.get("credential_env", ""),
        "Credential environment variable",
        128,
        required=False,
    )
    tool_calling = bool(payload.get("tool_calling", False))
    enabled = bool(payload.get("enabled", False))
    credential_present = bool(payload.get("credential_present", False))
    availability = _clean_text(payload.get("availability", "not-checked"), "Availability state", 40)
    if availability not in ("not-checked", "available", "unavailable", "offline-blocked"):
        raise UIError(
            "INVALID_INPUT",
            "Unsupported availability state.",
            "Use not-checked, available, unavailable or offline-blocked.",
        )
    permission_scope = _string_list(
        payload.get("permission_scope", []), "Provider permission scope", limit=100, item_limit=120
    )
    egress_ack = bool(payload.get("egress_acknowledged", False))
    if mode == "cloud-api" and enabled and not credential_present:
        raise UIError(
            "PROVIDER_UNAVAILABLE",
            "Cloud provider has no configured credential.",
            "Configure a supported API credential or switch to manual/local mode.",
        )
    if mode == "cloud-api" and enabled and not egress_ack:
        raise UIError(
            "NEEDS_APPROVAL",
            "Cloud provider data egress has not been acknowledged.",
            "Review the data scope and explicitly acknowledge remote transfer.",
        )
    if mode != "manual" and enabled and (not endpoint or not model):
        raise UIError(
            "INVALID_INPUT",
            "Enabled model providers require an endpoint and model identifier.",
            "Enter the local or hosted endpoint and the exact model identifier.",
        )
    if mode == "manual":
        credential_present = False
        availability = "available"
        permission_scope = []
        egress_ack = False
        endpoint = ""
        model = ""
        credential_env = ""
        tool_calling = False
    record = {
        "mode": mode,
        "provider_id": provider_id,
        "protocol": protocol,
        "endpoint": endpoint,
        "model": model,
        "credential_env": credential_env,
        "tool_calling": tool_calling,
        "enabled": enabled if mode != "manual" else True,
        "credential_present": credential_present,
        "availability": availability,
        "permission_scope": permission_scope,
        "egress_acknowledged": egress_ack,
        "updated_at": utc_now(),
        "note": (
            "No consumer subscription access is assumed. Cloud access requires a supported "
            "credential workflow and explicit data-egress review."
        ),
    }
    project.provider_config = record
    return dict(record)


def provider_status(project: Project, *, offline: bool) -> dict[str, Any]:
    configured = project.provider_config or {
        "mode": "manual",
        "provider_id": "manual",
        "protocol": "openai-compatible",
        "endpoint": "",
        "model": "",
        "credential_env": "",
        "tool_calling": False,
        "enabled": True,
        "credential_present": False,
        "availability": "available",
        "permission_scope": [],
        "egress_acknowledged": False,
        "note": "Manual/no-provider mode is always available locally.",
    }
    result = _clone_dict(configured)
    if offline and result.get("mode") == "cloud-api":
        result["effective_availability"] = "offline-blocked"
    else:
        result["effective_availability"] = result.get("availability", "not-checked")
    result["network_calls_observed"] = 0
    return result


def set_integration(
    project: Project, *, integration_id: str, connected: bool, permissions: list[str]
) -> dict[str, Any]:
    if integration_id not in INTEGRATION_IDS:
        raise UIError(
            "NOT_FOUND", "Unknown optional integration.", "Choose a bundled integration adapter."
        )
    clean_permissions = _string_list(
        permissions, "Integration permissions", limit=100, item_limit=160
    )
    if connected:
        raise UIError(
            "DEPENDENCY_MISSING",
            "This UI worker cannot establish external connections.",
            "Use the final integration layer with an installed, authorized adapter.",
        )
    record = {
        "id": integration_id,
        "connected": False,
        "enabled": False,
        "permissions": clean_permissions,
        "status": "disconnected",
        "capabilities": {
            "crossref": ["reference-metadata"],
            "openalex": ["reference-metadata", "literature-discovery"],
            "zotero": ["reference-import"],
            "osf": ["project-export"],
            "sync-folder": ["file-sync"],
        }[integration_id],
        "updated_at": utc_now(),
        "note": "Disabled by default; local-only workflows remain available.",
    }
    existing = next(
        (
            index
            for index, item in enumerate(project.integrations)
            if item.get("id") == integration_id
        ),
        None,
    )
    if existing is None:
        project.integrations.append(record)
    else:
        project.integrations[existing] = record
    return record


def integration_catalog(project: Project) -> list[dict[str, Any]]:
    saved = {item.get("id"): item for item in project.integrations}
    result = []
    for integration_id in sorted(INTEGRATION_IDS):
        result.append(
            saved.get(integration_id)
            or {
                "id": integration_id,
                "connected": False,
                "enabled": False,
                "permissions": [],
                "status": "disconnected",
                "capabilities": {
                    "crossref": ["reference-metadata"],
                    "openalex": ["reference-metadata", "literature-discovery"],
                    "zotero": ["reference-import"],
                    "osf": ["project-export"],
                    "sync-folder": ["file-sync"],
                }[integration_id],
                "note": "Disabled by default; no network connection has been attempted.",
            }
        )
    return _clone_list(result)


def add_notification(
    project: Project,
    *,
    code: str,
    severity: str,
    message: str,
    recovery: str,
    linkage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if severity not in ("info", "warning", "error"):
        raise UIError(
            "INVALID_INPUT", "Unknown notification severity.", "Use info, warning or error."
        )
    safe_message = _clean_text(message, "Notification message", 1_000)
    safe_recovery = _clean_text(recovery, "Recovery action", 1_000)
    # Reject common credential material from persistent diagnostics.
    lowered = f"{safe_message} {safe_recovery}".casefold()
    if any(token in lowered for token in ("api_key=", "authorization: bearer", "password=")):
        raise UIError(
            "UNTRUSTED_CONTENT",
            "Diagnostic text appears to contain a credential.",
            "Redact secrets before saving diagnostic details.",
        )
    record = {
        "id": new_id(),
        "diagnostic_id": hashlib.sha256(f"{project.id}:{code}:{utc_now()}".encode()).hexdigest()[
            :16
        ],
        "code": _clean_text(code, "Notification code", 80),
        "severity": severity,
        "message": safe_message,
        "recovery": safe_recovery,
        "linkage": dict(linkage or {}),
        "dismissed": False,
        "created_at": utc_now(),
    }
    project.notifications.append(record)
    project.notifications = project.notifications[-1_000:]
    return record


def dismiss_notification(project: Project, notification_id: str) -> dict[str, Any]:
    record = next(
        (item for item in project.notifications if item.get("id") == notification_id), None
    )
    if record is None:
        raise UIError("NOT_FOUND", "Notification was not found.", "Refresh the error center.")
    record["dismissed"] = True
    return dict(record)


def privacy_report(project: Project, *, offline: bool, backup_root: str) -> dict[str, Any]:
    provider = provider_status(project, offline=offline)
    return {
        "offline_mode": offline,
        "telemetry_enabled": False,
        "provider": provider,
        "provider_egress_enabled": bool(
            provider.get("mode") == "cloud-api"
            and provider.get("enabled")
            and provider.get("egress_acknowledged")
            and not offline
        ),
        "selected_data_scope": provider.get("permission_scope", []),
        "backup_destination": backup_root,
        "sync_destinations": [item["id"] for item in project.integrations if item.get("connected")],
        "retention": {
            "activity_events": 1_000,
            "notifications": 1_000,
            "agent_events": MAX_AGENT_EVENTS,
        },
        "credential_storage": "Credentials are not stored by this UI worker.",
        "audit_events": len(project.activity) + len(project.agent_actions),
        "deletion_preview": {
            "project_id": project.id,
            "project_title": project.title,
            "sources": len(project.sources),
            "datasets": len(project.datasets),
            "warning": "Deletion is not implemented in this worker; no files were removed.",
        },
        "network_calls_observed": 0,
    }


def set_review_flow(project: Project, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Persist only explicitly supplied PRISMA stages; unknown values remain null."""
    keys = (
        "records_identified",
        "duplicates_removed",
        "records_screened",
        "records_excluded",
        "reports_sought",
        "reports_not_retrieved",
        "reports_assessed",
        "reports_excluded",
        "studies_included",
    )
    result: dict[str, Any] = {}
    for key in keys:
        value = payload.get(key)
        if value is None:
            result[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UIError(
                "INVALID_INPUT",
                f"{key} must be a nonnegative count or unknown.",
                "Use a measured count or leave the stage unknown.",
            )
        result[key] = value
    reasons_raw = payload.get("exclusion_reasons", {})
    reasons = _mapping(reasons_raw, "Exclusion reasons")
    normalized_reasons: dict[str, int] = {}
    for label, value in reasons.items():
        clean_label = _clean_text(label, "Exclusion reason", 300)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UIError(
                "INVALID_INPUT",
                "Exclusion reason counts must be nonnegative.",
                "Correct the supplied reason count.",
            )
        normalized_reasons[clean_label] = value
    result["exclusion_reasons"] = normalized_reasons
    result["updated_at"] = utc_now()
    project.review_flow = result
    return _clone_dict(result)


def combined_prisma(project: Project, screening: Mapping[str, Any]) -> dict[str, Any]:
    supplied = project.review_flow
    return {
        "records_identified": supplied.get("records_identified"),
        "duplicates_removed": supplied.get("duplicates_removed"),
        "records_screened": supplied.get(
            "records_screened", screening.get("screened_with_final_outcome")
        ),
        "records_excluded": supplied.get("records_excluded", screening.get("excluded")),
        "reports_sought": supplied.get("reports_sought"),
        "reports_not_retrieved": supplied.get("reports_not_retrieved"),
        "reports_assessed": supplied.get("reports_assessed"),
        "reports_excluded": supplied.get("reports_excluded"),
        "studies_included": supplied.get("studies_included"),
        "exclusion_reasons": (
            supplied.get("exclusion_reasons") or screening.get("excluded_reasons", {})
        ),
        "source": "explicit review-flow events plus grounded local screening events",
        "unknowns_preserved": True,
        "warning": "Unknown stages remain null and are never inferred from unrelated counts.",
    }
