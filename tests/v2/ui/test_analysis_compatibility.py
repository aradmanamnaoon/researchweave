from __future__ import annotations

from researchweave.ui.analysis_compatibility import (
    COMPATIBILITY_COLUMNS,
    build_compatibility_rows,
)


def _row(rows: list[list[str]], family: str) -> list[str]:
    return next(row for row in rows if row[0] == family)


def test_compatibility_matrix_tracks_live_registered_methods_without_parity_claims() -> None:
    methods = [
        {"id": "analysis.statistics.describe", "available": True},
        {"id": "analysis.statistics.frequency", "available": True},
        {"id": "analysis.statistics.grouped_describe", "available": True},
        {"id": "analysis.statistics.test", "available": True},
        {"id": "analysis.statistics.anova", "available": True},
        {"id": "analysis.statistics.welch_anova", "available": True},
        {"id": "analysis.syntax.python", "available": True},
        {"id": "analysis.syntax.r", "available": True},
        {"id": "analysis.runtime.r", "available": True},
    ]
    rows = build_compatibility_rows(methods)

    descriptives = _row(rows, "Descriptives & frequencies")
    assert descriptives[1] == "Broad"
    assert "mapped R: describe" in descriptives[3]

    t_tests = _row(rows, "t tests / compare means")
    assert t_tests[1] == "Broad"
    assert t_tests[3] == "Python replay; mapped R syntax"

    anova = _row(rows, "ANOVA / GLM")
    assert anova[1] == "Partial"
    assert "Missing registered operations" in anova[4]

    manova = _row(rows, "Multivariate GLM / MANOVA")
    assert manova[1] == "Unavailable"
    assert manova[2] == "—"
    assert "No dedicated MANOVA/MANCOVA" in manova[4]


def test_compatibility_columns_are_stable_for_accessible_table_headers() -> None:
    assert COMPATIBILITY_COLUMNS == [
        "Procedure family",
        "Coverage",
        "Methods",
        "Reproducibility",
        "Limits",
    ]
