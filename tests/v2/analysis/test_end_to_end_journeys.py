from pathlib import Path

import pytest

from researchweave.analysis.journeys import (
    intro_stats_journey,
    psychometric_journey,
    qualitative_audit_journey,
    reproducible_script_journey,
    survey_modeling_journey,
)


def test_intro_stats_journey_restart_script_and_failure(tmp_path: Path):
    trace = intro_stats_journey(tmp_path)
    assert trace["scientific_result"]["method"] == "welch_t"
    assert 0 <= trace["scientific_result"]["p_value"] <= 1
    assert trace["scientific_result"]["n_used"] == 8
    assert trace["restart_replay"]["match"] is True
    assert trace["script_matches_facade"] is True
    assert trace["injected_failure"]["code"] == "INVALID_INPUT"
    assert len(trace["plot"]["sha256"]) == 64


def test_survey_modeling_journey_design_restart_and_bad_weight(tmp_path: Path):
    trace = survey_modeling_journey(tmp_path)
    assert trace["source_format"] == "sav"
    assert trace["survey_mean"]["n_strata"] == 2
    assert trace["survey_mean"]["n_psus"] == 6
    assert trace["model"]["method"] == "ols"
    assert trace["restart_result_match"] is True
    assert trace["injected_failure"] == "INVALID_INPUT"


def test_psychometric_journey_oracle_restart_and_invalid_endpoints(tmp_path: Path):
    trace = psychometric_journey(tmp_path)
    assert trace["score_summary"]["n_valid"] == 80
    assert trace["alpha"] == pytest.approx(trace["oracle_alpha"], abs=1e-12)
    assert trace["alpha"] > 0.7
    assert trace["omega_total"] is not None
    assert trace["restart_score_match"] is True
    assert trace["injected_failure"] == "INVALID_INPUT"


def test_qualitative_journey_unicode_agreement_review_restart_and_stale_source(tmp_path: Path):
    trace = qualitative_audit_journey(tmp_path)
    assert trace["n_annotations"] == 8
    assert trace["kappa"]["kappa"] == pytest.approx(0.5)
    assert len(trace["disagreements"]) == 1
    assert trace["restart_project_hash_match"] is True
    assert trace["stale_source_relocation"]["status"] == "missing"
    assert trace["review_consensus"][2]["status"] == "conflict"


def test_reproducible_script_journey_approval_timeout_replay_and_r_path(tmp_path: Path):
    trace = reproducible_script_journey(tmp_path)
    assert trace["restart_replay"]["match"] is True
    assert trace["script_matches_facade"] is True
    assert trace["runtime"]["stdout"].strip() == "42"
    assert trace["runtime"]["artifacts"][0]["path"] == "artifact.txt"
    assert trace["unsigned_denial"]["code"] == "PERMISSION_DENIED"
    assert trace["timeout_failure"]["code"] == "CANCELLED"
    if trace["r_available"]:
        assert trace["r_result"]["status"] == "ok"
    else:
        assert trace["r_result"]["code"] == "DEPENDENCY_MISSING"
