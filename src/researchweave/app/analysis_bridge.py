"""Desktop adapter that executes UI-selected methods through the production analysis facade."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from researchweave.analysis.facade import AnalysisFacade
from researchweave.core import CommandBus, OperationRequest
from researchweave.ui.facade import UIFacade


class ProductionAnalysisBackend:
    """Bridge UI datasets into the headless scientific analysis store with explicit provenance."""

    METHOD = "analysis.statistics.describe"

    _METHOD_LABELS = {
        "statistics.frequency": "Frequencies",
        "statistics.grouped_describe": "Descriptive statistics by group",
        "statistics.test": "T test",
        "statistics.correlate": "Correlation",
        "statistics.correlation_matrix": "Correlation matrix",
        "statistics.contingency": "Crosstabs and chi-square",
        "statistics.rank": "Rank-sum test",
        "statistics.wilcoxon": "Wilcoxon signed-rank test",
        "statistics.kruskal": "Kruskal-Wallis test",
        "statistics.friedman": "Friedman test",
        "statistics.anova": "One-way ANOVA",
        "statistics.welch_anova": "Welch ANOVA",
        "statistics.tukey": "Tukey post-hoc comparisons",
        "statistics.factorial_anova": "Factorial ANOVA",
        "statistics.repeated_anova": "Repeated-measures ANOVA",
        "statistics.ancova": "ANCOVA",
        "statistics.model": "Linear regression",
        "statistics.logistic": "Logistic regression",
        "statistics.poisson": "Poisson regression",
        "statistics.negative_binomial": "Negative-binomial regression",
        "statistics.psychometric": "Scale reliability and psychometrics",
        "statistics.reliability_diagnostics": "Reliability diagnostics",
        "statistics.pca": "Principal component analysis",
        "statistics.efa": "Exploratory factor analysis",
        "statistics.survival": "Survival analysis",
        "statistics.logrank": "Log-rank test",
        "statistics.cox": "Cox regression",
        "statistics.gee": "Generalized estimating equations",
        "statistics.mixed_effects": "Mixed-effects model",
        "statistics.ordinal": "Ordinal regression",
        "statistics.survey_mean": "Complex-survey mean",
        "statistics.survey_proportions": "Complex-survey proportions",
    }

    def __init__(
        self,
        ui: UIFacade,
        analysis: AnalysisFacade,
        import_root: Path,
        bus: CommandBus,
    ) -> None:
        self._ui = ui
        self._analysis = analysis
        self._import_root = import_root.resolve()
        self._bus = bus

    def methods(self) -> list[Mapping[str, Any]]:
        methods: list[Mapping[str, Any]] = [
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
        for capability in self._bus.capabilities():
            if capability.get("domain") != "analysis":
                continue
            operation = str(capability.get("operation", ""))
            if not operation or operation == "statistics.describe":
                continue
            methods.append(
                {
                    "id": f"analysis.{operation}",
                    "label": self._METHOD_LABELS.get(
                        operation,
                        operation.removeprefix("statistics.").replace("_", " ").title(),
                    ),
                    "available": True,
                    "arguments_schema": dict(capability.get("arguments_schema", {})),
                    "effect": capability.get("effect", "read"),
                    "offline": bool(capability.get("offline", True)),
                    "note": (
                        "Runs the production scientific operation through the shared command bus. "
                        "Advanced arguments are explicit JSON and remain subject to the "
                        "operation schema."
                    ),
                }
            )
        return methods

    def _dataset(self, dataset_id: str) -> tuple[str, list[str], list[list[str]], str]:
        for project in self._ui.store.list_projects():
            for dataset in project.datasets:
                if dataset.id == dataset_id:
                    return project.id, list(dataset.columns), list(dataset.rows), dataset.origin
        raise ValueError("UI dataset was not found")

    def _variable_metadata(self, dataset_id: str) -> list[dict[str, Any]]:
        for project in self._ui.store.list_projects():
            if any(dataset.id == dataset_id for dataset in project.datasets):
                return [
                    dict(record)
                    for record in project.variable_metadata.values()
                    if record.get("dataset_id") == dataset_id
                ]
        return []

    def _stage_csv(self, columns: list[str], rows: list[list[str]]) -> tuple[str, str]:
        self._import_root.mkdir(parents=True, exist_ok=True)
        filename = f"ui-analysis-{uuid4()}.csv"
        path = self._import_root / filename
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
        return filename, hashlib.sha256(path.read_bytes()).hexdigest()

    def _import_ui_dataset(
        self,
        dataset_id: str,
        project_id: UUID,
    ) -> tuple[dict[str, Any], str] | None:
        try:
            _project_id, columns, rows, _origin = self._dataset(dataset_id)
        except ValueError:
            return None
        filename, staged_hash = self._stage_csv(columns, rows)
        staged_path = self._import_root / filename
        import_request = OperationRequest(
            operation="dataset.import",
            project_id=project_id,
            arguments={"filename": filename},
            actor="desktop-user",
        )
        try:
            imported = self._bus.dispatch(
                import_request,
                approval=self._bus.issue_approval(import_request),
            )
        finally:
            staged_path.unlink(missing_ok=True)
        if imported.get("status") != "ok":
            raise ValueError("Scientific dataset import failed")
        imported_data = dict(imported["data"])
        dtype_map = {
            "numeric": "number",
            "categorical": "text",
            "boolean": "boolean",
            "date": "date",
            "text": "text",
        }
        for record in self._variable_metadata(dataset_id):
            variable = str(record.get("variable", ""))
            variable_type = str(record.get("type", "text"))
            updates: dict[str, Any] = {
                "dtype": dtype_map.get(variable_type, "text"),
                "units": str(record.get("units", "")),
                "missing_values": [str(value) for value in record.get("missing_codes", [])],
            }
            if variable_type == "categorical":
                updates["scale"] = "nominal"
                updates["category_order"] = [str(value) for value in record.get("levels", [])]
            description = str(record.get("description", "")).strip()
            if description:
                updates["label"] = description
            metadata_request = OperationRequest(
                operation="dataset.variable",
                project_id=project_id,
                arguments={
                    "dataset_id": imported_data["dataset_id"],
                    "revision": imported_data["revision"],
                    "column": variable,
                    "updates": updates,
                },
                actor="desktop-user",
            )
            metadata_result = self._bus.dispatch(
                metadata_request,
                approval=self._bus.issue_approval(metadata_request),
            )
            if metadata_result.get("status") != "ok":
                raise ValueError(f"Scientific variable metadata import failed for {variable}")
            imported_data["revision"] = metadata_result["data"]["revision"]
        return imported_data, staged_hash

    def _run_advanced(
        self,
        method: str,
        inputs: Mapping[str, Any],
        project_id: str,
    ) -> Mapping[str, Any]:
        operation = method.removeprefix("analysis.")
        capability = next(
            (
                item
                for item in self._bus.capabilities()
                if item.get("domain") == "analysis" and item.get("operation") == operation
            ),
            None,
        )
        if capability is None or method == operation:
            raise ValueError("Unsupported integrated analysis method")
        try:
            scope = UUID(project_id)
        except ValueError as exc:
            raise ValueError("Desktop project identifier is not a UUID") from exc
        prepared = dict(inputs)
        staged_hash = ""
        analysis_source_hash = ""
        dataset_id = prepared.get("dataset_id")
        if isinstance(dataset_id, str) and dataset_id:
            imported = self._import_ui_dataset(dataset_id, scope)
            if imported is not None:
                imported_data, staged_hash = imported
                analysis_source_hash = str(imported_data.get("source_hash", ""))
                prepared["dataset_id"] = imported_data["dataset_id"]
                prepared["revision"] = imported_data["revision"]
                nested = prepared.get("arguments")
                if operation in {"syntax.python", "syntax.r"} and isinstance(nested, Mapping):
                    target_arguments = dict(nested)
                    target_arguments["dataset_id"] = imported_data["dataset_id"]
                    target_arguments["revision"] = imported_data["revision"]
                    prepared["arguments"] = target_arguments
        operation_request = OperationRequest(
            operation=operation,
            project_id=scope,
            arguments=prepared,
            actor="desktop-user",
        )
        effect = self._bus.effect_for(operation)
        approval = None
        if effect != "read":
            approval = self._bus.issue_approval(operation_request)
        response = self._bus.dispatch(operation_request, approval=approval)
        if response.get("status") != "ok":
            error = response.get("error")
            if isinstance(error, Mapping):
                message = str(error.get("message", "Scientific analysis failed"))
                code = str(error.get("code", "ANALYSIS_ERROR"))
                raise ValueError(f"{code}: {message}")
            raise ValueError("Scientific analysis failed")
        data = dict(response.get("data", {}))
        warnings = [str(item) for item in response.get("warnings", [])]
        assumptions = data.pop("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = [str(assumptions)]
        return {
            "method": operation,
            "method_version": str(capability.get("version", "researchweave-analysis-v2")),
            "inputs": dict(inputs),
            "assumptions": [str(item) for item in assumptions],
            "warnings": warnings,
            "estimates": data,
            "uncertainty": {},
            "diagnostics": {
                "effect": effect,
                "artifacts": list(response.get("artifacts", [])),
                "impact": dict(response.get("impact", {})),
            },
            "provenance": {
                "request_id": response.get("request_id"),
                "events": list(response.get("provenance", [])),
                "staged_csv_sha256": staged_hash or None,
                "analysis_source_sha256": analysis_source_hash or None,
                "resolved_arguments": prepared,
            },
        }

    def run_for_project(
        self,
        method: str,
        inputs: Mapping[str, Any],
        *,
        project_id: str,
    ) -> Mapping[str, Any]:
        if method != self.METHOD:
            return self._run_advanced(method, inputs, project_id)
        dataset_id = str(inputs.get("dataset_id", ""))
        column = str(inputs.get("column", ""))
        ui_project_id, _columns, _rows, origin = self._dataset(dataset_id)
        try:
            scope = UUID(project_id)
        except ValueError as exc:
            raise ValueError("Desktop project identifier is not a UUID") from exc
        imported = self._import_ui_dataset(dataset_id, scope)
        if imported is None:
            raise ValueError("UI dataset was not found")
        imported_data, staged_hash = imported
        response = self._bus.dispatch(
            OperationRequest(
                operation="statistics.describe",
                project_id=scope,
                arguments={
                    "dataset_id": imported_data["dataset_id"],
                    "revision": imported_data["revision"],
                    "column": column,
                },
                actor="desktop-user",
            )
        )
        if response.get("status") != "ok":
            error = response.get("error")
            if isinstance(error, Mapping):
                raise ValueError(
                    str(error.get("message", "Scientific descriptive analysis failed"))
                )
            raise ValueError("Scientific descriptive analysis failed")
        data = dict(response["data"])
        return {
            "method": "descriptive statistics",
            "method_version": "researchweave-analysis-v2",
            "inputs": {
                "ui_project_id": ui_project_id,
                "ui_dataset_id": dataset_id,
                "column": column,
                "analysis_dataset_id": imported_data["dataset_id"],
                "analysis_revision": imported_data["revision"],
            },
            "assumptions": [
                "Finite numeric values are summarized; missing/non-numeric values are excluded."
            ],
            "warnings": [str(item) for item in response.get("warnings", [])],
            "estimates": {
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
            },
            "uncertainty": {
                "standard_error_mean": data.get("standard_error_mean"),
                "mean_confidence_interval_95": data.get("mean_confidence_interval_95"),
            },
            "diagnostics": {
                "q1": data.get("q1"),
                "q3": data.get("q3"),
                "iqr": data.get("iqr"),
                "median_absolute_deviation": data.get("median_absolute_deviation"),
                "skewness_bias_corrected": data.get("skewness_bias_corrected"),
                "excess_kurtosis_bias_corrected": data.get("excess_kurtosis_bias_corrected"),
                "ddof": data.get("ddof"),
            },
            "provenance": {
                "ui_dataset_origin": origin,
                "staged_csv_sha256": staged_hash,
                "analysis_source_sha256": imported_data["source_hash"],
                "analysis_response_provenance": response.get("provenance", []),
                "request_id": response.get("request_id"),
            },
        }

    def run(self, method: str, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        if method != self.METHOD:
            raise ValueError("Advanced analysis requires desktop project context")
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
