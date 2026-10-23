"""Golden tests use analytic values and SciPy as independent numerical oracle."""

from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.datasets import DatasetStore, import_csv, page, set_variable
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.modeling import adjust_pvalues, linear_regression, pooled_effects
from researchweave.analysis.statistics import correlation, describe, reliability, t_test
from researchweave.analysis.transformations import transform


@pytest.fixture
def sample(tmp_path: Path):
    csv_file = tmp_path / "study.csv"
    csv_file.write_text(
        "group,score,pre,item1,item2\nA,2,1,1,2\nA,4,3,2,3\n"
        "A,6,5,3,4\nB,1,2,2,2\nB,3,2,3,3\nB,5,4,4,4\n",
        encoding="utf-8",
    )
    return import_csv(csv_file)


def test_import_save_reload_and_dictionary(sample, tmp_path):
    store = DatasetStore(tmp_path / "history")
    store.save(sample)
    reopened = store.load(sample.dataset_id, sample.revision)
    assert reopened.records == sample.records
    assert reopened.source_hash == sample.source_hash
    assert page(reopened, offset=1, limit=2)["rows"][0]["score"] == "4"
    edited = set_variable(reopened, "score", units="points", scale="ratio")
    store.save(edited)
    assert store.load(edited.dataset_id, edited.revision).variables[1].units == "points"
    assert store.load(sample.dataset_id, sample.revision).variables[1].units == ""


def test_import_rejects_bad_csv(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("a,b\n1,2,3\n", encoding="utf-8")
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        import_csv(path)
    path.write_text("a,a\n1,2\n", encoding="utf-8")
    with pytest.raises(AnalysisError, match="Duplicate"):
        import_csv(path)


def test_transform_immutable_replay_and_null_policy(sample):
    spec = {"type": "filter", "expression": {"column": "group", "op": "eq", "value": "A"}}
    result = transform(sample, spec)
    assert len(result.records) == 3
    assert result.revision == transform(sample, spec).revision
    assert len(sample.records) == 6
    with pytest.raises(AnalysisError, match="Explicit null"):
        transform(
            sample, {"type": "filter", "expression": {"column": "score", "op": "eq", "value": None}}
        )


def test_descriptive_and_welch_oracle(sample):
    summary = describe(sample, "score")
    assert summary["mean"] == pytest.approx(3.5)
    assert summary["sd_sample"] == pytest.approx(np.std([2, 4, 6, 1, 3, 5], ddof=1))
    result = t_test(sample, "score", group="group", groups=("A", "B"))
    expected = stats.ttest_ind([2, 4, 6], [1, 3, 5], equal_var=False)
    assert result.statistic == pytest.approx(expected.statistic)
    assert result.p_value == pytest.approx(expected.pvalue)
    assert result.degrees_freedom == pytest.approx(4)
    assert result.n_used == 6
    assert result.effect["cohen_d"] == pytest.approx(0.5)


def test_paired_and_correlation(sample):
    paired = t_test(sample, "score", paired="pre")
    oracle = stats.ttest_rel([2, 4, 6, 1, 3, 5], [1, 3, 5, 2, 2, 4])
    assert paired.p_value == pytest.approx(oracle.pvalue)
    assert correlation(sample, "score", "pre").estimate == pytest.approx(
        stats.pearsonr([2, 4, 6, 1, 3, 5], [1, 3, 5, 2, 2, 4]).statistic
    )
    with pytest.raises(AnalysisError, match="Paired and independent"):
        t_test(sample, "score", group="group", paired="pre")


def test_alpha_manual_covariance(sample):
    output = reliability(sample, ["item1", "item2"])
    matrix = np.asarray([[1, 2], [2, 3], [3, 4], [2, 2], [3, 3], [4, 4]])
    oracle = 2 * (
        1 - np.sum(np.var(matrix, axis=0, ddof=1)) / np.var(np.sum(matrix, axis=1), ddof=1)
    )
    assert output.estimate == pytest.approx(oracle)
    with pytest.raises(AnalysisError, match="Reverse coding"):
        reliability(sample, ["item1", "item2"], reverse=["item1"])


def test_facade_authorization_and_restart(sample, tmp_path):
    facade = build_analysis_facade(tmp_path / "database")
    source = tmp_path / "source.csv"
    source.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    req = {"filename": "source.csv"}
    denied = facade.execute("dataset.import", req, {"trusted_import_root": tmp_path})
    assert denied["error"]["code"] == "PERMISSION_DENIED"
    allowed = facade.execute(
        "dataset.import", req, {"host_authorized": True, "trusted_import_root": tmp_path}
    )
    assert allowed["status"] == "ok"
    data = allowed["data"]
    reopened = build_analysis_facade(tmp_path / "database")
    describe_result = reopened.execute(
        "statistics.describe",
        {"dataset_id": data["dataset_id"], "revision": data["revision"], "column": "x"},
        {},
    )
    assert describe_result["data"]["mean"] == 2
    malicious = reopened.execute(
        "dataset.import",
        {"filename": "../outside.csv"},
        {"host_authorized": True, "trusted_import_root": tmp_path},
    )
    assert malicious["error"]["code"] == "PERMISSION_DENIED"


def test_regression_oracle_and_singular_design(tmp_path):
    path = tmp_path / "regression.csv"
    path.write_text("x,y,z\n1,3,2\n2,5,4\n3,7,6\n4,9,8\n5,11,10\n", encoding="utf-8")
    frame = import_csv(path)
    fitted = linear_regression(frame, "y", ["x"])
    assert fitted.details["coefficients"]["intercept"] == pytest.approx(1)
    assert fitted.details["coefficients"]["x"] == pytest.approx(2)
    assert fitted.details["r_squared"] == pytest.approx(1)
    with pytest.raises(AnalysisError, match="Singular"):
        linear_regression(frame, "y", ["x", "z"])


def test_meta_oracle_scale_guard_and_multiplicity():
    studies = [
        {"id": "a", "estimate": 2, "se": 1, "scale": "mean_difference"},
        {"id": "b", "estimate": 4, "se": 1, "scale": "mean_difference"},
    ]
    output = pooled_effects(studies)
    assert output["estimate"] == pytest.approx(3)
    assert output["standard_error"] == pytest.approx(1 / np.sqrt(2))
    with pytest.raises(AnalysisError, match="compatible"):
        pooled_effects([studies[0], {**studies[1], "scale": "log_or"}])
    assert adjust_pvalues([0.01, 0.04, 0.03], method="holm") == pytest.approx([0.03, 0.06, 0.06])
    assert adjust_pvalues([0.01, 0.04, 0.03], method="bh") == pytest.approx([0.03, 0.04, 0.04])
