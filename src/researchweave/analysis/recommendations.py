"""Deterministic design-based analysis recommendations without result cherry-picking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .errors import require

OutcomeType = Literal["continuous", "binary", "count", "ordinal", "categorical", "time_to_event"]


@dataclass(frozen=True)
class AnalysisDesign:
    outcome_type: OutcomeType
    groups: int = 0
    paired: bool = False
    repeated: bool = False
    predictors: int = 0
    categorical_predictors: int = 0
    covariates: int = 0
    clustered: bool = False
    survey_design: bool = False
    time_ordered: bool = False
    censoring: bool = False
    research_goal: Literal["describe", "compare", "associate", "model", "forecast"] = "compare"

    def validate(self) -> None:
        require(
            self.outcome_type
            in {"continuous", "binary", "count", "ordinal", "categorical", "time_to_event"},
            "Unsupported outcome type",
        )
        require(0 <= self.groups <= 100, "Group count outside supported range")
        require(0 <= self.predictors <= 100, "Predictor count outside supported range")
        require(
            0 <= self.categorical_predictors <= self.predictors,
            "Invalid categorical predictor count",
        )
        require(0 <= self.covariates <= self.predictors, "Invalid covariate count")
        require(not (self.paired and self.groups > 2), "Paired comparison supports two conditions")
        require(
            not (self.repeated and self.paired),
            "Use repeated design for more than paired conditions",
        )


def recommend_analysis(design: AnalysisDesign) -> dict[str, Any]:
    """Recommend from declared design only; observed p-values/effects are never inputs."""

    design.validate()
    primary = ""
    alternatives: list[dict[str, str]] = []
    assumptions: list[str] = []
    limitations: list[str] = []
    rule = ""
    if design.survey_design:
        if design.outcome_type == "continuous" and design.research_goal in {"describe", "compare"}:
            primary = "statistics.survey_mean"
            rule = "survey-continuous"
        elif design.outcome_type == "categorical":
            primary = "statistics.survey_proportions"
            rule = "survey-categorical"
        else:
            primary = "unsupported"
            rule = "survey-unsupported-model"
            limitations.append("Complex-survey regression for this outcome is not implemented")
        assumptions.append("Weights, strata and PSU identifiers must describe the sampling design")
    elif design.outcome_type == "time_to_event" or design.censoring:
        if design.predictors > 0:
            primary = "statistics.cox"
            rule = "survival-modeled"
            assumptions.append("Proportional hazards requires diagnostic review")
        elif design.groups == 2:
            primary = "statistics.logrank"
            rule = "survival-two-groups"
            alternatives.append(
                {"operation": "statistics.survival", "reason": "Estimate group curves"}
            )
        else:
            primary = "statistics.survival"
            rule = "survival-descriptive"
    elif design.time_ordered or design.research_goal == "forecast":
        primary = "statistics.time_features"
        rule = "time-ordered"
        alternatives.append(
            {"operation": "statistics.adf", "reason": "Review unit-root stationarity"}
        )
        limitations.append(
            "Forecast model choice also depends on frequency, seasonality and validation horizon"
        )
    elif design.outcome_type == "ordinal":
        primary = "statistics.ordinal"
        rule = "ordinal-model"
        assumptions.append(
            "Declared category ordering and proportional-odds assumptions must be defensible"
        )
    elif design.outcome_type == "count":
        primary = "statistics.poisson"
        rule = "count-model"
        limitations.append(
            "Check overdispersion and excess zeros before relying on Poisson inference"
        )
    elif design.outcome_type == "binary":
        if design.predictors > 0:
            primary = "statistics.logistic"
            rule = "binary-model"
        else:
            primary = "statistics.contingency"
            rule = "binary-table"
        assumptions.append("Event coding must be declared before model fitting")
    elif design.outcome_type == "categorical":
        primary = "statistics.contingency"
        rule = "categorical-association"
        limitations.append("Sparse expected cells may require Fisher exact or another exact design")
    elif design.outcome_type == "continuous":
        if design.clustered:
            primary = "statistics.mixed_effects"
            rule = "continuous-clustered"
            alternatives.append(
                {"operation": "statistics.gee", "reason": "Population-average estimand"}
            )
        elif design.repeated:
            primary = "statistics.repeated_anova"
            rule = "continuous-repeated"
            alternatives.append(
                {
                    "operation": "statistics.mixed_effects",
                    "reason": "Flexible incomplete/repeated structure",
                }
            )
        elif design.covariates > 0 and design.groups >= 2:
            primary = "statistics.ancova"
            rule = "continuous-group-covariates"
        elif design.predictors > 1 and design.categorical_predictors >= 2:
            primary = "statistics.factorial_anova"
            rule = "continuous-factorial"
        elif design.predictors > 0 and design.research_goal in {"associate", "model"}:
            primary = "statistics.model"
            rule = "continuous-regression"
        elif design.paired:
            primary = "statistics.test"
            rule = "continuous-paired"
            alternatives.append(
                {
                    "operation": "statistics.wilcoxon",
                    "reason": "Ordinal/rank or strong outlier sensitivity",
                }
            )
        elif design.groups == 2:
            primary = "statistics.test"
            rule = "continuous-two-groups"
            alternatives.extend(
                [
                    {"operation": "statistics.rank", "reason": "Rank-based independent comparison"},
                    {
                        "operation": "statistics.welch_anova",
                        "reason": "Equivalent unequal-variance omnibus framing",
                    },
                ]
            )
        elif design.groups > 2:
            primary = "statistics.anova"
            rule = "continuous-multi-group"
            alternatives.extend(
                [
                    {"operation": "statistics.welch_anova", "reason": "Unequal variances"},
                    {"operation": "statistics.kruskal", "reason": "Rank-based group comparison"},
                ]
            )
        else:
            primary = "statistics.describe"
            rule = "continuous-descriptive"
    else:
        primary = "unsupported"
        rule = "unsupported"
    return {
        "primary_operation": primary,
        "rule_id": rule,
        "alternatives": alternatives,
        "assumptions": assumptions,
        "limitations": limitations,
        "decision_inputs": {
            "outcome_type": design.outcome_type,
            "groups": design.groups,
            "paired": design.paired,
            "repeated": design.repeated,
            "predictors": design.predictors,
            "categorical_predictors": design.categorical_predictors,
            "covariates": design.covariates,
            "clustered": design.clustered,
            "survey_design": design.survey_design,
            "time_ordered": design.time_ordered,
            "censoring": design.censoring,
            "research_goal": design.research_goal,
        },
        "integrity": {
            "uses_observed_results": False,
            "selection_basis": "declared study design only",
            "preregistration_note": (
                "Choose the primary analysis before inspecting inferential results "
                "when confirmatory claims are intended"
            ),
            "multiplicity_note": (
                "Prespecify hypothesis families and correction when multiple "
                "confirmatory tests are planned"
            ),
        },
    }


def recommend_from_mapping(specification: dict[str, Any]) -> dict[str, Any]:
    """Strict mapping adapter; rejects result fields that could enable cherry-picking."""

    forbidden = {
        "p_value",
        "p_values",
        "effect",
        "effect_size",
        "estimate",
        "significant",
        "best_result",
    }
    require(
        not (set(specification) & forbidden),
        "Observed results cannot drive analysis selection",
        "INTEGRITY_FAILURE",
    )
    allowed = {
        "outcome_type",
        "groups",
        "paired",
        "repeated",
        "predictors",
        "categorical_predictors",
        "covariates",
        "clustered",
        "survey_design",
        "time_ordered",
        "censoring",
        "research_goal",
    }
    require(set(specification) <= allowed, "Unknown design field")
    return recommend_analysis(AnalysisDesign(**specification))
