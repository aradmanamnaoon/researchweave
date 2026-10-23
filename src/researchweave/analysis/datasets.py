"""Immutable imported datasets, durable revision store and reviewed variables."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from .errors import AnalysisError, require
from .models import Dataset, Variable, canonical_json, digest, utc_now

MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 500_000
MAX_COLUMNS = 2000


def validate_dataset_identity(dataset_id: str, revision: str | None = None) -> None:
    """Identifiers are hex digests, never filesystem paths or user-supplied labels."""
    require(
        isinstance(dataset_id, str)
        and len(dataset_id) == 24
        and all(c in "0123456789abcdef" for c in dataset_id),
        "Invalid dataset ID; expected 24 lowercase hex characters",
    )
    if revision is not None:
        require(
            isinstance(revision, str)
            and len(revision) == 64
            and all(c in "0123456789abcdef" for c in revision),
            "Invalid revision; expected 64 lowercase hex characters",
        )


def expected_revision(dataset: Dataset) -> str:
    """Reconstruct content-derived dataset revisions from supported constructors."""
    record_list = list(dataset.records)
    variables = [v.__dict__ for v in dataset.variables]
    operation = dataset.operation
    if dataset.parent_revision is None:
        if operation.get("type") == "import_csv":
            payload = {
                "id": dataset.dataset_id,
                "source": dataset.source_hash,
                "rows": record_list,
                "variables": variables,
                "operation": operation,
            }
        elif operation.get("type") == "import_table":
            payload = {
                "id": dataset.dataset_id,
                "source": dataset.source_hash,
                "rows": record_list,
                "variables": variables,
                "operation": operation,
            }
        else:
            raise AnalysisError("INTEGRITY_FAILURE", "Unknown root revision constructor")
    elif operation.get("type") == "join":
        payload = {
            "columns": dataset.columns,
            "rows": record_list,
            "variables": variables,
            "operation": operation,
        }
    elif operation.get("type") == "survey_indicator":
        payload = {"operation": operation, "records": record_list}
    else:
        payload = {
            "parent": dataset.parent_revision,
            "records": record_list,
            "variables": variables,
            "operation": operation,
        }
    return digest(payload)


def import_csv(
    path: Path,
    *,
    encoding: str = "utf-8-sig",
    delimiter: str | None = None,
    decimal: str = ".",
    missing: tuple[str, ...] = ("",),
    dataset_id: str | None = None,
) -> Dataset:
    require(decimal in (".", ","), "decimal must be dot or comma")
    require(path.is_file(), "Import source does not exist", "NOT_FOUND")
    require(
        path.stat().st_size <= MAX_BYTES, "Source exceeds configured byte budget", "RESOURCE_LIMIT"
    )
    content = path.read_bytes()
    try:
        text = content.decode(encoding)
    except (UnicodeError, LookupError) as exc:
        raise AnalysisError(
            "INVALID_INPUT", "Text decoding failed; select another encoding"
        ) from exc
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:16_384], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    require(len(delimiter) == 1, "Delimiter must contain exactly one character")
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, restkey="__overflow__")
    require(bool(reader.fieldnames), "CSV must include header")
    columns = tuple(reader.fieldnames or ())
    require(
        len(columns) == len(set(columns)) and all(columns), "Duplicate/empty columns prohibited"
    )
    require("__overflow__" not in columns, "Reserved column name used")
    require(len(columns) <= MAX_COLUMNS, "Too many columns", "RESOURCE_LIMIT")
    rows: list[dict[str, Any]] = []
    for row in reader:
        require(len(rows) < MAX_ROWS, "Too many rows", "RESOURCE_LIMIT")
        require(
            "__overflow__" not in row and all(k in columns for k in row),
            "CSV row has extra columns",
            "SCHEMA_MISMATCH",
        )
        require(
            all(value is not None for value in row.values()),
            "CSV row has missing fields",
            "SCHEMA_MISMATCH",
        )
        rows.append({column: None if row[column] in missing else row[column] for column in columns})
    variables = tuple(Variable(name=c, missing_values=missing) for c in columns)
    source_hash = hashlib.sha256(content).hexdigest()
    identifier = dataset_id or digest({"source_hash": source_hash})[:24]
    validate_dataset_identity(identifier)
    op = {
        "type": "import_csv",
        "encoding": encoding,
        "delimiter": delimiter,
        "decimal": decimal,
        "missing": list(missing),
    }
    revision = digest(
        {
            "id": identifier,
            "source": source_hash,
            "rows": rows,
            "variables": [v.__dict__ for v in variables],
            "operation": op,
        }
    )
    return Dataset(
        identifier, revision, None, source_hash, utc_now(), columns, variables, tuple(rows), op
    )


def import_table(
    path: Path, *, format: str | None = None, sheet: int | str = 0, dataset_id: str | None = None
) -> Dataset:
    """Import nonexecuting structured formats through opt-in vetted readers."""
    import pandas as pd

    require(path.is_file(), "Import source does not exist", "NOT_FOUND")
    require(path.stat().st_size <= MAX_BYTES, "Source exceeds byte budget", "RESOURCE_LIMIT")
    kind = (format or path.suffix.lower().lstrip(".")).lower()
    if kind in ("csv", "tsv"):
        return import_csv(path, delimiter="\t" if kind == "tsv" else None, dataset_id=dataset_id)
    readers = {
        "xlsx": lambda: pd.read_excel(path, sheet_name=sheet),
        "ods": lambda: pd.read_excel(path, sheet_name=sheet, engine="odf"),
        "parquet": lambda: pd.read_parquet(path),
        "dta": lambda: pd.read_stata(path, convert_categoricals=False),
        "xpt": lambda: pd.read_sas(path, format="xport"),
        "sav": lambda: pd.read_spss(path, convert_categoricals=False),
        "zsav": lambda: pd.read_spss(path, convert_categoricals=False),
        "json": lambda: pd.read_json(path),
        "jsonl": lambda: pd.read_json(path, lines=True),
    }
    require(kind in readers, f"Unsupported import format: {kind}", "UNSUPPORTED_FORMAT")
    try:
        frame = readers[kind]()
    except ImportError as exc:
        raise AnalysisError("DEPENDENCY_MISSING", f"Reader for {kind} is not installed") from exc
    except (ValueError, TypeError, OSError) as exc:
        raise AnalysisError("INVALID_INPUT", f"Could not parse {kind} source") from exc
    require(
        len(frame) <= MAX_ROWS and len(frame.columns) <= MAX_COLUMNS,
        "Parsed table exceeds row/column budget",
        "RESOURCE_LIMIT",
    )
    names = tuple(str(c) for c in frame.columns)
    require(len(set(names)) == len(names), "Duplicate columns prohibited")
    rows = json.loads(frame.to_json(orient="records", date_format="iso"))
    labels = tuple(
        Variable(
            name=c, dtype="number" if pd.api.types.is_numeric_dtype(frame.iloc[:, i]) else "text"
        )
        for i, c in enumerate(names)
    )
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    identifier = dataset_id or digest({"source": source_hash})[:24]
    validate_dataset_identity(identifier)
    operation = {"type": "import_table", "format": kind, "sheet": sheet}
    revision = digest(
        {
            "id": identifier,
            "source": source_hash,
            "rows": rows,
            "variables": [v.__dict__ for v in labels],
            "operation": operation,
        }
    )
    return Dataset(
        identifier, revision, None, source_hash, utc_now(), names, labels, tuple(rows), operation
    )


def revise(
    dataset: Dataset,
    records: list[dict[str, Any]],
    operation: dict[str, Any],
    variables: tuple[Variable, ...] | None = None,
) -> Dataset:
    metadata = variables or dataset.variables
    require(len(records) <= MAX_ROWS, "Too many transformed rows", "RESOURCE_LIMIT")
    require(
        all(set(row) == set(dataset.columns) for row in records),
        "Transformed schema mismatch",
        "SCHEMA_MISMATCH",
    )
    identity = digest(
        {
            "parent": dataset.revision,
            "records": records,
            "variables": [v.__dict__ for v in metadata],
            "operation": operation,
        }
    )
    return Dataset(
        dataset.dataset_id,
        identity,
        dataset.revision,
        dataset.source_hash,
        utc_now(),
        dataset.columns,
        metadata,
        tuple(records),
        operation,
    )


def revise_schema(
    dataset: Dataset,
    records: list[dict[str, Any]],
    columns: tuple[str, ...],
    variables: tuple[Variable, ...],
    operation: dict[str, Any],
) -> Dataset:
    """Create an immutable revision whose schema intentionally changes."""

    require(len(records) <= MAX_ROWS, "Too many transformed rows", "RESOURCE_LIMIT")
    require(bool(columns) and len(set(columns)) == len(columns), "Invalid transformed columns")
    require(tuple(variable.name for variable in variables) == columns, "Variable schema mismatch")
    require(
        all(set(row) == set(columns) for row in records),
        "Transformed schema mismatch",
        "SCHEMA_MISMATCH",
    )
    identity = digest(
        {
            "parent": dataset.revision,
            "columns": columns,
            "records": records,
            "variables": [v.__dict__ for v in variables],
            "operation": operation,
        }
    )
    return Dataset(
        dataset.dataset_id,
        identity,
        dataset.revision,
        dataset.source_hash,
        utc_now(),
        columns,
        variables,
        tuple(records),
        operation,
    )


def set_variable(dataset: Dataset, name: str, **updates: Any) -> Dataset:
    require(name in dataset.columns, "Unknown variable", "NOT_FOUND")
    allowed = {"label", "units", "scale", "value_labels", "missing_values", "private", "dtype"}
    require(set(updates) <= allowed, "Unsupported metadata property")
    metadata = tuple(
        replace(variable, **updates) if variable.name == name else variable
        for variable in dataset.variables
    )
    return revise(
        dataset,
        list(dataset.records),
        {"type": "variable_edit", "name": name, "changes": updates},
        metadata,
    )


def page(dataset: Dataset, *, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    require(offset >= 0 and 1 <= limit <= 1000, "Invalid page range")
    return {
        "total": len(dataset.records),
        "offset": offset,
        "limit": limit,
        "rows": list(dataset.records[offset : offset + limit]),
        "revision": dataset.revision,
    }


class DatasetStore:
    def __init__(self, directory: Path):
        self.root = directory.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, dataset: Dataset) -> Path:
        validate_dataset_identity(dataset.dataset_id, dataset.revision)
        require(
            expected_revision(dataset) == dataset.revision,
            "Dataset revision checksum does not match content",
            "INTEGRITY_FAILURE",
        )
        directory = self.root / dataset.dataset_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{dataset.revision}.json"
        record = dataset.as_json()
        content = canonical_json(
            {"schema_version": 2, "dataset": record, "content_sha256": digest(record)}
        )
        if target.exists():
            require(
                target.read_bytes() == content, "Existing revision differs", "INTEGRITY_FAILURE"
            )
            return target
        temporary = directory / f".{dataset.revision}.{os.getpid()}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def load(self, dataset_id: str, revision: str) -> Dataset:
        validate_dataset_identity(dataset_id, revision)
        path = self.root / dataset_id / f"{revision}.json"
        require(path.is_file(), "Revision not found", "NOT_FOUND")
        require(
            path.stat().st_size <= MAX_BYTES * 4,
            "Stored dataset exceeds read budget",
            "RESOURCE_LIMIT",
        )
        try:
            envelope = json.loads(path.read_bytes())
        except (ValueError, UnicodeError) as exc:
            raise AnalysisError("INTEGRITY_FAILURE", "Saved revision is not valid JSON") from exc
        require(
            envelope.get("schema_version") == 2 and isinstance(envelope.get("dataset"), dict),
            "Unsupported or unauthenticated dataset snapshot",
            "INTEGRITY_FAILURE",
        )
        obj = envelope["dataset"]
        require(
            digest(obj) == envelope.get("content_sha256"),
            "Saved dataset checksum mismatch",
            "INTEGRITY_FAILURE",
        )
        require(
            obj["revision"] == revision and obj["dataset_id"] == dataset_id,
            "Revision identity mismatch",
            "INTEGRITY_FAILURE",
        )
        result = Dataset(
            dataset_id,
            revision,
            obj["parent_revision"],
            obj["source_hash"],
            obj["created_at"],
            tuple(obj["columns"]),
            tuple(
                Variable(**{**v, "missing_values": tuple(v["missing_values"])})
                for v in obj["variables"]
            ),
            tuple(obj["records"]),
            obj["operation"],
        )
        require(
            expected_revision(result) == revision,
            "Revision does not match restored dataset",
            "INTEGRITY_FAILURE",
        )
        return result
