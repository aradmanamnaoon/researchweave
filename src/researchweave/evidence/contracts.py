"""Shared versioned facade input and response contracts.

This deliberately supports a conservative, executable subset of JSON Schema.
Every advertised *required* field has a concrete type/bound. Unknown optional
fields remain allowed for stable extensibility; domain-specific invariants are
still validated by their respective services before any mutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import require

_ARRAYS = {
    "files", "inventory", "reference_ids", "source_ids", "collection_ids",
    "review_ids", "protocol_ids", "tags", "searches", "sections", "unresolved", "actions",
    "redact_fields",
}
_OBJECTS = {
    "advanced", "candidate", "citations", "extracted", "finding", "metadata",
    "migration", "observed", "policies", "requirements", "responses", "schema",
    "supplied_metadata", "values",
}
_INTEGERS = {
    "end",
    "expected_records",
    "from_revision",
    "from_version",
    "limit",
    "offset",
    "page",
    "start",
    "statement_end",
    "statement_start",
    "to_revision",
    "to_version",
    "total_limit",
    "page_size",
    "version",
}
_OPTIONAL: dict[str, str] = {
    "privacy": "string", "locale": "string", "filename": "string",
    "format": "string", "author": "string", "include_revoked": "boolean",
    "include_notes": "boolean", "confirm_private_export": "boolean",
    "allow_incomplete": "boolean", "strict": "boolean",
    "search": "string", "limit": "integer", "offset": "integer",
    "page": "integer", "year_from": "integer", "year_to": "integer",
    "body": "string", "fields": "object", "filters": "object",
    "kind": "string", "source_id": "string", "reference_id": "string",
    "rationale": "string", "actor": "string", "review_id": "string",
    "checked_at": "string", "start": "integer", "end": "integer",
    "expected_records": "integer", "allow_network": "boolean",
    "collection_ids": "array", "review_ids": "array", "protocol_ids": "array",
    "mode": "string", "stage": "string", "description": "string",
    "tags": "array", "advanced": "object", "metadata": "object",
    "anchor_id": "string", "interpretation": "boolean", "relationship": "string",
    "status": "string", "priority": "string", "style": "string",
    "version": "integer", "requirements": "object", "supplied_metadata": "object",
    "reference_ids": "array", "redact_fields": "array",
    "destination_review_id": "string",
    "total_limit": "integer", "page_size": "integer",
}
_NUMERIC_MIN = {
    "start": 0,
    "end": 0,
    "limit": 1,
    "offset": 0,
    "expected_records": 0,
    "page": 1,
    "from_revision": 1,
    "from_version": 1,
    "statement_start": 0,
    "statement_end": 1,
    "to_revision": 1,
    "to_version": 1,
    "total_limit": 1,
    "page_size": 1,
    "version": 1,
}
_ENUMS = {
    "privacy": ["private", "restricted", "public"],
    "stage": ["title_abstract", "full_text"],
    "decision": ["include", "exclude", "unsure"],
    "disposition": ["retained", "duplicate", "removed_automation", "removed_other"],
}
_MAX_ITEMS = {"files": 1000, "reference_ids": 5000, "source_ids": 5000,
              "collection_ids": 5000, "review_ids": 5000, "protocol_ids": 5000,
              "tags": 500, "searches": 2000, "sections": 1000,
              "inventory": 10000, "unresolved": 10000, "actions": 20,
              "redact_fields": 100}


def _schema_for(name: str, operation: str) -> dict[str, Any]:
    if name == "data_base64":
        return {"type": "string", "minLength": 1, "maxLength": 45 * 1024 * 1024,
                "contentEncoding": "base64"}
    if name == "password":
        return {"type": "string", "minLength": 1, "maxLength": 1024,
                "writeOnly": True}
    if name == "mode" and operation.startswith("project.wizard_"):
        return {"type": "string", "enum": ["beginner", "advanced"]}
    if name == "stage" and operation.startswith("project.wizard_"):
        return {
            "type": "string",
            "enum": [
                "planning", "protocol", "discovery", "screening", "extraction",
                "synthesis", "writing",
            ],
        }
    if name == "status" and operation == "review.gap_update":
        return {"type": "string", "enum": ["open", "addressed"]}
    if name == "priority" and operation == "review.gap_update":
        return {"type": "string", "enum": ["low", "medium", "high", "critical"]}
    if name == "relationship" and operation == "review.study_attach":
        return {
            "type": "string",
            "enum": ["primary", "secondary", "protocol", "correction", "other"],
        }
    if name == "body":
        if operation.startswith("protocol."):
            return {"type": "object", "maxProperties": 500}
        return {"type": "string", "maxLength": 1000000}
    if name == "fields":
        return (
            {"type": "object", "maxProperties": 500}
            if operation.startswith("question.")
            else {"type": "array", "maxItems": 200, "items": {"type": "object"}}
        )
    if name in _OBJECTS:
        return {"type": "object", "maxProperties": 500}
    if name in _ARRAYS:
        result: dict[str, Any] = {"type": "array", "maxItems": _MAX_ITEMS[name]}
        if name != "unresolved":
            result["items"] = ({"type": "object"} if name in {
                "files", "inventory", "searches", "sections"
            } else {"type": "string"})
        return result
    if name in _INTEGERS or name in {"year_from", "year_to"}:
        result = {"type": "integer"}
        if name in _NUMERIC_MIN:
            result["minimum"] = _NUMERIC_MIN[name]
        if name == "limit":
            result["maximum"] = 1000
        if name == "total_limit":
            result["maximum"] = 200
        if name == "page_size":
            result["maximum"] = 50
        return result
    if name in _OPTIONAL and _OPTIONAL[name] == "boolean":
        return {"type": "boolean"}
    if name in _OPTIONAL and _OPTIONAL[name] == "object":
        return {"type": "object", "maxProperties": 500}
    result = {"type": "string", "maxLength": 20000 if name in {
        "rationale", "reason", "limitations", "provenance", "quote", "question"
    } else 5000}
    if name in {"project_id", "source_id", "reference_id", "record_id", "anchor_id",
                "review_id", "run_id", "collection_id", "plan_id", "form_id",
                "outline_id", "protocol_id", "batch_id", "edge_id", "snapshot",
                "note_id", "question_id", "study_id", "gap_id", "manuscript_id", "figure_id"}:
        result["minLength"] = 1
        result["maxLength"] = 255
    if name in _ENUMS:
        result["enum"] = _ENUMS[name]
    return result


def arguments_schema(operation: str, required: tuple[str, ...]) -> dict[str, Any]:
    """Generate an executable, bounded schema for declared facade parameters."""
    names = sorted(set(required) | set(_OPTIONAL))
    properties = {name: _schema_for(name, operation) for name in names}
    if "body" in required:
        properties["body"] = _schema_for("body", operation)
    if "fields" in required:
        properties["fields"] = _schema_for("fields", operation)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", "required": list(required),
            "properties": properties, "additionalProperties": True,
            "maxProperties": 250}


def response_schema() -> dict[str, Any]:
    """Actual public response envelope (success and failure share a shape)."""
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["request_id", "status", "data", "artifacts", "warnings",
                         "error", "provenance", "impact"],
            "properties": {
                "request_id": {"type": "string"},
                "status": {"type": "string", "enum": ["ok", "failed"]},
                "data": {"type": "object"},
                "artifacts": {"type": "array"},
                "warnings": {"type": "array"},
                "error": {"type": ["object", "null"]},
                "provenance": {"type": "array"},
                "impact": {"type": "object"},
            }}


def _validate_field(value: Any, schema: Mapping[str, Any], name: str) -> None:
    dtype = schema["type"]
    is_valid = {
        "string": lambda: isinstance(value, str),
        "integer": lambda: type(value) is int,
        "number": lambda: type(value) in (int, float),
        "object": lambda: isinstance(value, Mapping),
        "array": lambda: isinstance(value, list),
        "boolean": lambda: isinstance(value, bool),
    }[dtype]()
    require(is_valid, f"Invalid argument type: {name}")
    if "enum" in schema:
        require(value in schema["enum"], f"Unsupported value for {name}")
    if dtype == "string":
        require(len(value) <= schema.get("maxLength", 2**31),
                f"Argument exceeds length limit: {name}", "RESOURCE_LIMIT")
        require(len(value) >= schema.get("minLength", 0),
                f"Missing argument text: {name}")
    if dtype == "integer":
        require(value >= schema.get("minimum", -(2**63)),
                f"Argument outside range: {name}")
        require(value <= schema.get("maximum", 2**63 - 1),
                f"Argument outside range: {name}", "RESOURCE_LIMIT")
    if dtype == "object":
        require(len(value) <= schema.get("maxProperties", 5000),
                f"Too many properties in {name}", "RESOURCE_LIMIT")
        require(all(isinstance(key, str) for key in value),
                f"Argument object must use string keys: {name}")
    if dtype == "array":
        require(len(value) <= schema.get("maxItems", 5000),
                f"Too many array values in {name}", "RESOURCE_LIMIT")
        if "items" in schema:
            for item in value:
                _validate_field(item, schema["items"], f"{name}[]")


def validate_arguments(operation: str, required: tuple[str, ...],
                       arguments: Mapping[str, Any]) -> None:
    """Check actual user input against every advertised required field schema."""
    require(isinstance(arguments, Mapping), "Arguments must be an object")
    schema = arguments_schema(operation, required)
    require(len(arguments) <= schema["maxProperties"],
            "Too many command arguments", "RESOURCE_LIMIT")
    for name in required:
        require(name in arguments, f"Missing required argument: {name}")
    properties = schema["properties"]
    for name, value in arguments.items():
        require(isinstance(name, str), "Command argument names must be strings")
        definition = properties.get(name)
        if definition is not None:
            _validate_field(value, definition, name)


def risk_metadata(operation: str, effect: str) -> tuple[list[str], list[str]]:
    risks: list[str] = []
    constraints = ["Data is local-first; no telemetry is collected by this facade."]
    if effect == "external-network":
        risks.append("provider_metadata_may_be_inaccurate")
        constraints.append("Requires explicitly enabled trusted HTTPS transport.")
    if effect == "local-write":
        risks.append("persistent_project_mutation")
        constraints.append("Requires trusted host local-write access and supports revision checks.")
    if any(marker in operation for marker in ("export", "packet", "clone", "archive")):
        risks.append("potential_private_research_disclosure")
        constraints.append("Review destination privacy and data classifications before sharing.")
    if operation.startswith(("reference.", "review.", "writing.", "evidence.")):
        constraints.append("Identifier or source hash does not prove scientific claim support.")
    return risks, constraints
