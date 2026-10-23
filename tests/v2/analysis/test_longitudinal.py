from pathlib import Path

import numpy as np
import pytest
import statsmodels.api as sm

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.longitudinal import (
    difference_in_differences,
    gaussian_gee,
    panel_matrix,
)


@pytest.fixture
def panel(tmp_path: Path):
    file = tmp_path / "panel.csv"
    rows = ["id,time,treated,score"]
    for subject in range(1, 13):
        treated = int(subject > 6)
        for period in (0, 1):
            score = (
                subject / 3
                + period * 1.3
                + treated * period * 2.5
                + (subject % 3 - 1) * 0.2 * period
            )
            rows.append(f"{subject},{period},{treated},{score}")
    file.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return import_csv(file)


def test_balanced_did_against_clustered_ols(panel):
    result = difference_in_differences(
        panel, subject="id", time="time", treatment="treated", outcome="score"
    )
    cells = result["cell_means"]
    raw_did = (
        cells["treated_post"]
        - cells["treated_pre"]
        - (cells["control_post"] - cells["control_pre"])
    )
    assert result["estimate"] == pytest.approx(raw_did)
    assert result["estimate"] == pytest.approx(2.5)
    assert result["n_subjects"] == 12
    assert result["n_used"] == 24


def test_gee_matches_independent_reference(panel):
    result = gaussian_gee(
        panel,
        subject="id",
        time="time",
        outcome="score",
        predictors=["time", "treated"],
        correlation="exchangeable",
    )
    matrix = panel_matrix(
        panel, subject="id", time="time", outcome="score", predictors=["time", "treated"]
    )
    expected = sm.GEE(
        matrix["outcome"],
        matrix["design"],
        groups=np.asarray(matrix["groups"]),
        family=sm.families.Gaussian(),
        cov_struct=sm.cov_struct.Exchangeable(),
    ).fit(maxiter=100)
    assert result["coefficients"]["time"] == pytest.approx(expected.params[1])
    assert result["standard_errors"]["time"] == pytest.approx(expected.bse[1])
    assert result["n_subjects"] == 12
    assert result["converged"] is True


def test_duplicate_panels_fail(panel):
    duplicated = [dict(row) for row in panel.records]
    duplicated.append(dict(duplicated[-1]))
    from researchweave.analysis.datasets import revise

    frame = revise(panel, duplicated, {"type": "intentional_bad_duplicate"})
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        difference_in_differences(
            frame, subject="id", time="time", treatment="treated", outcome="score"
        )
