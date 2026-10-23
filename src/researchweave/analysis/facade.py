"""Typed command boundary for the desktop host and agent tool dispatcher."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .data_ops import case_selection, frequency_weighted_mean, missingness, recode_missing
from .datasets import DatasetStore, import_csv, import_table, page, set_variable
from .diagnostics import ols_diagnostics, variance_inflation
from .errors import AnalysisError, require
from .generalized import logistic_regression, poisson_regression
from .inference import (
    bootstrap_mean,
    contingency,
    exact_permutation_mean_difference,
    independent_rank_test,
    one_way_anova,
)
from .modeling import adjust_pvalues, linear_regression, pooled_effects
from .models import Dataset, digest
from .multivariate import hierarchical_clusters, kmeans_clusters, principal_components
from .plots import render_plot
from .power import two_sample_t_power, two_sample_t_required
from .runtime import run_script
from .scale_scoring import ScaleDefinition, item_total_diagnostics, score_scale
from .statistics import correlation, describe, reliability, t_test
from .time_series import adf_stationarity, causal_features, parse_chronology
from .transformations import transform


class AnalysisFacade:
    def __init__(self, directory: Path):
        self.store = DatasetStore(directory)

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        names = {
            "dataset.import": "local-write",
            "dataset.inspect": "read",
            "dataset.page": "read",
            "dataset.transform": "local-write",
            "dataset.variable": "local-write",
            "dataset.missingness": "read",
            "dataset.select": "local-write",
            "dataset.user_missing": "local-write",
            "statistics.weighted_mean": "read",
            "statistics.describe": "read",
            "statistics.test": "read",
            "statistics.correlate": "read",
            "statistics.psychometric": "read",
            "statistics.model": "read",
            "statistics.logistic": "read",
            "statistics.poisson": "read",
            "statistics.meta": "read",
            "statistics.adjust": "read",
            "statistics.contingency": "read",
            "statistics.rank": "read",
            "statistics.anova": "read",
            "statistics.bootstrap": "read",
            "statistics.permutation": "read",
            "statistics.pca": "read",
            "statistics.kmeans": "read",
            "statistics.hierarchical": "read",
            "statistics.power": "read",
            "statistics.required_n": "read",
            "statistics.diagnostics": "read",
            "statistics.vif": "read",
            "statistics.score_scale": "read",
            "statistics.item_total": "read",
            "statistics.time_features": "read",
            "statistics.adf": "read",
            "plot.render": "local-write",
            "runtime.python": "code-execution",
            "runtime.r": "code-execution",
        }
        return [
            {
                "operation": operation,
                "version": "1.0.0",
                "effect": effect,
                "offline": True,
                "risk": effect,
                "arguments_schema": {"type": "object"},
                "result_schema": {"type": "object"},
                "requires_permission": "local-data-write"
                if effect != "read"
                else "local-data-read",
            }
            for operation, effect in names.items()
        ]

    def health(self) -> Mapping[str, Any]:
        return {
            "status": "ok",
            "schema_version": 1,
            "offline": True,
            "capabilities": len(self.capability_manifest()),
        }

    def preview(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        known = {entry["operation"]: entry for entry in self.capability_manifest()}
        require(operation in known, "Unknown operation", "NOT_FOUND")
        return {
            "operation": operation,
            "effect": known[operation]["effect"],
            "argument_hash": digest(dict(arguments)),
            "network_hosts": [],
            "local_path": "host-managed",
            "requires_host_authorization": True,
        }

    def _dataset(self, arguments: Mapping[str, Any]) -> Dataset:
        return self.store.load(str(arguments["dataset_id"]), str(arguments["revision"]))

    def execute(
        self, operation: str, arguments: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        request_id = str(context.get("request_id", ""))
        try:
            return self._execute(operation, arguments, context, request_id)
        except AnalysisError as exc:
            return {
                "request_id": request_id,
                "status": "failed",
                "data": {},
                "artifacts": [],
                "warnings": [],
                "error": {"code": exc.code, "message": exc.message, "recovery": exc.recovery},
                "provenance": [],
                "impact": {"local_writes": [], "network_hosts": []},
            }
        except (KeyError, TypeError, ValueError):
            return {
                "request_id": request_id,
                "status": "failed",
                "data": {},
                "artifacts": [],
                "warnings": [],
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "Malformed operation arguments",
                    "recovery": "Check operation schema",
                },
                "provenance": [],
                "impact": {"local_writes": [], "network_hosts": []},
            }

    def _execute(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        context: Mapping[str, Any],
        request_id: str,
    ) -> Mapping[str, Any]:
        known = {entry["operation"]: entry for entry in self.capability_manifest()}
        require(operation in known, "Unknown operation", "NOT_FOUND")
        effect = known[operation]["effect"]
        if effect != "read":
            require(
                context.get("host_authorized") is True,
                "Host authorization required for persistent changes",
                "PERMISSION_DENIED",
            )
        if operation == "statistics.meta":
            data = pooled_effects(
                list(arguments["studies"]), model=str(arguments.get("model", "fixed"))
            )
        elif operation == "statistics.adjust":
            data = {
                "adjusted": adjust_pvalues(
                    list(arguments["pvalues"]), method=str(arguments.get("method", "holm"))
                )
            }
        elif operation == "statistics.bootstrap":
            from dataclasses import asdict

            data = asdict(
                bootstrap_mean(
                    list(arguments["values"]),
                    seed=int(arguments["seed"]),
                    iterations=int(arguments.get("iterations", 2000)),
                )
            )
        elif operation == "statistics.permutation":
            data = exact_permutation_mean_difference(
                list(arguments["first"]),
                list(arguments["second"]),
                alternative=str(arguments.get("alternative", "two-sided")),
            )
        elif operation in ("statistics.power", "statistics.required_n"):
            from dataclasses import asdict

            options = dict(arguments)
            if operation == "statistics.power":
                data = asdict(two_sample_t_power(**options))
            else:
                data = asdict(two_sample_t_required(**options))
        elif operation in ("runtime.python", "runtime.r"):
            data = run_script(
                str(arguments["source"]),
                language="python" if operation.endswith("python") else "r",
                approved=context.get("host_authorized") is True,
                timeout_seconds=int(arguments.get("timeout_seconds", 10)),
            )
        elif operation == "dataset.import":
            # Trusted host must inject a fixed import root. Do not accept an arbitrary AI path.
            allowed = context.get("trusted_import_root")
            require(
                isinstance(allowed, Path), "Trusted import root not supplied", "PERMISSION_DENIED"
            )
            path = (allowed / str(arguments["filename"])).resolve()
            require(
                path.is_relative_to(allowed.resolve()) and path.is_file(),
                "Import must be under host-approved root",
                "PERMISSION_DENIED",
            )
            if path.suffix.lower() in (".csv", ".tsv"):
                obj = import_csv(path, **dict(arguments.get("options", {})))
            else:
                obj = import_table(path, **dict(arguments.get("options", {})))
            self.store.save(obj)
            data = {
                "dataset_id": obj.dataset_id,
                "revision": obj.revision,
                "n": len(obj.records),
                "columns": list(obj.columns),
                "source_hash": obj.source_hash,
            }
        elif operation in ("dataset.inspect", "dataset.page"):
            obj = self._dataset(arguments)
            data = page(
                obj, offset=int(arguments.get("offset", 0)), limit=int(arguments.get("limit", 100))
            )
            if operation == "dataset.inspect":
                data["variables"] = [v.__dict__ for v in obj.variables]
                data["source_hash"] = obj.source_hash
        elif operation in (
            "dataset.transform",
            "dataset.variable",
            "dataset.select",
            "dataset.user_missing",
        ):
            obj = self._dataset(arguments)
            if operation == "dataset.transform":
                updated = transform(obj, dict(arguments["spec"]))
            elif operation == "dataset.variable":
                updated = set_variable(obj, str(arguments["column"]), **dict(arguments["updates"]))
            elif operation == "dataset.select":
                updated = case_selection(
                    obj,
                    str(arguments["column"]),
                    list(arguments["allowed"]),
                    include_null=bool(arguments.get("include_null", False)),
                )
            else:
                updated = recode_missing(
                    obj, str(arguments["column"]), list(arguments["missing_values"])
                )
            self.store.save(updated)
            data = {
                "dataset_id": updated.dataset_id,
                "revision": updated.revision,
                "parent_revision": obj.revision,
                "n": len(updated.records),
            }
        else:
            obj = self._dataset(arguments)
            if operation == "statistics.describe":
                data = describe(obj, str(arguments["column"]))
            elif operation == "dataset.missingness":
                data = missingness(obj, by=arguments.get("by"))
            elif operation == "statistics.weighted_mean":
                data = frequency_weighted_mean(
                    obj, str(arguments["column"]), str(arguments["weight"])
                )
            elif operation == "statistics.test":
                data = t_test(
                    obj, str(arguments["outcome"]), **dict(arguments.get("options", {}))
                ).as_json()
            elif operation == "statistics.correlate":
                data = correlation(
                    obj,
                    str(arguments["x"]),
                    str(arguments["y"]),
                    str(arguments.get("method", "pearson")),
                ).as_json()
            elif operation == "statistics.psychometric":
                data = reliability(
                    obj, list(arguments["columns"]), **dict(arguments.get("options", {}))
                ).as_json()
            elif operation == "statistics.model":
                data = linear_regression(
                    obj,
                    str(arguments["outcome"]),
                    list(arguments["predictors"]),
                    robust=str(arguments.get("covariance", "nonrobust")),
                ).as_json()
            elif operation == "statistics.logistic":
                data = logistic_regression(
                    obj,
                    str(arguments["outcome"]),
                    list(arguments["predictors"]),
                    max_iterations=int(arguments.get("max_iterations", 200)),
                ).as_json()
            elif operation == "statistics.poisson":
                data = poisson_regression(
                    obj,
                    str(arguments["outcome"]),
                    list(arguments["predictors"]),
                    offset=arguments.get("offset"),
                ).as_json()
            elif operation == "statistics.contingency":
                data = contingency(obj, str(arguments["first"]), str(arguments["second"]))
            elif operation == "statistics.rank":
                levels = tuple(arguments["levels"])
                require(len(levels) == 2, "Exactly two rank-test groups required")
                data = independent_rank_test(
                    obj, str(arguments["outcome"]), str(arguments["group"]), levels
                ).as_json()
            elif operation == "statistics.anova":
                data = one_way_anova(
                    obj,
                    str(arguments["outcome"]),
                    str(arguments["group"]),
                    levels=list(arguments["levels"]),
                ).as_json()
            elif operation == "statistics.pca":
                data = principal_components(
                    obj,
                    list(arguments["columns"]),
                    n_components=int(arguments.get("n_components", 2)),
                    standardize=bool(arguments.get("standardize", True)),
                )
            elif operation == "statistics.kmeans":
                data = kmeans_clusters(
                    obj,
                    list(arguments["columns"]),
                    k=int(arguments["k"]),
                    seed=int(arguments.get("seed", 0)),
                )
            elif operation == "statistics.hierarchical":
                data = hierarchical_clusters(
                    obj,
                    list(arguments["columns"]),
                    k=int(arguments["k"]),
                    linkage=str(arguments.get("linkage", "ward")),
                )
            elif operation == "statistics.diagnostics":
                data = ols_diagnostics(
                    obj, str(arguments["outcome"]), list(arguments["predictors"])
                )
            elif operation == "statistics.vif":
                data = variance_inflation(obj, list(arguments["predictors"]))
            elif operation in ("statistics.score_scale", "statistics.item_total"):
                spec = ScaleDefinition(**dict(arguments["scale"]))
                if operation == "statistics.score_scale":
                    data = score_scale(obj, spec, row_id=arguments.get("row_id"))
                else:
                    data = item_total_diagnostics(obj, spec)
            elif operation in ("statistics.time_features", "statistics.adf"):
                chronology = parse_chronology(
                    obj, str(arguments["time_column"]), str(arguments["value_column"])
                )
                if operation == "statistics.time_features":
                    data = causal_features(
                        chronology,
                        lags=list(arguments["lags"]),
                        rolling_window=arguments.get("rolling_window"),
                    )
                else:
                    data = adf_stationarity(chronology)
            elif operation == "plot.render":
                output_root = context.get("trusted_export_root")
                require(
                    isinstance(output_root, Path),
                    "Approved export root required",
                    "PERMISSION_DENIED",
                )
                output_path = (output_root / str(arguments["filename"])).resolve()
                require(
                    output_path.is_relative_to(output_root.resolve()),
                    "Export must be under approved root",
                    "PERMISSION_DENIED",
                )
                data = render_plot(
                    obj,
                    x=str(arguments["x"]),
                    y=arguments.get("y"),
                    output=output_path,
                    kind=str(arguments.get("kind", "scatter")),
                )
            else:
                raise AnalysisError("NOT_FOUND", "Unsupported operation")
        writes = [data.get("revision", "")] if effect != "read" else []
        return {
            "request_id": request_id,
            "status": "ok",
            "data": data,
            "artifacts": [],
            "warnings": [],
            "error": None,
            "provenance": [
                {
                    "operation": operation,
                    "dataset_revision": data.get("dataset_revision", data.get("revision")),
                    "argument_hash": digest(dict(arguments)),
                }
            ],
            "impact": {"local_writes": writes, "network_hosts": [], "irreversible": False},
        }


def build_analysis_facade(directory: Path) -> AnalysisFacade:
    return AnalysisFacade(directory)
