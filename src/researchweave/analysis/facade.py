"""Typed command boundary for the desktop host and agent tool dispatcher."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

from .advanced_statistics import (
    ancova,
    approximate_permutation_mean_difference,
    bca_bootstrap_mean,
    cluster_bootstrap_mean,
    distribution_diagnostics,
    factorial_anova,
    friedman_test,
    grouped_bootstrap_mean_difference,
    kruskal_wallis,
    linear_mixed_effects,
    ordinal_logistic,
    paired_bootstrap_mean_difference,
    paired_permutation_mean_difference,
    repeated_measures_anova,
    stratified_permutation_mean_difference,
    tukey_hsd,
    welch_anova,
    wilcoxon_paired,
)
from .authorization import CapabilityIssuer, HostCapability, HostPaths
from .automatic import AnalysisRequest, plan_automatic_analysis
from .coding_review import adjudicate_disagreements, propose_relocation
from .data_ops import (
    aggregate_groups,
    analytic_weighted_mean,
    case_selection,
    frequency_weighted_mean,
    join_tables,
    missingness,
    pivot_longer,
    pivot_wider,
    quality_screen,
    recode_missing,
)
from .datasets import (
    DatasetStore,
    data_view,
    export_csv,
    import_csv,
    import_table,
    page,
    scan_parquet_page,
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
from .generalized import (
    estimated_negative_binomial_regression,
    logistic_regression,
    negative_binomial_regression,
    poisson_regression,
)
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
from .mixed_methods import joint_display
from .modeling import adjust_pvalues, linear_regression, pooled_effects
from .models import Dataset, digest, utc_now
from .multivariate import (
    cluster_validation,
    hierarchical_clusters,
    kmeans_clusters,
    principal_components,
)
from .plots import render_plot
from .power import (
    mean_precision_required,
    one_sample_t_power,
    two_proportion_power,
    two_proportion_required,
    two_sample_t_power,
    two_sample_t_required,
)
from .psychometrics import reliability_diagnostics
from .qualitative import Code, Transcript, cohen_kappa
from .qualitative_store import Memo, QualitativeState, QualitativeStore
from .recommendations import recommend_from_mapping
from .reproducibility import AnalysisPlan, receipt_from_json, verify_replay
from .runtime import RuntimeAuthorizer, run_script
from .scale_scoring import ScaleDefinition, item_total_diagnostics, score_scale
from .schemas import RESULT_SCHEMA, schema_for, validate_arguments
from .script_exports import export_python_script, export_r_script
from .statistics import (
    correlation,
    correlation_matrix,
    describe,
    frequency_table,
    grouped_describe,
    reliability,
    t_test,
)
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
        self.qualitative_store = QualitativeStore(directory / "qualitative")
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
            "dataset.scan_parquet": "read",
            "dataset.inspect": "read",
            "dataset.page": "read",
            "dataset.view": "read",
            "dataset.export_csv": "sensitive-export",
            "dataset.transform": "local-write",
            "dataset.variable": "local-write",
            "dataset.missingness": "read",
            "dataset.quality": "read",
            "dataset.select": "local-write",
            "dataset.user_missing": "local-write",
            "dataset.complete_case": "local-write",
            "dataset.simple_impute": "local-write",
            "dataset.multiple_impute": "local-write",
            "dataset.join": "local-write",
            "dataset.aggregate": "local-write",
            "dataset.pivot_longer": "local-write",
            "dataset.pivot_wider": "local-write",
            "statistics.weighted_mean": "read",
            "statistics.analytic_weighted_mean": "read",
            "statistics.available_case": "read",
            "statistics.recommend": "read",
            "statistics.auto_plan": "read",
            "statistics.auto_analyze": "read",
            "statistics.effect_independent": "read",
            "statistics.effect_paired": "read",
            "statistics.effect_rank": "read",
            "statistics.effect_anova": "read",
            "statistics.effect_correlation": "read",
            "statistics.describe": "read",
            "statistics.frequency": "read",
            "statistics.grouped_describe": "read",
            "statistics.test": "read",
            "statistics.correlate": "read",
            "statistics.correlation_matrix": "read",
            "statistics.psychometric": "read",
            "statistics.reliability_diagnostics": "read",
            "statistics.model": "read",
            "statistics.logistic": "read",
            "statistics.poisson": "read",
            "statistics.negative_binomial": "read",
            "statistics.negative_binomial_estimated": "read",
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
            "statistics.bootstrap_bca": "read",
            "statistics.bootstrap_grouped": "read",
            "statistics.bootstrap_paired": "read",
            "statistics.cluster_bootstrap": "read",
            "statistics.permutation": "read",
            "statistics.permutation_approx": "read",
            "statistics.permutation_paired": "read",
            "statistics.permutation_stratified": "read",
            "statistics.pca": "read",
            "statistics.kmeans": "read",
            "statistics.hierarchical": "read",
            "statistics.cluster_validation": "read",
            "statistics.power": "read",
            "statistics.required_n": "read",
            "statistics.power_one_sample": "read",
            "statistics.power_proportion": "read",
            "statistics.required_n_proportion": "read",
            "statistics.required_n_precision": "read",
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
            "qualitative.create": "local-write",
            "qualitative.inspect": "read",
            "qualitative.add_code": "local-write",
            "qualitative.update_code": "local-write",
            "qualitative.delete_code": "local-write",
            "qualitative.add_transcript": "local-write",
            "qualitative.annotate": "local-write",
            "qualitative.add_memo": "local-write",
            "qualitative.review_annotation": "local-write",
            "qualitative.relocation_proposal": "read",
            "qualitative.kappa": "read",
            "qualitative.adjudicate": "read",
            "mixed.joint_display": "read",
            "mixed.joint_display_sensitive": "sensitive-export",
            "audit.plan": "read",
            "audit.verify_replay": "read",
            "syntax.python": "read",
            "syntax.r": "read",
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
        elif operation == "audit.plan":
            plan = AnalysisPlan.from_json(dict(arguments["plan"]))
            data = {
                "plan_id": plan.plan_id,
                "schema_version": plan.schema_version,
                "seed": plan.seed,
                "spec_hash": plan.spec_hash,
                "execution_order": list(plan.execution_order()),
                "operations": [step.operation for step in plan.steps],
                "step_count": len(plan.steps),
                "rationale": plan.rationale,
                "hypotheses": list(plan.hypotheses),
            }
        elif operation == "audit.verify_replay":
            expected = receipt_from_json(dict(arguments["expected"]))
            actual = receipt_from_json(dict(arguments["actual"]))
            data = verify_replay(expected, actual)
        elif operation in {"syntax.python", "syntax.r"}:
            target_operation = str(arguments["operation"])
            target_arguments = dict(arguments["arguments"])
            dataset = None
            if arguments.get("dataset_id") is not None or arguments.get("revision") is not None:
                require(
                    isinstance(arguments.get("dataset_id"), str)
                    and isinstance(arguments.get("revision"), str),
                    "Syntax export dataset identity requires dataset_id and revision together",
                )
                dataset = self.store.load(
                    str(arguments["dataset_id"]),
                    str(arguments["revision"]),
                )
            if operation == "syntax.python":
                data = export_python_script(target_operation, target_arguments, dataset).as_json()
            else:
                require(
                    dataset is not None,
                    "R syntax export requires an immutable dataset revision",
                )
                data = export_r_script(
                    target_operation,
                    target_arguments,
                    cast(Dataset, dataset),
                ).as_json()
        elif operation == "statistics.bootstrap":
            from dataclasses import asdict

            data = asdict(
                bootstrap_mean(
                    list(arguments["values"]),
                    seed=int(arguments["seed"]),
                    iterations=int(arguments.get("iterations", 2000)),
                )
            )
        elif operation == "statistics.bootstrap_bca":
            from dataclasses import asdict

            data = asdict(
                bca_bootstrap_mean(
                    list(arguments["values"]),
                    seed=int(arguments["seed"]),
                    iterations=int(arguments.get("iterations", 2000)),
                    confidence=float(arguments.get("confidence", 0.95)),
                )
            )
        elif operation == "statistics.bootstrap_grouped":
            from dataclasses import asdict

            data = asdict(
                grouped_bootstrap_mean_difference(
                    list(arguments["first"]),
                    list(arguments["second"]),
                    seed=int(arguments["seed"]),
                    iterations=int(arguments.get("iterations", 2000)),
                    confidence=float(arguments.get("confidence", 0.95)),
                )
            )
        elif operation == "statistics.bootstrap_paired":
            from dataclasses import asdict

            data = asdict(
                paired_bootstrap_mean_difference(
                    list(arguments["first"]),
                    list(arguments["second"]),
                    seed=int(arguments["seed"]),
                    iterations=int(arguments.get("iterations", 2000)),
                    confidence=float(arguments.get("confidence", 0.95)),
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
        elif operation == "statistics.permutation_stratified":
            data = stratified_permutation_mean_difference(
                list(arguments["first"]),
                list(arguments["second"]),
                list(arguments["first_strata"]),
                list(arguments["second_strata"]),
                seed=int(arguments["seed"]),
                iterations=int(arguments.get("iterations", 10_000)),
                alternative=str(arguments.get("alternative", "two-sided")),
            )
        elif operation in (
            "statistics.power",
            "statistics.required_n",
            "statistics.power_one_sample",
            "statistics.power_proportion",
            "statistics.required_n_proportion",
            "statistics.required_n_precision",
        ):
            from dataclasses import asdict

            options = dict(arguments)
            if operation == "statistics.power":
                data = asdict(two_sample_t_power(**options))
            elif operation == "statistics.required_n":
                data = asdict(two_sample_t_required(**options))
            elif operation == "statistics.power_one_sample":
                data = asdict(one_sample_t_power(**options))
            elif operation == "statistics.power_proportion":
                data = asdict(two_proportion_power(**options))
            elif operation == "statistics.required_n_proportion":
                data = asdict(two_proportion_required(**options))
            else:
                data = mean_precision_required(**options)
        elif operation == "statistics.fleiss":
            data = fleiss_agreement(list(arguments["rating_counts"]))
        elif operation == "statistics.icc":
            data = icc_two_way_absolute(list(arguments["ratings"]))
        elif operation == "qualitative.create":
            project_id = str(arguments["project_id"])
            data = self.qualitative_store.save(project_id, QualitativeState(), create_only=True)
        elif operation == "qualitative.inspect":
            project_id = str(arguments["project_id"])
            state, content_hash = self.qualitative_store.load_snapshot(project_id)
            data = {
                "project_id": project_id,
                "content_hash": content_hash,
                "state": state.to_json(),
            }
        elif operation in {
            "qualitative.add_code",
            "qualitative.update_code",
            "qualitative.delete_code",
            "qualitative.add_transcript",
            "qualitative.annotate",
            "qualitative.add_memo",
            "qualitative.review_annotation",
        }:
            project_id = str(arguments["project_id"])
            expected_hash = str(arguments["expected_content_hash"])
            state, actual_hash = self.qualitative_store.load_snapshot(project_id)
            require(
                actual_hash == expected_hash,
                "Qualitative project changed since it was read",
                "CONFLICT",
            )
            if operation == "qualitative.add_code":
                state.add_code(
                    Code(
                        str(arguments["code_id"]),
                        str(arguments["name"]),
                        str(arguments.get("description", "")),
                        arguments.get("parent"),
                    ),
                    actor=str(arguments["actor"]),
                )
            elif operation == "qualitative.update_code":
                parent = arguments["parent"] if "parent" in arguments else ...
                state.update_code(
                    str(arguments["code_id"]),
                    actor=str(arguments["actor"]),
                    name=arguments.get("name"),
                    description=arguments.get("description"),
                    parent=parent,
                )
            elif operation == "qualitative.delete_code":
                state.delete_code(str(arguments["code_id"]), actor=str(arguments["actor"]))
            elif operation == "qualitative.add_transcript":
                state.project.add_transcript(
                    Transcript(
                        str(arguments["source_id"]),
                        str(arguments["text"]),
                        str(arguments["case_id"]),
                        bool(arguments.get("confidential", True)),
                    )
                )
            elif operation == "qualitative.annotate":
                state.project.annotate(
                    str(arguments["source_id"]),
                    int(arguments["start"]),
                    int(arguments["end"]),
                    str(arguments["code_id"]),
                    str(arguments["coder"]),
                    str(arguments["unit_id"]),
                )
            elif operation == "qualitative.add_memo":
                state.add_memo(
                    Memo(
                        str(arguments["memo_id"]),
                        str(arguments["title"]),
                        str(arguments["text"]),
                        str(arguments["author"]),
                        utc_now(),
                        source_id=arguments.get("source_id"),
                        code_id=arguments.get("code_id"),
                    )
                )
            else:
                ledger = state.review_ledger()
                decision = ledger.decide(
                    int(arguments["annotation_index"]),
                    cast(
                        Literal["accept", "reject", "needs_review"],
                        str(arguments["disposition"]),
                    ),
                    reviewer=str(arguments["reviewer"]),
                    rationale=str(arguments["rationale"]),
                )
                state.attach_review_ledger(ledger)
            saved = self.qualitative_store.save(
                project_id, state, expected_content_hash=expected_hash
            )
            data = {**saved, "state": state.to_json()}
            if operation == "qualitative.review_annotation":
                data["decision"] = decision.__dict__
        elif operation == "qualitative.relocation_proposal":
            state = self.qualitative_store.load(str(arguments["project_id"]))
            index = int(arguments["annotation_index"])
            require(
                0 <= index < len(state.project.annotations),
                "Annotation does not exist",
                "NOT_FOUND",
            )
            annotation = state.project.annotations[index]
            original = state.project.transcripts[annotation.source_id]
            proposal = propose_relocation(
                annotation,
                Transcript(
                    original.source_id,
                    str(arguments["revised_text"]),
                    original.case_id,
                    original.confidential,
                ),
            )
            data = proposal.__dict__
        elif operation == "qualitative.kappa":
            first = {str(key): str(value) for key, value in dict(arguments["first"]).items()}
            second = {str(key): str(value) for key, value in dict(arguments["second"]).items()}
            data = cohen_kappa(first, second)
        elif operation == "qualitative.adjudicate":
            state = self.qualitative_store.load(str(arguments["project_id"]))
            data = adjudicate_disagreements(
                state.project,
                coder_a=str(arguments["coder_a"]),
                coder_b=str(arguments["coder_b"]),
                unit_ids=list(arguments["unit_ids"]),
                resolutions={
                    str(key): str(value) for key, value in dict(arguments["resolutions"]).items()
                },
                adjudicator=str(arguments["adjudicator"]),
                rationales={
                    str(key): str(value) for key, value in dict(arguments["rationales"]).items()
                },
            )
        elif operation in {"mixed.joint_display", "mixed.joint_display_sensitive"}:
            obj = self._dataset(arguments)
            state = self.qualitative_store.load(str(arguments["project_id"]))
            sensitive = operation == "mixed.joint_display_sensitive"
            data = joint_display(
                obj,
                state.project,
                case_column=str(arguments["case_column"]),
                measure_column=str(arguments["measure_column"]),
                code_id=str(arguments["code_id"]),
                min_reporting_cases=int(arguments.get("min_reporting_cases", 3)),
                allow_quotes=bool(arguments.get("allow_quotes", False)) if sensitive else False,
                include_private=(
                    bool(arguments.get("include_private", False)) if sensitive else False
                ),
            )
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
        elif operation == "dataset.scan_parquet":
            path = self.host_paths.import_file(str(arguments["filename"]))
            require(path.suffix.lower() == ".parquet", "Parquet scan requires a .parquet source")
            data = scan_parquet_page(
                path,
                offset=int(arguments.get("offset", 0)),
                limit=int(arguments.get("limit", 100)),
                columns=list(arguments["columns"]) if "columns" in arguments else None,
                batch_size=int(arguments.get("batch_size", 65_536)),
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
        elif operation == "dataset.join":
            left = self._dataset(arguments)
            right = self.store.load(
                str(arguments["right_dataset_id"]), str(arguments["right_revision"])
            )
            updated, receipt = join_tables(
                left,
                right,
                left_on=str(arguments["left_on"]),
                right_on=str(arguments["right_on"]),
                how=cast(Literal["inner", "left"], str(arguments.get("how", "inner"))),
                cardinality=cast(
                    Literal["one_to_one", "one_to_many", "many_to_one"],
                    str(arguments.get("cardinality", "one_to_one")),
                ),
                max_expansion=int(arguments.get("max_expansion", 5)),
            )
            self.store.save(updated)
            data = {
                "dataset_id": updated.dataset_id,
                "revision": updated.revision,
                "parent_revision": left.revision,
                "right_revision": right.revision,
                "n": len(updated.records),
                "receipt": receipt,
            }
        elif operation in {"dataset.aggregate", "dataset.pivot_longer", "dataset.pivot_wider"}:
            obj = self._dataset(arguments)
            if operation == "dataset.aggregate":
                updated = aggregate_groups(
                    obj,
                    by=list(arguments["by"]),
                    values=list(arguments["values"]),
                    functions=list(arguments["functions"]),
                )
            elif operation == "dataset.pivot_longer":
                updated = pivot_longer(
                    obj,
                    id_columns=list(arguments["id_columns"]),
                    value_columns=list(arguments["value_columns"]),
                    names_to=str(arguments.get("names_to", "variable")),
                    values_to=str(arguments.get("values_to", "value")),
                )
            else:
                updated = pivot_wider(
                    obj,
                    id_columns=list(arguments["id_columns"]),
                    names_from=str(arguments["names_from"]),
                    values_from=str(arguments["values_from"]),
                )
            self.store.save(updated)
            data = {
                "dataset_id": updated.dataset_id,
                "revision": updated.revision,
                "parent_revision": obj.revision,
                "n": len(updated.records),
                "columns": list(updated.columns),
                "operation": updated.operation,
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
                    strategy=cast(Literal["mean", "median", "mode"], str(arguments["strategy"])),
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
            if operation in {"statistics.auto_plan", "statistics.auto_analyze"}:
                request = AnalysisRequest(
                    mode=cast(Any, str(arguments["mode"])),
                    design=cast(Any, str(arguments["design"])),
                    outcome=(
                        str(arguments["outcome"]) if arguments.get("outcome") is not None else None
                    ),
                    outcome_type=(
                        cast(Any, str(arguments["outcome_type"]))
                        if arguments.get("outcome_type") is not None
                        else None
                    ),
                    group=(str(arguments["group"]) if arguments.get("group") is not None else None),
                    levels=tuple(str(value) for value in arguments.get("levels", [])),
                    predictors=tuple(str(value) for value in arguments.get("predictors", [])),
                    items=tuple(str(value) for value in arguments.get("items", [])),
                    paired_with=(
                        str(arguments["paired_with"])
                        if arguments.get("paired_with") is not None
                        else None
                    ),
                    variables=tuple(str(value) for value in arguments.get("variables", [])),
                    seed=int(arguments.get("seed", 0)),
                    max_operations=int(arguments.get("max_operations", 24)),
                )
                automatic_plan = plan_automatic_analysis(obj, request)
                data = {"plan": automatic_plan.as_json()}
                if operation == "statistics.auto_analyze":
                    identity = {"dataset_id": obj.dataset_id, "revision": obj.revision}
                    diagnostics: list[dict[str, Any]] = []
                    diagnostic_requests: list[tuple[str, dict[str, Any], str]] = [
                        (
                            "dataset.missingness",
                            dict(identity),
                            "Inspect missingness before selecting or interpreting procedures.",
                        ),
                        (
                            "dataset.quality",
                            {
                                **identity,
                                **(
                                    {
                                        "outcome": request.outcome,
                                        "predictors": list(request.predictors),
                                    }
                                    if request.outcome and request.predictors
                                    else {}
                                ),
                            },
                            (
                                "Run deterministic data-quality checks before inferential "
                                "interpretation."
                            ),
                        ),
                    ]
                    for index, (child_operation, child_arguments, reason) in enumerate(
                        diagnostic_requests
                    ):
                        child = self.execute(
                            child_operation,
                            child_arguments,
                            {"request_id": f"{request_id}:auto-diagnostic-{index + 1}"},
                        )
                        diagnostics.append(
                            {
                                "operation": child_operation,
                                "reason": reason,
                                "status": child.get("status"),
                                "data": child.get("data", {}),
                                "error": child.get("error"),
                            }
                        )

                    executions: list[dict[str, Any]] = []
                    for index, step in enumerate(automatic_plan.steps):
                        child = self.execute(
                            step.operation,
                            step.arguments,
                            {"request_id": f"{request_id}:auto-step-{index + 1}"},
                        )
                        executions.append(
                            {
                                "operation": step.operation,
                                "reason": step.reason,
                                "exclusions": list(step.exclusions),
                                "status": child.get("status"),
                                "data": child.get("data", {}),
                                "error": child.get("error"),
                            }
                        )
                    failures = [
                        {
                            "operation": entry["operation"],
                            "error": entry["error"],
                        }
                        for entry in [*diagnostics, *executions]
                        if entry["status"] != "ok"
                    ]
                    execution_payload = [
                        {
                            "operation": entry["operation"],
                            "status": entry["status"],
                            "data": entry["data"],
                            "error": entry["error"],
                        }
                        for entry in [*diagnostics, *executions]
                    ]
                    exclusions = []
                    if request.design == "descriptive":
                        exclusions.append(
                            "Inferential procedures were not selected because no inferential "
                            "study design was declared."
                        )
                    if request.mode == "compare-groups":
                        exclusions.append(
                            "Alternative tests were not selected from observed p-values or effect "
                            "sizes; the declared design determines the primary procedure."
                        )
                    if request.mode == "predict-outcome":
                        exclusions.append(
                            "Other model families were excluded by the declared outcome type."
                        )
                    data.update(
                        {
                            "diagnostics": diagnostics,
                            "executions": executions,
                            "failures": failures,
                            "report": {
                                "mode": request.mode,
                                "design": request.design,
                                "dataset_id": obj.dataset_id,
                                "dataset_revision": obj.revision,
                                "selected_methods": [
                                    step.operation for step in automatic_plan.steps
                                ],
                                "excluded_methods": exclusions,
                                "selection_rule": (
                                    "Methods are chosen only from explicit design/variable roles "
                                    "and predeclared deterministic rules. Observed significance "
                                    "never changes method selection."
                                ),
                                "multiple_testing_note": (
                                    "Treat automatically generated exploratory analyses as "
                                    "exploratory; prespecify confirmatory families and correction "
                                    "rules before confirmatory inference."
                                ),
                                "warnings": list(automatic_plan.warnings),
                            },
                            "execution_manifest": {
                                **automatic_plan.manifest,
                                "execution_sha256": digest(execution_payload),
                                "successful_operations": sum(
                                    entry["status"] == "ok" for entry in [*diagnostics, *executions]
                                ),
                                "failed_operations": len(failures),
                            },
                        }
                    )
            elif operation == "statistics.describe":
                data = describe(obj, str(arguments["column"]))
            elif operation == "statistics.frequency":
                data = frequency_table(obj, str(arguments["column"]))
            elif operation == "statistics.grouped_describe":
                data = grouped_describe(obj, str(arguments["column"]), str(arguments["group"]))
            elif operation == "statistics.available_case":
                data = available_case_covariance(obj, list(arguments["columns"]))
            elif operation == "statistics.distribution":
                data = distribution_diagnostics(obj, str(arguments["column"]))
            elif operation == "dataset.missingness":
                data = missingness(obj, by=arguments.get("by"))
            elif operation == "dataset.quality":
                data = quality_screen(
                    obj,
                    subject_column=arguments.get("subject_column"),
                    outcome=arguments.get("outcome"),
                    predictors=list(arguments.get("predictors", [])),
                    split_column=arguments.get("split_column"),
                    train_values=list(arguments.get("train_values", [])) or None,
                    test_values=list(arguments.get("test_values", [])) or None,
                    outlier_threshold=float(arguments.get("outlier_threshold", 3.0)),
                )
            elif operation == "statistics.weighted_mean":
                data = frequency_weighted_mean(
                    obj, str(arguments["column"]), str(arguments["weight"])
                )
            elif operation == "statistics.analytic_weighted_mean":
                data = analytic_weighted_mean(
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
            elif operation == "statistics.correlation_matrix":
                data = correlation_matrix(
                    obj,
                    list(arguments["columns"]),
                    method=str(arguments.get("method", "pearson")),
                    adjustment=str(arguments.get("adjustment", "holm")),
                )
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
                    cluster_group=arguments.get("cluster_group"),
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
            elif operation == "statistics.negative_binomial":
                data = negative_binomial_regression(
                    obj,
                    str(arguments["outcome"]),
                    list(arguments["predictors"]),
                    alpha=float(arguments.get("alpha", 1.0)),
                    offset=arguments.get("offset"),
                ).as_json()
            elif operation == "statistics.negative_binomial_estimated":
                data = estimated_negative_binomial_regression(
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
                    order_values = [int(value) for value in arguments["order"]]
                    seasonal_values = [
                        int(value) for value in arguments.get("seasonal_order", [0, 0, 0, 0])
                    ]
                    require(len(order_values) == 3, "ARIMA order must have three integers")
                    require(
                        len(seasonal_values) == 4,
                        "Seasonal ARIMA order must have four integers",
                    )
                    data = arima_forecast(
                        chronology,
                        order=(order_values[0], order_values[1], order_values[2]),
                        seasonal_order=(
                            seasonal_values[0],
                            seasonal_values[1],
                            seasonal_values[2],
                            seasonal_values[3],
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
                    x_label=arguments.get("x_label"),
                    y_label=arguments.get("y_label"),
                    title=str(arguments.get("title", "")),
                    options=dict(arguments.get("options", {})),
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
