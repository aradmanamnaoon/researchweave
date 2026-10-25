"""Conservative compatibility matrix for the desktop statistical workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from researchweave.analysis.script_exports import R_MAPPED_OPERATIONS

Coverage = Literal["Broad", "Partial", "Limited", "Unavailable"]


@dataclass(frozen=True)
class ProcedureFamily:
    name: str
    operations: tuple[str, ...]
    coverage: Coverage
    limitation: str


_FAMILIES: tuple[ProcedureFamily, ...] = (
    ProcedureFamily(
        "Descriptives & frequencies",
        (
            "analysis.statistics.describe",
            "analysis.statistics.frequency",
            "analysis.statistics.grouped_describe",
        ),
        "Broad",
        "Core summaries and frequency workflows are implemented; output options differ from SPSS.",
    ),
    ProcedureFamily(
        "t tests / compare means",
        ("analysis.statistics.test",),
        "Broad",
        "One-sample, paired and independent/Welch designs are covered with CI and effect sizes.",
    ),
    ProcedureFamily(
        "Correlation",
        ("analysis.statistics.correlate", "analysis.statistics.correlation_matrix"),
        "Broad",
        "Pearson/Spearman/Kendall workflows are covered; SPSS table styling/options differ.",
    ),
    ProcedureFamily(
        "Nonparametric tests",
        (
            "analysis.statistics.rank",
            "analysis.statistics.wilcoxon",
            "analysis.statistics.kruskal",
            "analysis.statistics.friedman",
        ),
        "Broad",
        "Major rank-based tests are implemented; exact-test option breadth is narrower than SPSS.",
    ),
    ProcedureFamily(
        "ANOVA / GLM",
        (
            "analysis.statistics.anova",
            "analysis.statistics.welch_anova",
            "analysis.statistics.tukey",
            "analysis.statistics.factorial_anova",
            "analysis.statistics.repeated_anova",
            "analysis.statistics.ancova",
        ),
        "Partial",
        (
            "Core ANOVA/ANCOVA designs exist; contrasts, estimated marginal means and full "
            "GLM options are incomplete."
        ),
    ),
    ProcedureFamily(
        "Regression",
        (
            "analysis.statistics.model",
            "analysis.statistics.logistic",
            "analysis.statistics.poisson",
            "analysis.statistics.negative_binomial",
        ),
        "Partial",
        (
            "Linear and major generalized models exist; selection diagnostics and SPSS option "
            "parity are incomplete."
        ),
    ),
    ProcedureFamily(
        "Mixed models & GEE",
        ("analysis.statistics.mixed_effects", "analysis.statistics.gee"),
        "Partial",
        (
            "Core mixed/GEE workflows exist; covariance structures and post-hoc option breadth "
            "are limited."
        ),
    ),
    ProcedureFamily(
        "Survival analysis",
        (
            "analysis.statistics.survival",
            "analysis.statistics.logrank",
            "analysis.statistics.cox",
        ),
        "Partial",
        (
            "Kaplan-Meier style estimates, log-rank and Cox models exist; advanced survival "
            "options are incomplete."
        ),
    ),
    ProcedureFamily(
        "Reliability & scale analysis",
        (
            "analysis.statistics.psychometric",
            "analysis.statistics.reliability_diagnostics",
            "analysis.statistics.item_total",
        ),
        "Partial",
        (
            "Reliability and item diagnostics are implemented; the full SPSS scale-analysis "
            "option set is not replicated."
        ),
    ),
    ProcedureFamily(
        "Dimension reduction & clustering",
        (
            "analysis.statistics.pca",
            "analysis.statistics.efa",
            "analysis.statistics.kmeans",
            "analysis.statistics.hierarchical",
            "analysis.statistics.cluster_validation",
        ),
        "Partial",
        (
            "PCA/EFA and common clustering workflows exist; broader SPSS multivariate tooling "
            "remains incomplete."
        ),
    ),
    ProcedureFamily(
        "Complex survey",
        ("analysis.statistics.survey_mean", "analysis.statistics.survey_proportions"),
        "Limited",
        (
            "Design-weighted means/proportions exist; full complex-samples modeling is not "
            "implemented."
        ),
    ),
    ProcedureFamily(
        "Time series",
        (
            "analysis.statistics.adf",
            "analysis.statistics.ljung_box",
            "analysis.statistics.seasonal_decompose",
            "analysis.statistics.arima_forecast",
        ),
        "Partial",
        (
            "Core diagnostics/decomposition/ARIMA exist; expert-modeler breadth and seasonal "
            "tooling are incomplete."
        ),
    ),
    ProcedureFamily(
        "Power & sample size",
        (
            "analysis.statistics.power",
            "analysis.statistics.required_n",
            "analysis.statistics.power_one_sample",
            "analysis.statistics.power_proportion",
            "analysis.statistics.required_n_proportion",
            "analysis.statistics.required_n_precision",
        ),
        "Partial",
        (
            "Common power/sample-size calculations exist; not every SPSS procedure has a "
            "matching power workflow."
        ),
    ),
    ProcedureFamily(
        "Meta-analysis",
        (
            "analysis.statistics.meta",
            "analysis.statistics.meta_random",
            "analysis.statistics.egger",
        ),
        "Partial",
        (
            "Fixed/random effects and Egger diagnostics exist; advanced meta-analysis options "
            "are narrower."
        ),
    ),
    ProcedureFamily(
        "Multivariate GLM / MANOVA",
        (),
        "Unavailable",
        "No dedicated MANOVA/MANCOVA operation is currently registered.",
    ),
    ProcedureFamily(
        "Discriminant / ROC classification",
        (),
        "Unavailable",
        "No dedicated discriminant-analysis or ROC procedure is currently registered.",
    ),
)


def _method_label(operation: str) -> str:
    return operation.removeprefix("analysis.statistics.").replace("_", " ")


def build_compatibility_rows(methods: Sequence[Mapping[str, object]]) -> list[list[str]]:
    """Build a live matrix without claiming equivalence beyond registered operations."""

    available = {
        str(method.get("id"))
        for method in methods
        if method.get("available") is True and isinstance(method.get("id"), str)
    }
    python_replay = "analysis.syntax.python" in available
    r_syntax = "analysis.syntax.r" in available
    r_runtime = "analysis.runtime.r" in available
    rows: list[list[str]] = []
    for family in _FAMILIES:
        implemented = [operation for operation in family.operations if operation in available]
        if not family.operations or not implemented:
            coverage: Coverage = "Unavailable"
        elif len(implemented) < len(family.operations):
            coverage = "Partial"
        else:
            coverage = family.coverage
        methods_text = ", ".join(_method_label(operation) for operation in implemented) or "—"
        mapped_r = [
            operation
            for operation in implemented
            if operation.removeprefix("analysis.") in R_MAPPED_OPERATIONS
        ]
        if not implemented:
            reproducibility = "—"
        elif python_replay and r_syntax and len(mapped_r) == len(implemented):
            reproducibility = "Python replay; mapped R syntax"
        elif python_replay and r_syntax and mapped_r:
            mapped = ", ".join(_method_label(operation) for operation in mapped_r)
            suffix = "; custom R for remaining methods" if r_runtime else ""
            reproducibility = f"Python replay; mapped R: {mapped}{suffix}"
        elif python_replay and r_runtime:
            reproducibility = "Python replay; custom R runtime only"
        elif python_replay:
            reproducibility = "Python replay"
        else:
            reproducibility = "Native ResearchWeave kernel"
        if family.operations and len(implemented) < len(family.operations):
            missing = [operation for operation in family.operations if operation not in available]
            limitation = (
                f"{family.limitation} Missing registered operations: "
                f"{', '.join(_method_label(operation) for operation in missing)}."
            )
        else:
            limitation = family.limitation
        rows.append([family.name, coverage, methods_text, reproducibility, limitation])
    return rows


COMPATIBILITY_COLUMNS = ["Procedure family", "Coverage", "Methods", "Reproducibility", "Limits"]
