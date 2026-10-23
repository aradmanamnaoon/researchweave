from pathlib import Path

import numpy as np
import pytest

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.meta_analysis import funnel_asymmetry_egger, random_effects_meta
from researchweave.analysis.multivariate import cluster_validation
from researchweave.analysis.time_series import (
    arima_forecast,
    ljung_box,
    parse_chronology,
    seasonal_decomposition,
)


def test_cluster_validation_prefers_well_separated_two_cluster_solution(tmp_path: Path):
    rng = np.random.default_rng(5)
    first = rng.normal(loc=-4, scale=0.25, size=(30, 2))
    second = rng.normal(loc=4, scale=0.25, size=(30, 2))
    values = np.vstack([first, second])
    path = tmp_path / "clusters.csv"
    path.write_text(
        "x,y\n" + "\n".join(f"{row[0]},{row[1]}" for row in values) + "\n",
        encoding="utf-8",
    )
    dataset = import_csv(path)
    result = cluster_validation(
        dataset, ["x", "y"], k_values=[2, 3, 4], seed=7, stability_repeats=4
    )
    assert result["recommended_k_by_declared_rule"] == 2
    two = next(row for row in result["candidates"] if row["k"] == 2)
    assert two["silhouette"] > 0.9
    assert two["mean_adjusted_rand_vs_first"] == pytest.approx(1)


def _seasonal_dataset(tmp_path: Path):
    rng = np.random.default_rng(10)
    values = [
        10 + 0.15 * i + 2 * np.sin(2 * np.pi * i / 12) + rng.normal(scale=0.2) for i in range(72)
    ]
    path = tmp_path / "series.csv"
    from datetime import UTC, datetime, timedelta

    rows = ["time,value"] + [
        f"{(datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat()},{value}"
        for i, value in enumerate(values)
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return import_csv(path)


def test_time_series_diagnostics_decomposition_and_no_leakage_forecast(tmp_path: Path):
    dataset = _seasonal_dataset(tmp_path)
    chronology = parse_chronology(dataset, "time", "value")
    serial = ljung_box(chronology, lags=[1, 6, 12])
    assert serial["lags"] == [1, 6, 12]
    decomposition = seasonal_decomposition(chronology, period=12)
    assert len(decomposition["seasonal"]) == 72
    forecast = arima_forecast(
        chronology,
        order=(1, 0, 0),
        seasonal_order=(1, 0, 0, 12),
        horizon=4,
        validation_horizon=8,
    )
    assert len(forecast["forecast"]) == 4
    assert forecast["validation"]["training_n"] == 64
    assert forecast["validation"]["no_future_leakage"] is True
    assert forecast["validation"]["rmse"] >= 0


def test_reml_meta_analysis_influence_and_egger():
    studies = [
        {"id": f"s{i}", "scale": "mean_difference", "estimate": value, "se": se}
        for i, (value, se) in enumerate(
            [
                (0.10, 0.10),
                (0.20, 0.11),
                (0.15, 0.09),
                (0.50, 0.12),
                (0.35, 0.10),
                (0.05, 0.15),
                (0.40, 0.13),
                (0.25, 0.09),
                (0.30, 0.10),
                (0.18, 0.12),
            ]
        )
    ]
    result = random_effects_meta(studies, tau_method="reml", hartung_knapp=True)
    assert 0.1 < result["estimate"] < 0.4
    assert result["tau_squared"] >= 0
    assert len(result["leave_one_out"]) == 10
    assert (
        result["confidence_interval_95"][0]
        < result["estimate"]
        < result["confidence_interval_95"][1]
    )
    egger = funnel_asymmetry_egger(studies)
    assert 0 <= egger["p_value"] <= 1
