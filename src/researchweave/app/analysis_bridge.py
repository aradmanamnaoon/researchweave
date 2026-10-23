"""Desktop adapter that executes UI-selected methods through the production analysis facade."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from researchweave.analysis.facade import AnalysisFacade
from researchweave.ui.facade import UIFacade


class ProductionAnalysisBackend:
    """Bridge UI datasets into the headless scientific analysis store with explicit provenance."""

    METHOD = "analysis.statistics.describe"

    def __init__(self, ui: UIFacade, analysis: AnalysisFacade, import_root: Path) -> None:
        self._ui = ui
        self._analysis = analysis
        self._import_root = import_root.resolve()

    def methods(self) -> list[Mapping[str, Any]]:
        return [
            {
                "id": self.METHOD,
                "label": "Production descriptive statistics",
                "available": True,
                "arguments": {
                    "dataset_id": {"type": "string"},
                    "column": {"type": "string"},
                },
                "note": (
                    "Runs through the V2 scientific analysis facade with an immutable imported "
                    "dataset revision and explicit denominator/provenance metadata."
                ),
            }
        ]

    def _dataset(self, dataset_id: str) -> tuple[str, list[str], list[list[str]], str]:
        for project in self._ui.store.list_projects():
            for dataset in project.datasets:
                if dataset.id == dataset_id:
                    return project.id, list(dataset.columns), list(dataset.rows), dataset.origin
        raise ValueError("UI dataset was not found")

    def _stage_csv(self, columns: list[str], rows: list[list[str]]) -> tuple[str, str]:
        self._import_root.mkdir(parents=True, exist_ok=True)
        filename = f"ui-analysis-{uuid4()}.csv"
        path = self._import_root / filename
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
        return filename, hashlib.sha256(path.read_bytes()).hexdigest()

    def run(self, method: str, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        if method != self.METHOD:
            raise ValueError("Unsupported integrated analysis method")
        dataset_id = str(inputs.get("dataset_id", ""))
        column = str(inputs.get("column", ""))
        project_id, columns, rows, origin = self._dataset(dataset_id)
        if column not in columns:
            raise ValueError("Analysis column was not found")
        filename, staged_hash = self._stage_csv(columns, rows)
        staged_path = self._import_root / filename
        import_args = {"filename": filename}
        try:
            capability = self._analysis.issue_authorization("dataset.import", import_args)
            imported = self._analysis.execute(
                "dataset.import", import_args, {"host_capability": capability}
            )
        finally:
            staged_path.unlink(missing_ok=True)
        if imported.get("status") != "ok":
            raise ValueError("Scientific dataset import failed")
        imported_data = dict(imported["data"])
        arguments = {
            "dataset_id": imported_data["dataset_id"],
            "revision": imported_data["revision"],
            "column": column,
        }
        response = self._analysis.execute("statistics.describe", arguments, {})
        if response.get("status") != "ok":
            raise ValueError("Scientific descriptive analysis failed")
        data = dict(response["data"])
        estimates = {
            key: data.get(key)
            for key in (
                "n_total",
                "n_valid",
                "n_missing",
                "mean",
                "median",
                "sd_sample",
                "min",
                "max",
            )
        }
        uncertainty = {
            "standard_error_mean": data.get("standard_error_mean"),
            "mean_confidence_interval_95": data.get("mean_confidence_interval_95"),
        }
        diagnostics = {
            "q1": data.get("q1"),
            "q3": data.get("q3"),
            "iqr": data.get("iqr"),
            "median_absolute_deviation": data.get("median_absolute_deviation"),
            "skewness_bias_corrected": data.get("skewness_bias_corrected"),
            "excess_kurtosis_bias_corrected": data.get("excess_kurtosis_bias_corrected"),
            "ddof": data.get("ddof"),
        }
        return {
            "method": "descriptive statistics",
            "method_version": "researchweave-analysis-v2",
            "inputs": {
                "ui_project_id": project_id,
                "ui_dataset_id": dataset_id,
                "column": column,
                "analysis_dataset_id": imported_data["dataset_id"],
                "analysis_revision": imported_data["revision"],
            },
            "assumptions": [
                "Finite numeric values are summarized; missing/non-numeric values are excluded."
            ],
            "warnings": [],
            "estimates": estimates,
            "uncertainty": uncertainty,
            "diagnostics": diagnostics,
            "provenance": {
                "ui_dataset_origin": origin,
                "staged_csv_sha256": staged_hash,
                "analysis_source_sha256": imported_data["source_hash"],
                "analysis_response_provenance": response.get("provenance", []),
            },
        }
