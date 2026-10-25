"""Desktop adapter that executes UI-selected methods through the production analysis facade."""

from __future__ import annotations

import csv
import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from researchweave.analysis.errors import AnalysisError
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

    def _dataset(
        self, dataset_id: str, project_id: UUID | str | None = None
    ) -> tuple[str, list[str], list[list[str]], str]:
        projects = (
            [self._ui.store.open(str(project_id))]
            if project_id is not None
            else self._ui.store.list_projects()
        )
        for project in projects:
            for dataset in project.datasets:
                if dataset.id == dataset_id:
                    return project.id, list(dataset.columns), list(dataset.rows), dataset.origin
        raise ValueError("UI dataset was not found")

    def _variable_metadata(
        self, dataset_id: str, project_id: UUID | str | None = None
    ) -> list[dict[str, Any]]:
        projects = (
            [self._ui.store.open(str(project_id))]
            if project_id is not None
            else self._ui.store.list_projects()
        )
        for project in projects:
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

    @staticmethod
    def _metadata_updates(record: Mapping[str, Any]) -> dict[str, Any]:
        dtype_map = {
            "numeric": "number",
            "categorical": "text",
            "boolean": "boolean",
            "date": "date",
            "text": "text",
        }
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
        return updates

    def _apply_ui_variable_metadata(
        self,
        ui_dataset_id: str,
        analysis_dataset_id: str,
        revision: str,
        project_id: UUID,
    ) -> str:
        current_revision = revision
        for record in self._variable_metadata(ui_dataset_id, project_id):
            variable = str(record.get("variable", ""))
            current = self._analysis.store.load(analysis_dataset_id, current_revision)
            analysis_variable = next(
                (candidate for candidate in current.variables if candidate.name == variable), None
            )
            if analysis_variable is None:
                raise ValueError(f"Scientific variable metadata target was not found: {variable}")
            updates = self._metadata_updates(record)
            matches = True
            for key, expected in updates.items():
                actual = getattr(analysis_variable, key)
                if isinstance(actual, tuple):
                    expected = tuple(expected)
                if actual != expected:
                    matches = False
                    break
            if matches:
                continue
            metadata_request = OperationRequest(
                operation="dataset.variable",
                project_id=project_id,
                arguments={
                    "dataset_id": analysis_dataset_id,
                    "revision": current_revision,
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
            current_revision = str(metadata_result["data"]["revision"])
        return current_revision

    def _import_ui_dataset(
        self,
        dataset_id: str,
        project_id: UUID,
    ) -> tuple[dict[str, Any], str] | None:
        try:
            _project_id, columns, rows, _origin = self._dataset(dataset_id, project_id)
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
        imported_data["revision"] = self._apply_ui_variable_metadata(
            dataset_id,
            str(imported_data["dataset_id"]),
            str(imported_data["revision"]),
            project_id,
        )
        return imported_data, staged_hash

    def transform_for_project(
        self,
        dataset_id: str,
        kind: str,
        options: Mapping[str, Any],
        *,
        project_id: str,
    ) -> Mapping[str, Any]:
        """Create one immutable scientific revision for a scoped desktop dataset."""

        try:
            scope = UUID(project_id)
        except ValueError as exc:
            raise ValueError("Desktop project identifier is not a UUID") from exc
        # Resolve against the requested project before staging any local scientific write.
        project = self._ui.store.open(str(scope))
        ui_dataset = next((item for item in project.datasets if item.id == dataset_id), None)
        if ui_dataset is None:
            raise ValueError("UI dataset was not found in this project")
        if ui_dataset.analysis_dataset_id and ui_dataset.analysis_revision:
            try:
                anchored = self._analysis.store.load(
                    ui_dataset.analysis_dataset_id, ui_dataset.analysis_revision
                )
            except AnalysisError as exc:
                raise ValueError("Anchored scientific dataset revision is unavailable") from exc
            projected_rows = [
                ["" if row[column] is None else str(row[column]) for column in anchored.columns]
                for row in anchored.records
            ]
            if list(anchored.columns) != ui_dataset.columns or projected_rows != ui_dataset.rows:
                raise ValueError(
                    "Derived dataset projection does not match its anchored scientific revision"
                )
            current_revision = self._apply_ui_variable_metadata(
                dataset_id,
                anchored.dataset_id,
                anchored.revision,
                scope,
            )
            imported_data = {
                "dataset_id": anchored.dataset_id,
                "revision": current_revision,
            }
            base_dataset = self._analysis.store.load(anchored.dataset_id, current_revision)
            staged_hash: str | None = None
        else:
            imported = self._import_ui_dataset(dataset_id, scope)
            if imported is None:
                raise ValueError("UI dataset was not found in this project")
            imported_data, staged_hash = imported
            base_dataset = self._analysis.store.load(
                str(imported_data["dataset_id"]), str(imported_data["revision"])
            )
        arguments: dict[str, Any] = {
            "dataset_id": imported_data["dataset_id"],
            "revision": imported_data["revision"],
        }
        if kind == "select":
            column = str(options.get("column", ""))
            variable = next(
                (candidate for candidate in base_dataset.variables if candidate.name == column),
                None,
            )
            if variable is None:
                raise ValueError("Selection variable was not found in the scientific dataset")
            requested_allowed = list(options.get("allowed", []))
            observed = [row[column] for row in base_dataset.records if row.get(column) is not None]
            allowed: list[Any] = []
            for requested in requested_allowed:
                requested_text = str(requested).strip()
                exact = next(
                    (value for value in observed if str(value) == requested_text),
                    None,
                )
                if exact is not None:
                    allowed.append(exact)
                    continue
                if variable.dtype == "number":
                    try:
                        numeric = float(requested_text)
                    except (TypeError, ValueError, OverflowError) as exc:
                        raise ValueError(
                            "Numeric case-selection values must be finite numbers"
                        ) from exc
                    if not math.isfinite(numeric):
                        raise ValueError("Numeric case-selection values must be finite numbers")
                    equivalent = next(
                        (
                            value
                            for value in observed
                            if isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            and float(value) == numeric
                        ),
                        numeric,
                    )
                    allowed.append(equivalent)
                    continue
                if variable.dtype == "boolean":
                    boolean_values = {"true": True, "false": False}
                    try:
                        allowed.append(boolean_values[requested_text.casefold()])
                    except KeyError as exc:
                        raise ValueError(
                            "Boolean case-selection values must be true or false"
                        ) from exc
                    continue
                allowed.append(requested)
            arguments.update(
                {
                    "column": column,
                    "allowed": allowed,
                    "include_null": bool(options.get("include_null", False)),
                }
            )
            operation = "dataset.select"
        elif kind == "recode":
            column = str(options.get("column", ""))
            variable = next(
                (candidate for candidate in base_dataset.variables if candidate.name == column),
                None,
            )
            if variable is None:
                raise ValueError("Recode variable was not found in the scientific dataset")
            mapping = dict(options.get("mapping", {}))
            if variable.dtype == "number":
                try:
                    numeric_mapping: dict[str, float] = {}
                    for old, new in mapping.items():
                        old_number = float(old)
                        new_number = float(new)
                        if not math.isfinite(old_number) or not math.isfinite(new_number):
                            raise ValueError
                        numeric_mapping[str(old_number)] = new_number
                        if old_number.is_integer():
                            numeric_mapping[str(int(old_number))] = new_number
                    mapping = numeric_mapping
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(
                        "Numeric recode mappings must use finite numeric values"
                    ) from exc
            elif variable.dtype == "boolean":
                boolean_values = {"true": True, "false": False}
                try:
                    mapping = {
                        str(boolean_values[str(old).strip().casefold()]): boolean_values[
                            str(new).strip().casefold()
                        ]
                        for old, new in mapping.items()
                    }
                except KeyError as exc:
                    raise ValueError("Boolean recode mappings must use true or false") from exc
            arguments["spec"] = {
                "type": "recode",
                "column": column,
                "mapping": mapping,
            }
            operation = "dataset.transform"
        elif kind == "derive":
            spec: dict[str, Any] = {
                "type": "derive",
                "column": options.get("column"),
                "source": options.get("source"),
                "operation": options.get("operation"),
            }
            operand_column = options.get("operand_column")
            if isinstance(operand_column, str) and operand_column:
                spec["operand_column"] = operand_column
            else:
                spec["operand"] = options.get("operand")
            arguments["spec"] = spec
            operation = "dataset.transform"
        elif kind == "user_missing":
            arguments.update(
                {
                    "column": options.get("column"),
                    "missing_values": list(options.get("missing_values", [])),
                }
            )
            operation = "dataset.user_missing"
        else:
            raise ValueError("Unsupported Data View transformation")

        request = OperationRequest(
            operation=operation,
            project_id=scope,
            arguments=arguments,
            actor="desktop-user",
        )
        response = self._bus.dispatch(request, approval=self._bus.issue_approval(request))
        if response.get("status") != "ok":
            error = response.get("error")
            if isinstance(error, Mapping):
                code = str(error.get("code", "ANALYSIS_ERROR"))
                message = str(error.get("message", "Dataset transformation failed"))
                raise ValueError(f"{code}: {message}")
            raise ValueError("Dataset transformation failed")
        data = dict(response.get("data", {}))
        analysis_dataset_id = str(data.get("dataset_id", ""))
        analysis_revision = str(data.get("revision", ""))
        updated = self._analysis.store.load(analysis_dataset_id, analysis_revision)
        if updated.parent_revision != imported_data["revision"]:
            raise ValueError(
                "Transformed dataset lineage did not match the imported parent revision"
            )
        rows = [
            ["" if row[column] is None else str(row[column]) for column in updated.columns]
            for row in updated.records
        ]
        return {
            "columns": list(updated.columns),
            "rows": rows,
            "variables": [variable.__dict__ for variable in updated.variables],
            "analysis_dataset_id": updated.dataset_id,
            "analysis_revision": updated.revision,
            "analysis_parent_revision": updated.parent_revision,
            "analysis_operation": dict(updated.operation),
            "staged_csv_sha256": staged_hash,
            "analysis_source_sha256": updated.source_hash,
            "request_id": response.get("request_id"),
            "provenance": list(response.get("provenance", [])),
            "impact": dict(response.get("impact", {})),
        }

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
            if imported is None:
                raise ValueError("UI dataset was not found in this project")
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
        if not isinstance(assumptions, Sequence) or isinstance(
            assumptions, (str, bytes, bytearray)
        ):
            assumptions = [str(assumptions)]
        scientific_result = {
            "method",
            "dataset_revision",
            "n_total",
            "n_used",
            "n_excluded",
        } <= data.keys()
        result_warnings = data.pop("warnings", []) if scientific_result else []
        if not isinstance(result_warnings, Sequence) or isinstance(
            result_warnings, (str, bytes, bytearray)
        ):
            result_warnings = [str(result_warnings)]
        for warning in result_warnings:
            rendered = str(warning)
            if rendered not in warnings:
                warnings.append(rendered)
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
        ui_project_id, _columns, _rows, origin = self._dataset(dataset_id, project_id)
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
