"""Bounded, strict validation of provider-generated JSON against a safe schema subset."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .errors import AIError


def parse_structured_output(
    text: str,
    schema: Mapping[str, Any],
    *,
    max_bytes: int = 1_000_000,
) -> Any:
    """Parse JSON exactly, refusing duplicate keys, invalid constants and schema mismatches.

    Supports type, enum, const, properties, required, additionalProperties, items,
    min/maxItems, min/maxLength, minimum, maximum and depth limits. Unsupported
    schema keywords are rejected rather than silently bypassed.
    """
    if not isinstance(text, str) or len(text.encode("utf-8")) > max_bytes:
        raise AIError("RESOURCE_LIMIT", "Structured output exceeds byte limit")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AIError("SCHEMA_MISMATCH", "Duplicate JSON property")
            result[key] = value
        return result

    def invalid_constant(_: str) -> Any:
        raise AIError("SCHEMA_MISMATCH", "Nonfinite JSON numeric constant")

    try:
        value = json.loads(text, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as exc:
        raise AIError("SCHEMA_MISMATCH", "Invalid JSON structured output") from exc
    validate_schema(value, schema)
    return value


def validate_schema(value: Any, schema: Mapping[str, Any], *, max_depth: int = 32) -> None:
    allowed = {
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "description",
        "title",
    }

    def walk(node: Any, spec: Mapping[str, Any], path: str, depth: int) -> None:
        if depth > max_depth:
            raise AIError("RESOURCE_LIMIT", "Structured output nesting limit exceeded")
        if not isinstance(spec, Mapping) or set(spec) - allowed:
            raise AIError("INVALID_INPUT", "Unsupported structured-output schema")
        kind = spec.get("type")
        types = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }
        if kind is not None and (kind not in types or not types[kind](node)):
            raise AIError("SCHEMA_MISMATCH", f"Unexpected value at {path}")
        if "enum" in spec and node not in spec["enum"]:
            raise AIError("SCHEMA_MISMATCH", f"Unexpected enum at {path}")
        if "const" in spec and (type(node) is not type(spec["const"]) or node != spec["const"]):
            raise AIError("SCHEMA_MISMATCH", f"Unexpected constant at {path}")
        if isinstance(node, dict):
            properties = spec.get("properties", {})
            required = spec.get("required", [])
            if not isinstance(properties, Mapping) or not isinstance(required, list):
                raise AIError("INVALID_INPUT", "Malformed object schema")
            for key in required:
                if not isinstance(key, str) or key not in node:
                    raise AIError("SCHEMA_MISMATCH", f"Missing required property at {path}")
            extra = spec.get("additionalProperties", True)
            for key, item in node.items():
                if key in properties:
                    walk(item, properties[key], f"{path}.{key}", depth + 1)
                elif extra is False:
                    raise AIError("SCHEMA_MISMATCH", f"Unexpected property at {path}")
                elif isinstance(extra, Mapping):
                    walk(item, extra, f"{path}.{key}", depth + 1)
        if isinstance(node, list):
            minimum = spec.get("minItems")
            maximum = spec.get("maxItems")
            if minimum is not None and len(node) < minimum:
                raise AIError("SCHEMA_MISMATCH", f"Invalid list length at {path}")
            if maximum is not None and len(node) > maximum:
                raise AIError("SCHEMA_MISMATCH", f"Invalid list length at {path}")
            if "items" in spec:
                for index, item in enumerate(node):
                    walk(item, spec["items"], f"{path}[{index}]", depth + 1)
        if isinstance(node, str):
            minimum = spec.get("minLength")
            maximum = spec.get("maxLength")
            if minimum is not None and len(node) < minimum:
                raise AIError("SCHEMA_MISMATCH", f"Invalid string length at {path}")
            if maximum is not None and len(node) > maximum:
                raise AIError("SCHEMA_MISMATCH", f"Invalid string length at {path}")
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            if "minimum" in spec and node < spec["minimum"]:
                raise AIError("SCHEMA_MISMATCH", f"Number below minimum at {path}")
            if "maximum" in spec and node > spec["maximum"]:
                raise AIError("SCHEMA_MISMATCH", f"Number above maximum at {path}")

    walk(value, schema, "$", 0)
