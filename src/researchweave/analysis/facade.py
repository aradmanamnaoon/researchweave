"""Typed command boundary for the desktop host and agent tool dispatcher."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .advanced_statistics import (
    ancova,
    approximate_permutation_mean_difference,
    cluster_bootstrap_mean,
    distribution_diagnostics,
    factorial_anova,
    friedman_test,
    kruskal_wallis,
    linear_mixed_effects,
    ordinal_logistic,
    paired_permutation_mean_difference,
    repeated_measures_anova,
    tukey_hsd,
    welch_anova,
    wilcoxon_paired,
)
from .authorization import CapabilityIssuer, HostCapability, HostPaths
from .data_ops import case_selection, frequency_weighted_mean, missingness, recode_missing
from .datasets import (
    DatasetStore,
    data_view,
    export_csv,
    import_csv,
    import_table,
    page,
    set_variable,
)
from .diagnostics import ols_diagnostics, variance_inflation
from .effects import (
    anova_effect_sizes,
    correlation_effect,
    independent_standardized_mean_difference,
    paired_standardized_mean_difference,
    rank_biserial_from_mann_whitney,
)
from .errors import AnalysisError, require
from .generalized import logistic_regression, poisson_regression
from .inference import (
    bootstrap_mean,
    contingency,
    exact_permutation_mean_difference,
    independent_rank_test,
    one_way_anova,
)
from .longitudinal import difference_in_differences, gaussian_gee
from .measurement import (
    correlation_suitability,
    exploratory_factors,
    fleiss_agreement,
    icc_two_way_absolute,
)
from .meta_analysis import funnel_asymmetry_egger, random_effects_meta
from .missing_data import (
    available_case_covariance,
    complete_case,
    multiple_impute_normal,
    simple_impute,
)
from .modeling import adjust_pvalues, linear_regression, pooled_effects
from .models import Dataset, digest
from .multivariate import (
    cluster_validation,
    hierarchical_clusters,
    kmeans_clusters,
    principal_components,
)
from .plots import render_plot
from .power import two_sample_t_power, two_sample_t_required
from .psychometrics import reliability_diagnostics
from .recommendations import recommend_from_mapping
from .runtime import RuntimeAuthorizer, run_script
from .scale_scoring import ScaleDefinition, item_total_diagnostics, score_scale
from .schemas import RESULT_SCHEMA, schema_for, validate_arguments
from .statistics import correlation, describe, reliability, t_test
from .survey import design_weighted_mean, survey_proportions
from .survival import cox_proportional_hazards, kaplan_meier, logrank_test
from .time_series import (
    adf_stationarity,
    arima_forecast,
    causal_features,
    ljung_box,
    parse_chronology,
    seasonal_decomposition,
)
from .transformations import transform


class AnalysisFacade:
    def __init__(self, directory: Path, *, host_paths: HostPaths | None = None):
        self.store = DatasetStore(directory)
        self.host_paths = host_paths or HostPaths()
        self.authorizations = CapabilityIssuer(directory)
        self.runtime_authorizations = RuntimeAuthorizer()

    def issue_authorization(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        *,
        ttl_seconds: int = 60,
    ) -> HostCapability:
        """Trusted-host API used only after the user approves an exact preview."""

        known = {entry["operation"]: entry for entry in self.capability_manifest()}
        require(operation in known, "Unknown operation", "NOT_FOUND")
        effect = str(known[operation]["effect"])
        require(effect != "read", "Read-only operations do not require approval")
        return self.authorizations.issue(
            operation,
            arguments,
            effect=effect,
            ttl_seconds=ttl_seconds,
        )

    def capability_manifest(self) -> list[Mapping[str, Any]]:
        names = {
            "dataset.import": "local-write",
            "dataset.inspect": "read",
            "dataset.page": "read",
            "dataset.view": "read",
            "dataset.export_csv": "sensitive-export",
            "dataset.transform": "local-write",
            "dataset.variable": "local-write",
            "dataset.missingness": "read",
            "dataset.select": "local-write",
            "dataset.user_missing": "local-write",
            "dataset.complete_case": "local-write",
            "dataset.simple_impute": "local-write",
            "dataset.multiple_impute": "local-write",
            "statistics.weighted_mean": "read",
            "statistics.available_case": "read",
            "statistics.recommend": "read",
            "statistics.effect_independent": "read",
            "statistics.effect_paired": "read",
            "statistics.effect_rank": "read",
            "statistics.effect_anova": "read",
            "statistics.effect_correlation": "read",
            "statistics.describe": "read",
            "statistics.test": "read",
            "statistics.correlate": "read",
            "statistics.psychometric": "read",
            "statistics.reliability_diagnostics": "read",
            "statistics.model": "read",
            "statistics.logistic": "read",
            "statistics.poisson": "read",
            "statistics.meta": "read",
            "statistics.meta_random": "read",
            "statistics.egger": "read",
            "statistics.adjust": "read",
            "statistics.distribution": "read",
            "statistics.contingency": "read",
            "statistics.rank": "read",
            "statistics.wilcoxon": "read",
            "statistics.kruskal": "read",
            "statistics.friedman": "read",
            "statistics.anova": "read",
            "statistics.welch_anova": "read",
            "statistics.tukey": "read",
            "statistics.factorial_anova": "read",
            "statistics.repeated_anova": "read",
            "statistics.ancova": "read",
            "statistics.bootstrap": "read",
            "statistics.cluster_bootstrap": "read",
            "statistics.permutation": "read",
            "statistics.permutation_approx": "read",
            "statistics.permutation_paired": "read",
            "statistics.pca": "read",
            "statistics.kmeans": "read",
            "statistics.hierarchical": "read",
            "statistics.cluster_validation": "read",
            "statistics.power": "read",
            "statistics.required_n": "read",
            "statistics.diagnostics": "read",
            "statistics.vif": "read",
            "statistics.score_scale": "read",
            "statistics.item_total": "read",
            "statistics.time_features": "read",
            "statistics.adf": "read",
            "statistics.ljung_box": "read",
            "statistics.seasonal_decompose": "read",
            "statistics.arima_forecast": "read",
            "statistics.survival": "read",
            "statistics.logrank": "read",
            "statistics.cox": "read",
            "statistics.gee": "read",
            "statistics.did": "read",
            "statistics.mixed_effects": "read",
            "statistics.ordinal": "read",
            "statistics.survey_mean": "read",
            "statistics.survey_proportions": "read",
            "statistics.factor_suitability": "read",
            "statistics.efa": "read",
            "statistics.fleiss": "read",
            "statistics.icc": "read",
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
                "arguments_schema": schema_for(operation).as_json_schema(),
                "result_schema": RESULT_SCHEMA,
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
        validate_arguments(operation, arguments)
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
        validate_arguments(operation, arguments)
        effect = known[operation]["effect"]
        if effect != "read":
            self.authorizations.verify_and_consume(
                context.get("host_capability"),
                operation,
                arguments,
                effect=str(effect),
            )
        if operation == "statistics.meta":
            data = pooled_effects(
                list(arguments["studies"]), model=str(arguments.get("model", "fixed"))
            )
        elif operation == "statistics.meta_random":
            data = random_effects_meta(
                list(arguments["studies"]),
                tau_method=str(arguments.get("tau_method", "reml")),
                hartung_knapp=bool(arguments.get("hartung_knapp", True)),
            )
        elif operation == "statistics.egger":
            data = funnel_asymmetry_egger(list(arguments["studies"]))
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
        elif operation == "statistics.cluster_bootstrap":
            from dataclasses import asdict

            data = asdict(
                cluster_bootstrap_mean(
                    list(arguments["values"]),
                    [str(value) for value in arguments["clusters"]],
                    seed=int(arguments["seed"]),
                    iterations=int(arguments.get("iterations", 2000)),
                    confidence=float(arguments.get("confidence", 0.95)),
                )
            )
        elif operation == "statistics.permutation":
            data = exact_permutation_mean_difference(
                list(arguments["first"]),
                list(arguments["second"]),
                alternative=str(arguments.get("alternative", "two-sided")),
            )
        elif operation == "statistics.permutation_approx":
            data = approximate_permutation_mean_difference(
                list(arguments["first"]),
                list(arguments["second"]),
                seed=int(arguments["seed"]),
                iterations=int(arguments.get("iterations", 10_000)),
                alternative=str(arguments.get("alternative", "two-sided")),
            )
        elif operation == "statistics.permutation_paired":
            data = paired_permutation_mean_difference(
                list(arguments["first"]),
                list(arguments["second"]),
                seed=int(arguments["seed"]),
                iterations=int(arguments.get("iterations", 10_000)),
                alternative=str(arguments.get("alternative", "two-sided")),
            )
        elif operation in ("statistics.power", "statistics.required_n"):
            from dataclasses import asdict

            options = dict(arguments)
            if operation == "statistics.power":
                data = asdict(two_sample_t_power(**options))
            else:
                data = asdict(two_sample_t_required(**options))
        elif operation == "statistics.fleiss":
            data = fleiss_agreement(list(arguments["rating_counts"]))
        elif operation == "statistics.icc":
            data = icc_two_way_absolute(list(arguments["ratings"]))
        elif operation == "statistics.recommend":
            data = recommend_from_mapping(dict(arguments))
        elif operation == "statistics.effect_independent":
            data = independent_standardized_mean_difference(
                list(arguments["first"]), list(arguments["second"])
            )
        elif operation == "statistics.effect_paired":
            data = paired_standardized_mean_difference(
                list(arguments["first"]), list(arguments["second"])
            )
        elif operation == "statistics.effect_rank":
            data = rank_biserial_from_mann_whitney(
                float(arguments["u"]), int(arguments["n_first"]), int(arguments["n_second"])
            )
        elif operation == "statistics.effect_anova":
            data = anova_effect_sizes(
                ss_effect=float(arguments["ss_effect"]),
                ss_error=float(arguments["ss_error"]),
                df_effect=float(arguments["df_effect"]),
                df_error=float(arguments["df_error"]),
                ss_total=(
                    float(arguments["ss_total"]) if arguments.get("ss_total") is not None else None
                ),
            )
        elif operation == "statistics.effect_correlation":
            data = correlation_effect(float(arguments["r"]), n=int(arguments["n"]))
        elif operation in ("runtime.python", "runtime.r"):
            language = "python" if operation.endswith("python") else "r"
            timeout_seconds = int(arguments.get("timeout_seconds", 10))
            runtime_approval = self.runtime_authorizations.issue(
                str(arguments["source"]),
                language=language,
                timeout_seconds=timeout_seconds,
            )
            data = run_script(
                str(arguments["source"]),
                authorizer=self.runtime_authorizations,
                approval=runtime_approval,
                language=language,
                timeout_seconds=timeout_seconds,
                directory=self.host_paths.execution_directory(),
            )
        elif operation == "dataset.import":
            path = self.host_paths.import_file(str(arguments["filename"]))
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
        elif operation == "dataset.multiple_impute":
            obj = self._dataset(arguments)
            generated = multiple_impute_normal(
                obj,
                list(arguments["columns"]),
                m=int(arguments.get("m", 5)),
                seed=int(arguments["seed"]),
            )
            for revision in generated.datasets:
                self.store.save(revision)
            data = {
                "dataset_id": obj.dataset_id,
                "parent_revision": obj.revision,
                "revisions": [revision.revision for revision in generated.datasets],
                "m": len(generated.datasets),
                "method": generated.method,
                "seed": generated.seed,
                "missing_counts": generated.missing_counts,
                "assumptions": list(generated.assumptions),
            }
        elif operation in ("dataset.inspect", "dataset.page", "dataset.view"):
            obj = self._dataset(arguments)
            if operation == "dataset.view":
                data = data_view(
                    obj,
                    offset=int(arguments.get("offset", 0)),
                    limit=int(arguments.get("limit", 100)),
                    sort_by=arguments.get("sort_by"),
                    descending=bool(arguments.get("descending", False)),
                    search=arguments.get("search"),
                )
            else:
                data = page(
                    obj,
                    offset=int(arguments.get("offset", 0)),
                    limit=int(arguments.get("limit", 100)),
                )
            if operation == "dataset.inspect":
                data["variables"] = [v.__dict__ for v in obj.variables]
                data["source_hash"] = obj.source_hash
        elif operation in (
            "dataset.transform",
            "dataset.variable",
            "dataset.select",
            "dataset.user_missing",
            "dataset.complete_case",
            "dataset.simple_impute",
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
            elif operation == "dataset.complete_case":
                updated, receipt = complete_case(obj, list(arguments["columns"]))
            elif operation == "dataset.simple_impute":
                updated, receipt = simple_impute(
                    obj,
                    str(arguments["column"]),
                    strategy=str(arguments["strategy"]),
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
            if operation in {"dataset.complete_case", "dataset.simple_impute"}:
                data["receipt"] = receipt
        else:
            obj = self._dataset(arguments)
            if operation == "statistics.describe":
                data = describe(obj, str(arguments["column"]))
            elif operation == "statistics.available_case":
                data = available_case_covariance(obj, list(arguments["columns"]))
            elif operation == "statistics.distribution":
                data = distribution_diagnostics(obj, str(arguments["column"]))
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
            elif operation == "statistics.reliability_diagnostics":
                data = reliability_diagnostics(
                    obj,
                    list(arguments["columns"]),
                    reverse=list(arguments.get("reverse", [])),
                    scale_min=arguments.get("scale_min"),
                    scale_max=arguments.get("scale_max"),
                    bootstrap_iterations=int(arguments.get("bootstrap_iterations", 0)),
                    seed=int(arguments.get("seed", 0)),
                )
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
            elif operation == "statistics.wilcoxon":
                data = wilcoxon_paired(
                    obj,
                    str(arguments["first"]),
                    str(arguments["second"]),
                    alternative=str(arguments.get("alternative", "two-sided")),
                    zero_method=str(arguments.get("zero_method", "wilcox")),
                )
            elif operation == "statistics.kruskal":
                data = kruskal_wallis(
                    obj,
                    str(arguments["outcome"]),
                    str(arguments["group"]),
                    levels=list(arguments["levels"]),
                )
            elif operation == "statistics.friedman":
                data = friedman_test(obj, list(arguments["columns"]))
            elif operation == "statistics.anova":
                data = one_way_anova(
                    obj,
                    str(arguments["outcome"]),
                    str(arguments["group"]),
                    levels=list(arguments["levels"]),
                ).as_json()
            elif operation == "statistics.welch_anova":
                data = welch_anova(
                    obj,
                    str(arguments["outcome"]),
                    str(arguments["group"]),
                    levels=list(arguments["levels"]),
                )
            elif operation == "statistics.tukey":
                data = tukey_hsd(
                    obj,
                    str(arguments["outcome"]),
                    str(arguments["group"]),
                    levels=list(arguments["levels"])
                    if arguments.get("levels") is not None
                    else None,
                    alpha=float(arguments.get("alpha", 0.05)),
                )
            elif operation == "statistics.factorial_anova":
                data = factorial_anova(
                    obj,
                    str(arguments["outcome"]),
                    list(arguments["factors"]),
                    typ=int(arguments.get("type", 2)),
                )
            elif operation == "statistics.repeated_anova":
                data = repeated_measures_anova(
                    obj,
                    subject=str(arguments["subject"]),
                    within=str(arguments["within"]),
                    outcome=str(arguments["outcome"]),
                )
            elif operation == "statistics.ancova":
                data = ancova(
                    obj,
                    str(arguments["outcome"]),
                    str(arguments["factor"]),
                    list(arguments["covariates"]),
                    typ=int(arguments.get("type", 2)),
                    include_slope_interactions=bool(arguments.get("slope_interactions", False)),
                )
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
            elif operation == "statistics.cluster_validation":
                data = cluster_validation(
                    obj,
                    list(arguments["columns"]),
                    k_values=[int(value) for value in arguments["k_values"]],
                    seed=int(arguments.get("seed", 0)),
                    stability_repeats=int(arguments.get("stability_repeats", 8)),
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
            elif operation in (
                "statistics.time_features",
                "statistics.adf",
                "statistics.ljung_box",
                "statistics.seasonal_decompose",
                "statistics.arima_forecast",
            ):
                chronology = parse_chronology(
                    obj, str(arguments["time_column"]), str(arguments["value_column"])
                )
                if operation == "statistics.time_features":
                    data = causal_features(
                        chronology,
                        lags=list(arguments["lags"]),
                        rolling_window=arguments.get("rolling_window"),
                    )
                elif operation == "statistics.adf":
                    data = adf_stationarity(chronology)
                elif operation == "statistics.ljung_box":
                    data = ljung_box(chronology, lags=[int(value) for value in arguments["lags"]])
                elif operation == "statistics.seasonal_decompose":
                    data = seasonal_decomposition(chronology, period=int(arguments["period"]))
                else:
                    data = arima_forecast(
                        chronology,
                        order=tuple(int(value) for value in arguments["order"]),
                        seasonal_order=tuple(
                            int(value) for value in arguments.get("seasonal_order", [0, 0, 0, 0])
                        ),
                        horizon=int(arguments["horizon"]),
                        validation_horizon=int(arguments.get("validation_horizon", 0)),
                        confidence=float(arguments.get("confidence", 0.95)),
                    )
            elif operation == "statistics.survival":
                data = kaplan_meier(
                    obj,
                    str(arguments["duration"]),
                    str(arguments["event"]),
                    group=arguments.get("group"),
                    level=arguments.get("level"),
                )
            elif operation == "statistics.logrank":
                levels = tuple(arguments["levels"])
                require(len(levels) == 2, "Logrank requires two groups")
                data = logrank_test(
                    obj,
                    str(arguments["duration"]),
                    str(arguments["event"]),
                    str(arguments["group"]),
                    levels=levels,
                )
            elif operation == "statistics.cox":
                data = cox_proportional_hazards(
                    obj,
                    str(arguments["duration"]),
                    str(arguments["event"]),
                    list(arguments["predictors"]),
                )
            elif operation == "statistics.gee":
                data = gaussian_gee(
                    obj,
                    subject=str(arguments["subject"]),
                    time=str(arguments["time"]),
                    outcome=str(arguments["outcome"]),
                    predictors=list(arguments["predictors"]),
                    correlation=str(arguments.get("correlation", "exchangeable")),
                )
            elif operation == "statistics.did":
                data = difference_in_differences(
                    obj,
                    subject=str(arguments["subject"]),
                    time=str(arguments["time"]),
                    treatment=str(arguments["treatment"]),
                    outcome=str(arguments["outcome"]),
                )
            elif operation == "statistics.mixed_effects":
                data = linear_mixed_effects(
                    obj,
                    outcome=str(arguments["outcome"]),
                    predictors=list(arguments["predictors"]),
                    group=str(arguments["group"]),
                    random_slope=arguments.get("random_slope"),
                    reml=bool(arguments.get("reml", True)),
                )
            elif operation == "statistics.ordinal":
                data = ordinal_logistic(
                    obj,
                    outcome=str(arguments["outcome"]),
                    predictors=list(arguments["predictors"]),
                    levels=list(arguments["levels"]),
                    link=str(arguments.get("link", "logit")),
                )
            elif operation == "statistics.survey_mean":
                data = design_weighted_mean(
                    obj,
                    outcome=str(arguments["outcome"]),
                    weight=str(arguments["weight"]),
                    stratum=str(arguments["stratum"]),
                    psu=str(arguments["psu"]),
                )
            elif operation == "statistics.survey_proportions":
                data = survey_proportions(
                    obj,
                    category=str(arguments["category"]),
                    weight=str(arguments["weight"]),
                    stratum=str(arguments["stratum"]),
                    psu=str(arguments["psu"]),
                    levels=list(arguments["levels"]),
                )
            elif operation == "statistics.factor_suitability":
                data = correlation_suitability(obj, list(arguments["columns"]))
            elif operation == "statistics.efa":
                data = exploratory_factors(
                    obj,
                    list(arguments["columns"]),
                    n_factors=int(arguments["n_factors"]),
                    rotate=str(arguments.get("rotate", "varimax")),
                )
            elif operation == "plot.render":
                output_path = self.host_paths.export_file(str(arguments["filename"]))
                data = render_plot(
                    obj,
                    x=str(arguments["x"]),
                    y=arguments.get("y"),
                    output=output_path,
                    kind=str(arguments.get("kind", "scatter")),
                )
            elif operation == "dataset.export_csv":
                output_path = self.host_paths.export_file(str(arguments["filename"]))
                data = export_csv(
                    obj,
                    output_path,
                    delimiter=str(arguments.get("delimiter", ",")),
                    decimal=str(arguments.get("decimal", ".")),
                    formula_safe=bool(arguments.get("formula_safe", True)),
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


def build_analysis_facade(
    directory: Path,
    *,
    import_root: Path | None = None,
    export_root: Path | None = None,
    execution_root: Path | None = None,
) -> AnalysisFacade:
    return AnalysisFacade(
        directory,
        host_paths=HostPaths(import_root, export_root, execution_root),
    )
