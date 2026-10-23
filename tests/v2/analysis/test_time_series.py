from pathlib import Path

import numpy as np
import pytest
from statsmodels.tsa.stattools import adfuller

from researchweave.analysis.datasets import import_csv
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.time_series import (
    adf_stationarity,
    autocorrelation,
    causal_features,
    parse_chronology,
    trend_slope,
)


def _series(tmp_path: Path, content: str):
    path = tmp_path / "series.csv"
    path.write_text("time,value\n" + content, encoding="utf-8")
    return import_csv(path)


def test_timezone_dst_and_strict_order(tmp_path):
    data = _series(
        tmp_path,
        "2026-03-29T00:00:00+01:00,1\n"
        "2026-03-29T01:00:00+01:00,2\n"
        "2026-03-29T03:00:00+02:00,3\n"
        "2026-03-29T04:00:00+02:00,4\n",
    )
    chronology = parse_chronology(data, "time", "value")
    assert chronology.interval_seconds == 3600
    assert chronology.n_used == 4
    bad = _series(
        tmp_path,
        "2026-01-01T00:00:00,1\n"
        "2026-01-02T00:00:00,2\n2026-01-03T00:00:00,3\n"
        "2026-01-04T00:00:00,4\n",
    )
    with pytest.raises(AnalysisError, match="timezone"):
        parse_chronology(bad, "time", "value")


def test_causal_features_past_only_and_acf(tmp_path):
    data = _series(tmp_path, "".join(f"2026-01-{i:02d}T12:00:00+00:00,{i}\n" for i in range(1, 11)))
    chronology = parse_chronology(data, "time", "value")
    features = causal_features(chronology, lags=[1, 2], rolling_window=3)
    assert features["n_lagged"] == 3
    assert features["rows"][0]["target"] == 4
    assert features["rows"][0]["lag_1"] == 3
    assert features["rows"][0]["rolling_mean_3"] == 2
    acf = autocorrelation(chronology, max_lag=2)
    observed = chronology.values
    centered = observed - np.mean(observed)
    reference = np.dot(centered[:-1], centered[1:]) / np.dot(centered, centered)
    assert acf["autocorrelation"][0] == pytest.approx(reference)
    assert trend_slope(chronology)["slope_per_observation"] == pytest.approx(1)


def test_adf_against_reference_and_too_short(tmp_path):
    rng = np.random.default_rng(19)
    values = [int(v) for v in rng.integers(0, 10, 25)]
    data = _series(
        tmp_path,
        "".join(f"2026-01-{i:02d}T12:00:00+00:00,{v}\n" for i, v in enumerate(values, start=1)),
    )
    chronology = parse_chronology(data, "time", "value")
    output = adf_stationarity(chronology)
    oracle = adfuller(values, autolag="AIC", result_object=False)
    assert output["statistic"] == pytest.approx(oracle[0])
    assert output["p_value"] == pytest.approx(oracle[1])
    with pytest.raises(AnalysisError, match="twelve"):
        adf_stationarity(
            parse_chronology(
                _series(
                    tmp_path, "".join(f"2026-01-{i:02d}T12:00:00+00:00,{i}\n" for i in range(1, 7))
                ),
                "time",
                "value",
            )
        )
