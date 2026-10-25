from __future__ import annotations

from researchweave.ui.result_presentation import format_result_record


def test_descriptive_result_is_presented_as_structured_rows() -> None:
    presentation = format_result_record(
        {
            "method": "descriptive",
            "method_version": "python-statistics-v1",
            "created_at": "2026-10-25T00:00:00Z",
            "inputs": {"column": "score"},
            "assumptions": ["Values are numeric."],
            "warnings": [],
            "estimates": {"n": 3, "mean": 2.5},
            "uncertainty": {},
            "diagnostics": {"excluded_n": 1},
            "provenance": {"dataset_revision": "abc"},
        }
    )
    assert presentation.columns == ("Section", "Metric", "Value")
    assert ("Estimates", "mean", "2.5") in presentation.rows
    assert ("Estimates", "n", "3") in presentation.rows
    assert ("Diagnostics", "excluded_n", "1") in presentation.rows
    assert "Warnings: none" in presentation.detail
    assert "Reproducibility" in presentation.detail
    assert '"dataset_revision": "abc"' in presentation.detail


def test_auto_analysis_is_flattened_without_inference() -> None:
    presentation = format_result_record(
        {
            "method": "analysis.statistics.auto_analyze",
            "method_version": "scientific-v2",
            "created_at": "2026-10-25T00:00:00Z",
            "inputs": {"mode": "predict-outcome"},
            "assumptions": [],
            "warnings": ["Exploratory output."],
            "estimates": {
                "coefficients": {
                    "intercept": {"estimate": 1.25, "p_value": 0.04},
                    "x": {"estimate": -0.5, "p_value": None},
                },
                "report": {"selected_methods": ["statistics.model"]},
            },
            "uncertainty": {"confidence_level": 0.95},
            "diagnostics": {},
            "provenance": {"engine": "python"},
        }
    )
    rows = set(presentation.rows)
    assert ("Estimates", "coefficients.intercept.estimate", "1.25") in rows
    assert ("Estimates", "coefficients.intercept.p_value", "0.04") in rows
    assert ("Estimates", "coefficients.x.p_value", "—") in rows
    assert ("Uncertainty", "confidence_level", "0.95") in rows
    assert "Exploratory output." in presentation.detail


def test_t_test_uses_procedure_aware_table_with_sample_accounting() -> None:
    presentation = format_result_record(
        {
            "method": "statistics.test",
            "method_version": "scientific-v2",
            "created_at": "2026-10-25T00:00:00Z",
            "inputs": {"outcome": "score"},
            "assumptions": ["Independent units."],
            "warnings": [],
            "estimates": {
                "method": "welch_t",
                "n_total": 10,
                "n_used": 9,
                "n_excluded": 1,
                "estimate": 1.5,
                "statistic": 2.25,
                "p_value": 0.031,
                "degrees_freedom": 6.75,
                "confidence_interval": [0.1, 2.9],
                "effect": {"cohen_d": 0.7},
                "details": {
                    "outcome": "score",
                    "group": "condition",
                    "levels": ["control", "treatment"],
                    "alternative": "two-sided",
                    "alpha": 0.05,
                },
            },
            "uncertainty": {},
            "diagnostics": {},
            "provenance": {"dataset_revision": "abc"},
        }
    )
    assert presentation.columns == (
        "Procedure",
        "Estimate",
        "t",
        "df",
        "p",
        "CI lower",
        "CI upper",
        "Effect",
        "N used",
        "N excluded",
    )
    assert presentation.rows == (
        ("Welch t test", "1.5", "2.25", "6.75", "0.031", "0.1", "2.9", "Cohen's d = 0.7", "9", "1"),
    )
    assert "Outcome: score" in presentation.detail
    assert "N total: 10" in presentation.detail


def test_one_way_anova_uses_named_degrees_of_freedom() -> None:
    presentation = format_result_record(
        {
            "method": "statistics.anova",
            "method_version": "scientific-v2",
            "created_at": "now",
            "inputs": {},
            "assumptions": [],
            "warnings": [],
            "estimates": {
                "method": "one_way_anova",
                "n_total": 12,
                "n_used": 11,
                "n_excluded": 1,
                "statistic": 4.25,
                "p_value": 0.018,
                "degrees_freedom": 2,
                "effect": {"eta_squared": 0.22},
                "details": {
                    "df_between": 2,
                    "df_within": 8,
                    "levels": ["A", "B", "C"],
                    "n_per_group": [4, 4, 3],
                },
            },
            "uncertainty": {},
            "diagnostics": {},
            "provenance": {},
        }
    )
    assert presentation.columns[:5] == ("Procedure", "df between", "df within", "F", "p")
    assert presentation.rows[0][:5] == ("One-way ANOVA", "2", "8", "4.25", "0.018")
    assert presentation.rows[0][5] == "eta squared = 0.22"
    assert "N per group: [4, 4, 3]" in presentation.detail


def test_ols_uses_coefficient_table_and_keeps_model_diagnostics_in_detail() -> None:
    presentation = format_result_record(
        {
            "method": "statistics.model",
            "method_version": "scientific-v2",
            "created_at": "now",
            "inputs": {"outcome": "y", "predictors": ["x"]},
            "assumptions": ["Independent units."],
            "warnings": ["Review residual diagnostics."],
            "estimates": {
                "method": "ols",
                "n_total": 8,
                "n_used": 7,
                "n_excluded": 1,
                "details": {
                    "coefficients": {"intercept": 1.0, "x": 2.0},
                    "intervals": {"intercept": [0.25, 1.75], "x": [1.5, 2.5]},
                    "p_values": {"intercept": 0.02, "x": 0.0004},
                    "r_squared": 0.91,
                    "covariance": "HC3",
                    "cluster_group": None,
                    "missing_policy": "complete_case",
                },
            },
            "uncertainty": {},
            "diagnostics": {},
            "provenance": {"request_id": "r1"},
        }
    )
    assert presentation.columns == ("Term", "Estimate", "CI lower", "CI upper", "p")
    assert presentation.rows == (
        ("intercept", "1", "0.25", "1.75", "0.02"),
        ("x", "2", "1.5", "2.5", "0.0004"),
    )
    assert "R²: 0.91" in presentation.detail
    assert "Covariance: HC3" in presentation.detail
    assert "N used: 7" in presentation.detail
    assert "Review residual diagnostics." in presentation.detail


def test_unknown_complex_result_falls_back_to_bounded_json() -> None:
    presentation = format_result_record(
        {
            "method": "experimental",
            "method_version": "1",
            "created_at": "now",
            "inputs": {},
            "assumptions": [],
            "warnings": [],
            "estimates": {"matrix": [[index for index in range(20)]]},
            "uncertainty": {},
            "diagnostics": {},
            "provenance": {},
        }
    )
    matrix_row = next(row for row in presentation.rows if row[1] == "matrix[0]")
    assert matrix_row[2].startswith("[0,1,2")


def test_empty_structured_sections_use_explicit_empty_state() -> None:
    presentation = format_result_record(
        {
            "method": "empty",
            "method_version": "1",
            "created_at": "now",
            "inputs": {},
            "assumptions": [],
            "warnings": [],
            "estimates": {},
            "uncertainty": {},
            "diagnostics": {},
            "provenance": {},
        }
    )
    assert presentation.rows == (
        ("Result", "status", "No structured numerical fields were returned."),
    )
