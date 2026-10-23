import json
import math
from pathlib import Path

import pytest

from researchweave.analysis.coding_review import CodingReviewLedger
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.missing_data import (
    available_case_covariance,
    complete_case,
    multiple_impute_normal,
    pool_scalar_rubin,
    simple_impute,
)
from researchweave.analysis.qualitative import Code, Transcript
from researchweave.analysis.qualitative_store import Memo, QualitativeState, QualitativeStore
from researchweave.analysis.recommendations import (
    AnalysisDesign,
    recommend_analysis,
    recommend_from_mapping,
)


def _table(tmp_path: Path, content: str):
    path = tmp_path / "data.csv"
    path.write_text(content, encoding="utf-8")
    return import_csv(path)


def test_complete_available_and_simple_imputation(tmp_path: Path):
    dataset = _table(tmp_path, "id,x,y\na,1,2\nb,,4\nc,3,\nd,5,8\n")
    complete, receipt = complete_case(dataset, ["x", "y"])
    assert receipt["n_used"] == 2
    assert [row["id"] for row in complete.records] == ["a", "d"]
    pairwise = available_case_covariance(dataset, ["x", "y"])
    assert pairwise["pairwise_n"] == [[3, 2], [2, 3]]
    imputed, operation = simple_impute(dataset, "x", strategy="mean")
    assert operation["fill_value"] == pytest.approx(3)
    assert imputed.records[1]["x"] == pytest.approx(3)
    assert dataset.records[1]["x"] is None


def test_multiple_imputation_is_seeded_preserves_observed_and_pools(tmp_path: Path):
    dataset = _table(
        tmp_path,
        "x,y,z\n1,2,3\n2,4,6\n3,,9\n4,8,12\n,10,15\n6,12,18\n",
    )
    first = multiple_impute_normal(dataset, ["x", "y", "z"], m=4, seed=19)
    second = multiple_impute_normal(dataset, ["x", "y", "z"], m=4, seed=19)
    assert [item.revision for item in first.datasets] == [item.revision for item in second.datasets]
    assert all(item.records[0]["x"] == "1" for item in first.datasets)
    imputed_y = [float(item.records[2]["y"]) for item in first.datasets]
    assert len(set(imputed_y)) > 1
    pooled = pool_scalar_rubin([1.0, 1.2, 0.8, 1.1], [0.04, 0.05, 0.04, 0.06])
    assert pooled["estimate"] == pytest.approx(1.025)
    assert pooled["total_variance"] > pooled["within_variance"]


def test_recommendations_use_design_not_observed_results():
    result = recommend_analysis(
        AnalysisDesign(outcome_type="continuous", groups=3, research_goal="compare")
    )
    assert result["primary_operation"] == "statistics.anova"
    assert {item["operation"] for item in result["alternatives"]} == {
        "statistics.welch_anova",
        "statistics.kruskal",
    }
    assert result["integrity"]["uses_observed_results"] is False
    clustered = recommend_analysis(
        AnalysisDesign(
            outcome_type="continuous", predictors=1, clustered=True, research_goal="model"
        )
    )
    assert clustered["primary_operation"] == "statistics.mixed_effects"
    with pytest.raises(AnalysisError, match="Observed results"):
        recommend_from_mapping({"outcome_type": "continuous", "groups": 2, "p_value": 0.2})


def test_qualitative_store_restart_history_memo_and_tamper(tmp_path: Path):
    state = QualitativeState()
    state.project.add_transcript(Transcript("source", "alpha beta gamma", "case1"))
    state.add_code(Code("parent", "Parent"), actor="alice")
    state.add_code(Code("child", "Child", parent="parent"), actor="alice")
    annotation = state.project.annotate("source", 0, 5, "child", "alice", "u1")
    reviewer = CodingReviewLedger(state.project)
    reviewer.decide(0, "accept", reviewer="reviewer1", rationale="Matches code definition")
    reviewer.decide(0, "reject", reviewer="reviewer2", rationale="Boundary is too broad")
    state.attach_review_ledger(reviewer)
    state.add_memo(
        Memo(
            "memo1",
            "Decision",
            "Keep context",
            "alice",
            "2026-10-23T00:00:00+00:00",
            source_id="source",
        )
    )
    state.update_code("child", actor="bob", description="Refined definition")
    with pytest.raises(AnalysisError, match="child codes"):
        state.delete_code("parent", actor="alice")
    with pytest.raises(AnalysisError, match="annotations"):
        state.delete_code("child", actor="alice")
    store = QualitativeStore(tmp_path / "qual")
    saved = store.save("project1", state)
    reopened = QualitativeStore(tmp_path / "qual").load("project1")
    assert reopened.project.verify(annotation)
    assert reopened.project.codes["child"].description == "Refined definition"
    assert reopened.memos["memo1"].text == "Keep context"
    assert len(reopened.codebook_events) == 3
    assert reopened.review_ledger().consensus()[0]["status"] == "conflict"
    path = Path(saved["path"])
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["state"]["project"]["transcripts"][0]["text"] = "tampered"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(AnalysisError, match="hash mismatch"):
        store.load("project1")


