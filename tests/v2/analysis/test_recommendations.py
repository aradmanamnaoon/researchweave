import pytest

from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.recommendations import (
    AnalysisDesign,
    recommend_analysis,
    recommend_from_mapping,
)


@pytest.mark.parametrize(
    ("design", "primary", "rule"),
    [
        (
            AnalysisDesign("binary", predictors=2, research_goal="model"),
            "statistics.logistic",
            "binary-model",
        ),
        (
            AnalysisDesign("count", predictors=1, research_goal="model"),
            "statistics.poisson",
            "count-model",
        ),
        (
            AnalysisDesign("ordinal", predictors=1, research_goal="model"),
            "statistics.ordinal",
            "ordinal-model",
        ),
        (AnalysisDesign("time_to_event", groups=2), "statistics.logrank", "survival-two-groups"),
        (AnalysisDesign("continuous", groups=3), "statistics.anova", "continuous-multi-group"),
        (AnalysisDesign("continuous", paired=True), "statistics.test", "continuous-paired"),
        (
            AnalysisDesign("continuous", repeated=True),
            "statistics.repeated_anova",
            "continuous-repeated",
        ),
        (
            AnalysisDesign("continuous", predictors=2, covariates=1, groups=2),
            "statistics.ancova",
            "continuous-group-covariates",
        ),
        (
            AnalysisDesign("categorical", survey_design=True),
            "statistics.survey_proportions",
            "survey-categorical",
        ),
    ],
)
def test_design_rules_are_deterministic_and_never_result_driven(design, primary, rule):
    first = recommend_analysis(design)
    second = recommend_analysis(design)
    assert first == second
    assert first["primary_operation"] == primary
    assert first["rule_id"] == rule
    assert first["integrity"]["uses_observed_results"] is False
    assert first["integrity"]["selection_basis"] == "declared study design only"
    assert first["integrity"]["preregistration_note"]
    assert first["integrity"]["multiplicity_note"]


def test_recommendations_record_alternatives_and_limitations_for_ambiguous_designs():
    two_group = recommend_analysis(AnalysisDesign("continuous", groups=2))
    assert {item["operation"] for item in two_group["alternatives"]} == {
        "statistics.rank",
        "statistics.welch_anova",
    }
    count = recommend_analysis(AnalysisDesign("count", predictors=2, research_goal="model"))
    assert any("overdispersion" in item for item in count["limitations"])
    forecast = recommend_analysis(
        AnalysisDesign("continuous", time_ordered=True, research_goal="forecast")
    )
    assert forecast["alternatives"][0]["operation"] == "statistics.adf"
    assert forecast["limitations"]
    unsupported = recommend_analysis(AnalysisDesign("binary", survey_design=True, predictors=2))
    assert unsupported["primary_operation"] == "unsupported"
    assert unsupported["limitations"]


@pytest.mark.parametrize(
    "field",
    ["p_value", "p_values", "effect", "effect_size", "estimate", "significant", "best_result"],
)
def test_observed_result_fields_are_rejected_as_cherry_picking_inputs(field):
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        recommend_from_mapping({"outcome_type": "continuous", "groups": 2, field: 0.01})


def test_invalid_or_ambiguous_design_declarations_fail_typed_validation():
    with pytest.raises(AnalysisError, match="Group count"):
        recommend_analysis(AnalysisDesign("continuous", groups=-1))
    with pytest.raises(AnalysisError, match="categorical predictor"):
        recommend_analysis(AnalysisDesign("continuous", predictors=1, categorical_predictors=2))
    with pytest.raises(AnalysisError, match="Paired comparison"):
        recommend_analysis(AnalysisDesign("continuous", groups=3, paired=True))
    with pytest.raises(AnalysisError, match="Unknown design field"):
        recommend_from_mapping({"outcome_type": "continuous", "unknown": True})
