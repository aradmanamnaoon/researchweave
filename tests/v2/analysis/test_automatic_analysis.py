"""Contract tests for deterministic, declarative statistical planning."""

from dataclasses import replace

import pytest

from researchweave.analysis.automatic import (
    AnalysisRequest,
    plan_automatic_analysis,
    profile_columns,
)
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.models import Dataset, Variable
from researchweave.analysis.schemas import validate_arguments


@pytest.fixture
def dataset() -> Dataset:
    return Dataset(
        dataset_id="d1",
        revision="r1",
        parent_revision=None,
        source_hash="sha256-fixture",
        created_at="2026-01-01T00:00:00Z",
        columns=("score", "group", "other", "item"),
        variables=(
            Variable("score", dtype="number", missing_values=("999",)),
            Variable("group"),
            Variable("other", dtype="number"),
            Variable("item", dtype="number"),
        ),
        records=(
            {"score": 1.0, "group": "A", "other": 3, "item": 2},
            {"score": 2.0, "group": "B", "other": 4, "item": 3},
            {"score": 999, "group": "A", "other": None, "item": 4},
            {"score": None, "group": "B", "other": 5, "item": 3},
        ),
        operation={"type": "fixture"},
    )


def test_profiles_preserve_declared_type_and_user_missing(dataset: Dataset) -> None:
    profiles = {p.name: p for p in profile_columns(dataset)}
    assert (profiles["score"].n_valid, profiles["score"].n_missing) == (2, 2)
    assert profiles["group"].observed_kind == "text"
    assert profiles["group"].distinct_values == 2
    assert profiles["other"].observed_kind == "number"
    assert profiles["item"].declared_dtype == "number"


@pytest.mark.parametrize(
    "spec,expected",
    [
        (
            AnalysisRequest("explore", "descriptive"),
            ("statistics.describe", "statistics.frequency"),
        ),
        (
            AnalysisRequest(
                "compare-groups",
                "independent",
                outcome="score",
                outcome_type="continuous",
                group="group",
                levels=("A", "B"),
            ),
            ("statistics.test",),
        ),
        (
            AnalysisRequest(
                "compare-groups",
                "paired",
                outcome="score",
                outcome_type="continuous",
                paired_with="other",
            ),
            ("statistics.test",),
        ),
        (
            AnalysisRequest("relationships", "observational", variables=("score", "other")),
            ("statistics.correlation_matrix",),
        ),
        (
            AnalysisRequest("questionnaire", "descriptive", items=("score", "item")),
            ("statistics.psychometric",),
        ),
        (
            AnalysisRequest(
                "predict-outcome",
                "observational",
                outcome="score",
                outcome_type="continuous",
                predictors=("other",),
            ),
            ("statistics.model",),
        ),
        (
            AnalysisRequest("comprehensive", "descriptive"),
            ("statistics.describe", "statistics.frequency"),
        ),
    ],
)
def test_selection_validates_registered_argument_schemas(
    dataset: Dataset, spec: AnalysisRequest, expected: tuple[str, ...]
) -> None:
    plan = plan_automatic_analysis(dataset, spec)
    operations = tuple(step.operation for step in plan.steps)
    assert set(operations) == set(expected)
    for step in plan.steps:
        validate_arguments(step.operation, step.arguments)
        assert step.reason and step.exclusions


def test_manifest_and_plan_are_deterministic(dataset: Dataset) -> None:
    spec = AnalysisRequest(
        "compare-groups",
        "independent",
        outcome="score",
        outcome_type="continuous",
        group="group",
        levels=("A", "B"),
    )
    a = plan_automatic_analysis(dataset, spec)
    b = plan_automatic_analysis(dataset, spec)
    assert a.as_json() == b.as_json()
    assert len(a.manifest["plan_sha256"]) == 64
    assert a.steps[0].arguments["options"]["equal_variance"] is False
    assert a.manifest["selection_basis"].startswith("explicit roles")


@pytest.mark.parametrize(
    "spec",
    [
        AnalysisRequest(
            "compare-groups", "descriptive", outcome="score", outcome_type="continuous"
        ),
        AnalysisRequest(
            "compare-groups",
            "independent",
            outcome="score",
            outcome_type="continuous",
            group="group",
        ),
        AnalysisRequest("compare-groups", "paired", outcome="score", outcome_type="continuous"),
        AnalysisRequest("predict-outcome", "observational", outcome="score", predictors=("other",)),
        AnalysisRequest(
            "predict-outcome",
            "observational",
            outcome="score",
            outcome_type="ordinal",
            predictors=("other",),
        ),
        AnalysisRequest("relationships", "observational", variables=("score",)),
        AnalysisRequest("questionnaire", "descriptive", items=("score",)),
        AnalysisRequest("comprehensive", "survey"),
        AnalysisRequest("explore", "repeated"),
        AnalysisRequest("explore", "survey"),
        AnalysisRequest(
            "predict-outcome",
            "observational",
            outcome="score",
            outcome_type="continuous",
            predictors=("missing",),
        ),
    ],
)
def test_ambiguous_or_unsupported_design_refused(dataset: Dataset, spec: AnalysisRequest) -> None:
    with pytest.raises(AnalysisError):
        plan_automatic_analysis(dataset, spec)


def test_budget_and_revision_change_are_provenance_sensitive(dataset: Dataset) -> None:
    spec = AnalysisRequest("explore", "descriptive", max_operations=2)
    with pytest.raises(AnalysisError, match="budget"):
        plan_automatic_analysis(dataset, spec)
    allowed = replace(spec, max_operations=4)
    first = plan_automatic_analysis(dataset, allowed)
    revised = plan_automatic_analysis(replace(dataset, revision="r2"), allowed)
    assert first.manifest["plan_sha256"] != revised.manifest["plan_sha256"]
