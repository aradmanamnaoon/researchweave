from __future__ import annotations

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.planner import PlanCompiler, PlannedStep, ToolManifest


def make_compiler():
    return PlanCompiler(
        [
            ToolManifest("evidence.search", "read", required_arguments=("query",)),
            ToolManifest("evidence.save", "local-write", required_arguments=("title",)),
            ToolManifest(
                "cloud.send", "sensitive-egress", required_arguments=("content",), offline=False
            ),
        ]
    )


def test_graph_topological_order_and_approval_preview():
    compiler = make_compiler()
    plan = compiler.compile(
        "project",
        [
            PlannedStep("save", "evidence.save", {"title": "draft"}, ("search",)),
            PlannedStep("search", "evidence.search", {"query": "memory"}),
        ],
    )
    assert [step.step_id for step in plan.steps] == ["search", "save"]
    assert plan.requires_approval == ("save",)
    assert plan.estimated_effects == {"read": 1, "local-write": 1}
    assert plan.public_preview()["steps"][0]["arguments_digest"]
    assert plan.to_runtime_steps()[1]["arguments"] == {"title": "draft"}


def test_human_revision_recompiles_and_invalidates_approval():
    compiler = make_compiler()
    first = compiler.compile("p", [PlannedStep("save", "evidence.save", {"title": "original"})])
    revised = compiler.revise(first, {"save": {"title": "corrected"}})
    assert revised.plan_digest != first.plan_digest
    assert revised.requires_approval == ("save",)
    assert "reapprove" in revised.warnings[0]
    with pytest.raises(AIError) as error:
        compiler.revise(first, {"save": {"title": "corrected", "approved": True}})
    assert error.value.code == "SCHEMA_MISMATCH"


@pytest.mark.parametrize(
    "steps,code",
    [
        ([PlannedStep("x", "evidence.search", {"query": "a"}, ("y",))], "NOT_FOUND"),
        ([PlannedStep("x", "evidence.search", {"query": "a"}, ("x",))], "INVALID_INPUT"),
        (
            [
                PlannedStep("x", "evidence.search", {"query": "a"}, ("y",)),
                PlannedStep("y", "evidence.save", {"title": "b"}, ("x",)),
            ],
            "CONFLICT",
        ),
        ([PlannedStep("x", "unknown.tool", {})], "NOT_FOUND"),
        ([PlannedStep("x", "evidence.save", {"approved": True})], "SCHEMA_MISMATCH"),
    ],
)
def test_invalid_graph_denied_before_any_tool_execution(steps, code):
    with pytest.raises(AIError) as error:
        make_compiler().compile("p", steps)
    assert error.value.code == code


def test_cloud_tool_denied_offline():
    with pytest.raises(AIError) as error:
        make_compiler().compile("p", [PlannedStep("c", "cloud.send", {"content": "x"})])
    assert error.value.code == "OFFLINE_DENIED"
