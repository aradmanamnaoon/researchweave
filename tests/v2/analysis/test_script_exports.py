import json
import subprocess
import sys
from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.script_exports import (
    READ_OPERATIONS,
    export_python_script,
    export_r_script,
    save_syntax,
)


def test_export_executes_in_new_interpreter(tmp_path: Path):
    file = tmp_path / "values.csv"
    file.write_text("score\n1\n3\n5\n", encoding="utf-8")
    data = import_csv(file)
    store = tmp_path / "versions"
    build_analysis_facade(store).store.save(data)
    args = {"dataset_id": data.dataset_id, "revision": data.revision, "column": "score"}
    exported = export_python_script("statistics.describe", args, data)
    target = tmp_path / "replay.py"
    saved = save_syntax(exported, target)
    assert saved["sha256"] == exported.source_sha256
    # S603: use this test's fixed Python executable and generated local script.
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(target), str(store)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["mean"] == 3


def test_scripts_guard_revision_and_unsupported_r(tmp_path: Path):
    file = tmp_path / "values.csv"
    file.write_text("x\n2\n4\n6\n", encoding="utf-8")
    data = import_csv(file)
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        export_python_script(
            "statistics.describe", {"dataset_id": data.dataset_id, "revision": "bad"}, data
        )
    args = {"dataset_id": data.dataset_id, "revision": data.revision, "column": "x"}
    r = export_r_script("statistics.describe", args, data)
    assert "mean(v)" in r.source and "sd(v)" in r.source
    with pytest.raises(AnalysisError, match="UNSUPPORTED"):
        export_r_script("statistics.poisson", args, data)


def test_r_export_maps_common_inferential_procedures_to_base_r(tmp_path: Path):
    file = tmp_path / "values.csv"
    file.write_text(
        "score,x,group\n2,1,A\n4,2,A\n6,3,A\n8,4,B\n10,5,B\n12,6,B\n",
        encoding="utf-8",
    )
    data = import_csv(file)
    identity = {"dataset_id": data.dataset_id, "revision": data.revision}

    t_test = export_r_script("statistics.test", {**identity, "outcome": "score"}, data)
    assert "t.test(x" in t_test.source
    assert "source_revision" in t_test.source

    correlation = export_r_script(
        "statistics.correlate",
        {**identity, "x": "score", "y": "x", "method": "spearman"},
        data,
    )
    assert 'cor.test(x, y, method = "spearman", exact = FALSE)' in correlation.source

    anova = export_r_script(
        "statistics.anova",
        {**identity, "outcome": "score", "group": "group", "levels": ["A", "B"]},
        data,
    )
    assert "oneway.test(y ~ g, var.equal = TRUE)" in anova.source
    assert "eta_squared" in anova.source

    model = export_r_script(
        "statistics.model",
        {**identity, "outcome": "score", "predictors": ["x"]},
        data,
    )
    assert "fit <- lm(y ~ ., data = d)" in model.source
    assert '"x1": "x"' in model.source
    with pytest.raises(AnalysisError, match="base OLS only"):
        export_r_script(
            "statistics.model",
            {**identity, "outcome": "score", "predictors": ["x"], "covariance": "HC3"},
            data,
        )


def test_r_t_test_centers_nonzero_null_mean_output_on_researchweave_scale(tmp_path: Path):
    file = tmp_path / "values.csv"
    file.write_text("score,paired\n2,1\n4,2\n8,3\n10,4\n", encoding="utf-8")
    data = import_csv(file)
    identity = {"dataset_id": data.dataset_id, "revision": data.revision, "outcome": "score"}

    one_sample = export_r_script(
        "statistics.test",
        {**identity, "options": {"null_mean": 4}},
        data,
    )
    assert "mu <- 4" in one_sample.source
    assert "contrast_estimate <- unname(fit$estimate) - mu" in one_sample.source
    assert "contrast_conf_int <- unname(fit$conf.int) - mu" in one_sample.source
    assert any("centered on null_mean" in note for note in one_sample.limitations)

    paired = export_r_script(
        "statistics.test",
        {**identity, "options": {"paired": "paired", "null_mean": 2}},
        data,
    )
    assert "mu <- 2" in paired.source
    assert "t.test(x, y, paired = TRUE, mu = mu" in paired.source
    assert "contrast_conf_int <- unname(fit$conf.int) - mu" in paired.source


def test_python_replay_allowlist_matches_read_only_manifest(tmp_path: Path):
    facade = build_analysis_facade(tmp_path / "store")
    expected = {
        item["operation"]
        for item in facade.capability_manifest()
        if item["effect"] == "read" and item["operation"] != "dataset.scan_parquet"
    }
    assert READ_OPERATIONS == expected


def test_non_dataset_operation_replays_in_fresh_interpreter(tmp_path: Path):
    arguments = {"r": 0.5, "n": 20}
    exported = export_python_script("statistics.effect_correlation", arguments)
    assert exported.dataset_id is None
    assert exported.dataset_revision is None
    target = tmp_path / "effect_replay.py"
    save_syntax(exported, target)
    store = tmp_path / "empty_store"
    store.mkdir()
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(target), str(store)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["r"] == pytest.approx(0.5)
    assert payload["n"] == 20
