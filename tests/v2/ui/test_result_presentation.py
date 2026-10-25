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


def test_nested_regression_and_auto_analysis_are_flattened_without_inference() -> None:
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
