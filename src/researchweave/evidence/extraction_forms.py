"""Versioned extraction-form schemas with explicit prior-value migration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, cast

from .errors import EvidenceError, require
from .extraction import ExtractedValue, FieldDefinition, validate_field
from .models import canonical_json, new_id, now_utc, sha256
from .storage import ProjectStore


def _field_from_wire(data: Mapping[str, Any]) -> FieldDefinition:
    permitted = data.get("permitted_values", ())
    require(
        isinstance(permitted, (list, tuple))
        and all(isinstance(value, str) for value in permitted),
        "permitted_values must contain strings",
    )
    dtype = data.get("datatype")
    require(isinstance(dtype, str) and dtype in
            {"number", "integer", "string", "boolean", "category"},
            "Unsupported extraction field datatype")
    typed_dtype = cast(Literal["number", "integer", "string", "boolean", "category"],
                       dtype)
    return FieldDefinition(
        name=str(data.get("name", "")),
        datatype=typed_dtype,
        required=bool(data.get("required", False)),
        permitted_values=tuple(permitted),
        unit=data.get("unit") if isinstance(data.get("unit"), str) else None,
        minimum=data.get("minimum") if type(data.get("minimum")) in {int, float} else None,
        maximum=data.get("maximum") if type(data.get("maximum")) in {int, float} else None,
    )


def _field_wire(field: FieldDefinition) -> dict[str, Any]:
    return {
        "name": field.name,
        "datatype": field.datatype,
        "required": field.required,
        "permitted_values": list(field.permitted_values),
        "unit": field.unit,
        "minimum": field.minimum,
        "maximum": field.maximum,
    }


class ExtractionFormService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    @staticmethod
    def _tables(conn: Any) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS extraction_forms ("
            "id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), "
            "name TEXT NOT NULL, schema_json TEXT NOT NULL, rationale TEXT NOT NULL, "
            "author TEXT NOT NULL, recorded_at TEXT NOT NULL, schema_sha256 TEXT NOT NULL, "
            "PRIMARY KEY(id,version))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS extraction_form_values ("
            "id TEXT PRIMARY KEY, form_id TEXT NOT NULL, form_version INTEGER NOT NULL, "
            "record_id TEXT NOT NULL REFERENCES review_records(id), values_json TEXT NOT NULL, "
            "reviewer TEXT NOT NULL, migrated_from TEXT, recorded_at TEXT NOT NULL, "
            "FOREIGN KEY(form_id,form_version) REFERENCES extraction_forms(id,version))"
        )

    @staticmethod
    def _validate_schema(fields: list[FieldDefinition]) -> None:
        require(0 < len(fields) <= 200, "Extraction form needs 1 to 200 fields")
        names = [field.name for field in fields]
        require(len(names) == len(set(names)), "Extraction form field names must be unique")

    def create(
        self,
        name: str,
        fields: list[FieldDefinition],
        author: str,
        *,
        rationale: str = "Initial extraction schema",
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        require(bool(name.strip()) and len(name) <= 300, "Extraction form name is required")
        require(bool(author.strip()) and len(author) <= 255, "Extraction form author is required")
        require(bool(rationale.strip()) and len(rationale) <= 5000,
                "Extraction form rationale is required")
        self._validate_schema(fields)
        schema = [_field_wire(field) for field in fields]
        encoded = canonical_json(schema)
        digest = sha256(encoded.encode())
        form_id = new_id()

        def persist(conn: Any) -> None:
            self._tables(conn)
            conn.execute(
                "INSERT INTO extraction_forms VALUES (?,?,?,?,?,?,?,?)",
                (
                    form_id, 1, name.strip(), encoded, rationale.strip(), author.strip(),
                    now_utc(), digest,
                ),
            )

        _, revision = self.store.mutate(
            "review.extraction_form_create",
            {"form_id": form_id, "version": 1, "schema_sha256": digest},
            persist,
            expected_revision=expected_revision,
        )
        return {
            "form_id": form_id,
            "version": 1,
            "schema_sha256": digest,
            "project_revision": revision,
        }

    def history(self, form_id: str) -> list[dict[str, Any]]:
        table = self.store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='extraction_forms'"
        ).fetchone()
        if table is None:
            return []
        rows = self.store.conn.execute(
            "SELECT * FROM extraction_forms WHERE id=? ORDER BY version", (form_id,)
        ).fetchall()
        return [
            {
                "form_id": row["id"],
                "version": row["version"],
                "name": row["name"],
                "fields": json.loads(row["schema_json"]),
                "rationale": row["rationale"],
                "author": row["author"],
                "recorded_at": row["recorded_at"],
                "schema_sha256": row["schema_sha256"],
            }
            for row in rows
        ]

    def _latest(self, form_id: str) -> dict[str, Any]:
        history = self.history(form_id)
        if not history:
            raise EvidenceError(
                "NOT_FOUND", "Extraction form not found", "Choose an existing form."
            )
        return history[-1]

    def record(
        self,
        form_id: str,
        record_id: str,
        values: Mapping[str, Mapping[str, Any]],
        reviewer: str,
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        latest = self._latest(form_id)
        require(bool(reviewer.strip()) and len(reviewer) <= 255, "Reviewer is required")
        fields = [_field_from_wire(field) for field in latest["fields"]]
        expected_names = {field.name for field in fields}
        require(set(values) == expected_names, "Extraction values must match form fields exactly")
        parsed: dict[str, Any] = {}
        for field in fields:
            raw = values[field.name]
            require(isinstance(raw, Mapping), f"Extraction value {field.name} must be an object")
            missingness = raw.get("missingness", "present")
            require(isinstance(missingness, str) and missingness in
                    {"present", "not_reported", "not_applicable", "not_extracted"},
                    "Invalid extraction missingness")
            typed_missingness = cast(Literal["present", "not_reported", "not_applicable",
                                             "not_extracted"], missingness)
            extracted = ExtractedValue(
                field=field.name,
                value=raw.get("value"),
                missingness=typed_missingness,
                unit=raw.get("unit") if isinstance(raw.get("unit"), str) else None,
                original_text=str(raw.get("original_text", "")),
            )
            parsed[field.name] = validate_field(field, extracted)
        value_id = new_id()

        def persist(conn: Any) -> None:
            self._tables(conn)
            require(
                conn.execute("SELECT 1 FROM review_records WHERE id=?", (record_id,)).fetchone()
                is not None,
                "Review record does not exist",
                "NOT_FOUND",
            )
            conn.execute(
                "INSERT INTO extraction_form_values VALUES (?,?,?,?,?,?,?,?)",
                (
                    value_id, form_id, latest["version"], record_id,
                    canonical_json(parsed), reviewer.strip(), None, now_utc(),
                ),
            )

        _, revision = self.store.mutate(
            "review.extraction_form_record",
            {
                "form_id": form_id,
                "form_version": latest["version"],
                "record_id": record_id,
                "value_id": value_id,
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "value_id": value_id,
            "form_id": form_id,
            "form_version": latest["version"],
            "values": parsed,
            "project_revision": revision,
        }

    def revise(
        self,
        form_id: str,
        fields: list[FieldDefinition],
        author: str,
        rationale: str,
        migration: Mapping[str, str | None],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        prior = self._latest(form_id)
        self._validate_schema(fields)
        require(bool(author.strip()), "Extraction form author is required")
        require(bool(rationale.strip()), "Extraction form revision rationale is required")
        old_fields = [_field_from_wire(item) for item in prior["fields"]]
        old_names = {field.name for field in old_fields}
        new_names = {field.name for field in fields}
        require(set(migration) == old_names,
                "Migration map must explicitly account for every prior field")
        targets = [target for target in migration.values() if target is not None]
        require(len(targets) == len(set(targets)), "Migration targets must be unique")
        require(set(targets).issubset(new_names), "Migration target is absent from new schema")
        new_by_name = {field.name: field for field in fields}
        version = int(prior["version"]) + 1
        schema = [_field_wire(field) for field in fields]
        encoded = canonical_json(schema)
        digest = sha256(encoded.encode())
        require(digest != prior["schema_sha256"], "Extraction schema is unchanged", "CONFLICT")
        prior_values = self.store.conn.execute(
            "SELECT * FROM extraction_form_values WHERE form_id=? AND form_version=? "
            "ORDER BY recorded_at,id",
            (form_id, prior["version"]),
        ).fetchall()
        migrated_rows: list[tuple[str, str, dict[str, Any], str]] = []
        for row in prior_values:
            original = json.loads(row["values_json"])
            mapped: dict[str, Any] = {}
            for old_name, target in migration.items():
                if target is None:
                    continue
                prior_value = original[old_name]
                extracted = ExtractedValue(
                    field=target,
                    value=prior_value["value"],
                    missingness=prior_value["missingness"],
                    unit=prior_value.get("unit"),
                    original_text=prior_value.get("original_text", ""),
                )
                mapped[target] = validate_field(new_by_name[target], extracted)
            for field in fields:
                if field.name in mapped:
                    continue
                require(
                    not field.required,
                    f"New required field {field.name} needs an explicit migration source",
                )
                mapped[field.name] = validate_field(
                    field,
                    ExtractedValue(
                        field=field.name,
                        value=None,
                        missingness="not_extracted",
                        unit=field.unit,
                    ),
                )
            migrated_rows.append((new_id(), row["record_id"], mapped, row["id"]))

        def persist(conn: Any) -> None:
            conn.execute(
                "INSERT INTO extraction_forms VALUES (?,?,?,?,?,?,?,?)",
                (
                    form_id, version, prior["name"], encoded, rationale.strip(),
                    author.strip(), now_utc(), digest,
                ),
            )
            for value_id, record_id, mapped, source_id in migrated_rows:
                conn.execute(
                    "INSERT INTO extraction_form_values VALUES (?,?,?,?,?,?,?,?)",
                    (
                        value_id, form_id, version, record_id, canonical_json(mapped),
                        "schema-migration", source_id, now_utc(),
                    ),
                )

        _, revision = self.store.mutate(
            "review.extraction_form_revise",
            {
                "form_id": form_id,
                "from_version": prior["version"],
                "to_version": version,
                "schema_sha256": digest,
                "migrated_records": len(migrated_rows),
            },
            persist,
            expected_revision=expected_revision,
        )
        return {
            "form_id": form_id,
            "version": version,
            "schema_sha256": digest,
            "migrated_records": len(migrated_rows),
            "project_revision": revision,
        }

    def values(self, form_id: str, version: int | None = None) -> list[dict[str, Any]]:
        if not self.history(form_id):
            raise EvidenceError(
                "NOT_FOUND", "Extraction form not found", "Choose an existing form."
            )
        if version is None:
            query = (
                "SELECT * FROM extraction_form_values WHERE form_id=? "
                "ORDER BY recorded_at,id"
            )
            params: tuple[Any, ...] = (form_id,)
        else:
            query = (
                "SELECT * FROM extraction_form_values WHERE form_id=? AND form_version=? "
                "ORDER BY recorded_at,id"
            )
            params = (form_id, version)
        return [
            {
                "value_id": row["id"],
                "form_id": row["form_id"],
                "form_version": row["form_version"],
                "record_id": row["record_id"],
                "values": json.loads(row["values_json"]),
                "reviewer": row["reviewer"],
                "migrated_from": row["migrated_from"],
                "recorded_at": row["recorded_at"],
            }
            for row in self.store.conn.execute(query, params)
        ]