def test_multiple_imputation_rejects_all_missing_row(tmp_path: Path):
    dataset = _table(tmp_path, "x,y\n1,2\n,\n3,4\n5,6\n")
    with pytest.raises(AnalysisError, match="missing all"):
        multiple_impute_normal(dataset, ["x", "y"], m=3, seed=1)


def test_missing_data_denominators_provenance_and_unchanged_original(tmp_path: Path):
    data = _table(tmp_path, "id,x,y\na,1,2\nb,,4\nc,3,\nd,5,8\n")
    original = [dict(row) for row in data.records]
    complete, receipt = complete_case(data, ["x", "y"])
    assert (receipt["n_total"], receipt["n_used"], receipt["n_excluded"]) == (4, 2, 2)
    assert complete.revision != data.revision
    assert len(complete.records) == receipt["n_used"]
    pairwise = available_case_covariance(data, ["x", "y"])
    assert pairwise["dataset_revision"] == data.revision
    assert pairwise["pairwise_n"] == [[3, 2], [2, 3]]
    assert pairwise["covariance"][0][1] == pytest.approx(12.0)
    assert pairwise["covariance"][1][0] == pytest.approx(12.0)
    filled, operation = simple_impute(data, "x", strategy="median")
    assert operation["imputed_rows"] == [1]
    assert operation["fill_value"] == 3.0
    assert filled.records[1]["x"] == 3.0
    assert filled.records[1]["y"] == "4"
    assert list(data.records) == original


def test_missing_data_invalid_models_and_no_implicit_imputation(tmp_path: Path):
    all_missing = _table(tmp_path, "x,y\n,1\n,2\n,3\n,4\n")
    with pytest.raises(AnalysisError, match="observed"):
        simple_impute(all_missing, "x", strategy="mean")
    with pytest.raises(AnalysisError, match="observed"):
        multiple_impute_normal(all_missing, ["x", "y"], m=3, seed=7)
    with pytest.raises(AnalysisError, match="complete cases"):
        complete_case(all_missing, ["x", "y"])
    with pytest.raises(AnalysisError, match="strategy"):
        simple_impute(all_missing, "x", strategy="unsupported")
    assert all(row["x"] is None for row in all_missing.records)
    tiny = _table(tmp_path, "x,y\n1,2\n,3\n2,4\n")
    with pytest.raises(AnalysisError, match="three observed"):
        multiple_impute_normal(tiny, ["x", "y"], m=3, seed=5)
    nonfinite = _table(tmp_path, "x,y\n1,2\n2,3\n3,4\ninf,5\n,6\n")
    with pytest.raises(AnalysisError):
        multiple_impute_normal(nonfinite, ["x", "y"], m=3, seed=8)


def test_multiple_imputation_seed_lineage_and_rubin_golden(tmp_path: Path):
    data = _table(tmp_path, "x,y\n1,2\n2,3\n3,\n4,5\n,6\n6,7\n")
    original = [dict(row) for row in data.records]
    first = multiple_impute_normal(data, ["x", "y"], m=3, seed=100)
    again = multiple_impute_normal(data, ["x", "y"], m=3, seed=100)
    different = multiple_impute_normal(data, ["x", "y"], m=3, seed=101)
    assert first.missing_counts == {"x": 1, "y": 1}
    assert first.seed == 100 and len(first.datasets) == 3
    assert [item.revision for item in first.datasets] == [item.revision for item in again.datasets]
    assert [item.revision for item in first.datasets] != [
        item.revision for item in different.datasets
    ]
    assert all(item.records[0] == original[0] for item in first.datasets)
    assert all(item.records[2]["x"] == "3" for item in first.datasets)
    assert list(data.records) == original
    assert any("not identified" in note for note in first.assumptions)
    assert any("fixed" in note for note in first.assumptions)

    estimates = [1.0, 2.0, 3.0]
    variances = [0.25, 0.5, 0.75]
    pooled = pool_scalar_rubin(estimates, variances)
    assert pooled["estimate"] == pytest.approx(2.0)
    assert pooled["within_variance"] == pytest.approx(0.5)
    assert pooled["between_variance"] == pytest.approx(1.0)
    assert pooled["total_variance"] == pytest.approx(0.5 + 4 / 3)
    assert pooled["standard_error"] == pytest.approx(math.sqrt(11 / 6))
    assert pooled["degrees_freedom"] == pytest.approx(2 * (1 + 0.5 / (4 / 3)) ** 2)
    assert pool_scalar_rubin([2, 2], [0.5, 0.5])["degrees_freedom"] == math.inf
    with pytest.raises(AnalysisError, match="nonnegative"):
        pool_scalar_rubin([1, 2], [0.1, -0.1])
    with pytest.raises(AnalysisError, match="positive"):
        pool_scalar_rubin([1, 1], [0, 0])
