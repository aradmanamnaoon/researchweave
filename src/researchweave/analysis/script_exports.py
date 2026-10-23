"""Portable syntax exports with explicit source revisions and dependency checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .errors import require
from .models import Dataset, canonical_json, digest, finite_number, runtime_versions
from .schemas import OPERATION_SCHEMAS

NON_REPLAYABLE_OPERATIONS = frozenset(
    {
        "dataset.import",
        "dataset.scan_parquet",
        "dataset.export_csv",
        "dataset.transform",
        "dataset.variable",
        "dataset.select",
        "dataset.user_missing",
        "dataset.complete_case",
        "dataset.simple_impute",
        "dataset.multiple_impute",
        "dataset.join",
        "dataset.aggregate",
        "dataset.pivot_longer",
        "dataset.pivot_wider",
        "qualitative.create",
        "qualitative.add_code",
        "qualitative.update_code",
        "qualitative.delete_code",
        "qualitative.add_transcript",
        "qualitative.annotate",
        "qualitative.add_memo",
        "qualitative.review_annotation",
        "mixed.joint_display_sensitive",
        "plot.render",
        "runtime.python",
        "runtime.r",
    }
)

# Every other registered facade operation is a deterministic read. Keeping this
# definition tied to the schema registry prevents syntax support from silently
# falling behind as scientific methods are added.
READ_OPERATIONS = frozenset(OPERATION_SCHEMAS) - NON_REPLAYABLE_OPERATIONS


@dataclass(frozen=True)
class SyntaxExport:
    language: str
    operation: str
    dataset_revision: str | None
    dataset_id: str | None
    arguments_sha256: str
    dependencies: dict[str, str]
    source: str
    source_sha256: str
    invocation: str
    limitations: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def export_python_script(
    operation: str, arguments: dict[str, Any], dataset: Dataset | None = None
) -> SyntaxExport:
    """Generate deterministic script using installed ResearchWeave kernels."""
    require(operation in READ_OPERATIONS, "Syntax replay unsupported", "UNSUPPORTED")
    schema = OPERATION_SCHEMAS[operation]
    requires_dataset = {"dataset_id", "revision"} <= set(schema.required)
    if requires_dataset:
        require(dataset is not None, "Dataset revision required for syntax replay")
        require(
            arguments.get("dataset_id") == dataset.dataset_id
            and arguments.get("revision") == dataset.revision,
            "Export parameters do not identify exact source revision",
            "INTEGRITY_FAILURE",
        )
    else:
        require(
            dataset is None,
            "Dataset must be omitted for an operation without dataset identity",
            "SCHEMA_MISMATCH",
        )
    schema.validate(arguments)
    require(len(canonical_json(arguments)) <= 100_000, "Arguments exceed source budget")
    versions = runtime_versions()
    dependencies = {
        key: val
        for key, val in versions.items()
        if key in {"python", "numpy", "scipy", "statsmodels"}
    }
    args_literal = json.dumps(json.dumps(arguments, ensure_ascii=True, sort_keys=True))
    versions_literal = json.dumps(json.dumps(dependencies, ensure_ascii=True, sort_keys=True))
    operation_literal = json.dumps(operation)
    source = """#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from researchweave.analysis import build_analysis_facade
from researchweave.analysis.models import runtime_versions

EXPECTED = json.loads(__VERSIONS__)
ARGS = json.loads(__ARGS__)
OPERATION = __OP__

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python replay.py STORE_ROOT")
    installed = runtime_versions()
    for package, expected in EXPECTED.items():
        if installed.get(package) != expected:
            raise SystemExit("Dependency mismatch: " + package)
    facade = build_analysis_facade(Path(sys.argv[1]))
    outcome = facade.execute(OPERATION, ARGS, {"request_id": "replay"})
    if outcome["status"] != "ok":
        raise SystemExit("Replay failed: " + str(outcome["error"]))
    print(json.dumps(outcome["data"], sort_keys=True, allow_nan=False))

if __name__ == "__main__":
    main()
"""
    source = (
        source.replace("__VERSIONS__", versions_literal)
        .replace("__ARGS__", args_literal)
        .replace("__OP__", operation_literal)
    )
    return SyntaxExport(
        "python",
        operation,
        dataset.revision if dataset is not None else None,
        dataset.dataset_id if dataset is not None else None,
        digest(arguments),
        dependencies,
        source,
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "python replay.py STORE_ROOT",
        (
            "Requires compatible local ResearchWeave version and exact dependencies",
            *(
                ("Requires original immutable dataset revision in local store",)
                if dataset is not None
                else ()
            ),
        ),
    )


def export_r_script(operation: str, arguments: dict[str, Any], dataset: Dataset) -> SyntaxExport:
    """Restricted scalar descriptive R syntax; never imply unverified parity."""
    require(
        operation == "statistics.describe", "R export unavailable for this method", "UNSUPPORTED"
    )
    require(
        arguments.get("dataset_id") == dataset.dataset_id
        and arguments.get("revision") == dataset.revision,
        "Dataset identity mismatch",
        "INTEGRITY_FAILURE",
    )
    column = arguments.get("column")
    require(column in dataset.columns, "Unknown column")
    values = [finite_number(row[column]) for row in dataset.records if row[column] is not None]
    require(len(values) >= 2, "At least two numeric observations required")
    literals = ", ".join(format(value, ".17g") for value in values)
    source = (
        "# ResearchWeave descriptive calculation (complete observed values only)\n"
        f"# source_revision: {dataset.revision}\n"
        f"# data_sha256: {digest({'values': values})}\n"
        f"v <- c({literals})\n"
        "stopifnot(length(v) >= 2, all(is.finite(v)))\n"
        "cat(sprintf('%.17g\\n', mean(v)))\n"
        "cat(sprintf('%.17g\\n', median(v)))\n"
        "cat(sprintf('%.17g\\n', sd(v)))\n"
    )
    return SyntaxExport(
        "r",
        operation,
        dataset.revision,
        dataset.dataset_id,
        digest(arguments),
        {"R": "optional and unverified"},
        source,
        hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "Rscript descriptive.R",
        (
            "Snapshot includes complete observed numerical values only",
            "R numerical equivalence has not been validated in this environment",
        ),
    )


def save_syntax(export: SyntaxExport, destination: Path) -> dict[str, Any]:
    require(destination.parent.is_dir(), "Export folder missing", "NOT_FOUND")
    expected_suffix = ".py" if export.language == "python" else ".r"
    require(destination.suffix.lower() == expected_suffix, "Incorrect script suffix")
    require(not destination.exists(), "Destination exists", "CONFLICT")
    payload = export.source.encode("utf-8")
    require(
        hashlib.sha256(payload).hexdigest() == export.source_sha256,
        "Export hash mismatch",
        "INTEGRITY_FAILURE",
    )
    destination.write_bytes(payload)
    return {
        "path": str(destination),
        "sha256": export.source_sha256,
        "bytes": len(payload),
        "language": export.language,
    }
