"""Runnable synthetic end-to-end analysis journeys used for acceptance and demos."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .coding_review import CodingReviewLedger, disagreements, propose_relocation
from .datasets import DatasetStore, import_csv
from .errors import AnalysisError, require
from .facade import AnalysisFacade, build_analysis_facade
from .mixed_methods import case_code_matrix
from .models import canonical_json, digest, utc_now
from .psychometrics import reliability_diagnostics
from .qualitative import Code, Transcript, cohen_kappa
from .qualitative_store import Memo, QualitativeState, QualitativeStore
from .reproducibility import (
    AnalysisPlan,
    AnalysisStep,
    execute_plan,
    load_receipt,
    save_receipt,
    verify_replay,
)
from .scale_scoring import ScaleDefinition, score_scale
from .script_exports import export_python_script, save_syntax
from .statistics import reliability
from .survey import design_weighted_mean


def _ensure_workspace(workspace: Path) -> Path:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _authorized(
    facade: AnalysisFacade,
    operation: str,
    arguments: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    capability = facade.issue_authorization(operation, arguments)
    return dict(
        facade.execute(
            operation,
            arguments,
            {"host_capability": capability, "request_id": request_id},
        )
    )


def _identity(imported: dict[str, Any]) -> dict[str, str]:
    require(imported.get("status") == "ok", "Synthetic import failed", "INTEGRITY_FAILURE")
    data = imported["data"]
    return {"dataset_id": str(data["dataset_id"]), "revision": str(data["revision"])}


def intro_stats_journey(workspace: Path) -> dict[str, Any]:
    """CSV -> inspect -> Welch t -> plot -> receipt restart -> syntax replay -> failure."""

    root = _ensure_workspace(workspace) / "intro_stats"
    root.mkdir(exist_ok=True)
    source = root / "intro.csv"
    source.write_text(
        "group,score,pre\nA,2,1\nA,4,3\nA,6,5\nA,8,6\nB,1,2\nB,3,2\nB,5,4\nB,6,5\n",
        encoding="utf-8",
    )
    store_root = root / "store"
    facade = build_analysis_facade(store_root, import_root=root, export_root=root)
    import_args = {"filename": source.name}
    imported = _authorized(facade, "dataset.import", import_args, request_id="intro-import")
    identity = _identity(imported)
    inspected = facade.execute("dataset.inspect", identity, {"request_id": "intro-inspect"})
    missing = facade.execute("dataset.missingness", identity, {"request_id": "intro-missing"})
    test_args = {
        **identity,
        "outcome": "score",
        "options": {"group": "group", "groups": ["A", "B"], "equal_variance": False},
    }
    tested = facade.execute("statistics.test", test_args, {"request_id": "intro-test"})
    require(tested["status"] == "ok", "Intro t-test failed", "INTEGRITY_FAILURE")
    plot_args = {**identity, "filename": "intro_hist.svg", "x": "score", "kind": "histogram"}
    plotted = _authorized(facade, "plot.render", plot_args, request_id="intro-plot")
    plan = AnalysisPlan(
        "intro_plan",
        1,
        (
            AnalysisStep("describe", "statistics.describe", {**identity, "column": "score"}),
            AnalysisStep("compare", "statistics.test", test_args),
        ),
        seed=17,
        rationale="Synthetic two-group introductory comparison",
        hypotheses=("Group means differ",),
    )
    receipt = execute_plan(plan, facade, {"request_id": "intro-plan"})
    receipt_path = root / "intro_receipt.json"
    save_receipt(receipt, receipt_path)
    reopened_receipt = load_receipt(receipt_path)
    restarted = build_analysis_facade(store_root)
    replayed = execute_plan(plan, restarted, {"request_id": "intro-plan"})
    replay_check = verify_replay(reopened_receipt, replayed)
    dataset = DatasetStore(store_root).load(identity["dataset_id"], identity["revision"])
    syntax = export_python_script("statistics.test", test_args, dataset)
    syntax_path = root / "intro_replay.py"
    save_syntax(syntax, syntax_path)
    process = subprocess.run(  # noqa: S603
        [sys.executable, str(syntax_path), str(store_root)],
        cwd=root,
        capture_output=True,
        check=False,
        shell=False,
        timeout=30,
        text=True,
        encoding="utf-8",
    )
    require(process.returncode == 0, "Generated intro replay script failed", "INTEGRITY_FAILURE")
    script_data = json.loads(process.stdout)
    invalid_args = {
        **identity,
        "outcome": "score",
        "options": {"group": "group", "groups": ["A", "missing"]},
    }
    invalid = facade.execute("statistics.test", invalid_args, {"request_id": "intro-invalid"})
    require(invalid["status"] == "failed", "Invalid group selection unexpectedly succeeded")
    return {
        "journey": "intro_stats",
        "dataset": identity,
        "inspect_columns": inspected["data"]["variables"],
        "missingness": missing["data"],
        "scientific_result": tested["data"],
        "plot": plotted["data"],
        "receipt_hash": receipt.output_hash,
        "restart_replay": replay_check,
        "syntax_sha256": syntax.source_sha256,
        "script_result_hash": digest(script_data),
        "facade_result_hash": digest(tested["data"]),
        "script_matches_facade": digest(script_data) == digest(tested["data"]),
        "injected_failure": invalid["error"],
        "offline": True,
    }


def survey_modeling_journey(workspace: Path) -> dict[str, Any]:
    """Labelled SAV -> missing policy -> survey mean + OLS diagnostics -> restart."""

    root = _ensure_workspace(workspace) / "survey_modeling"
    root.mkdir(exist_ok=True)
    try:
        import pandas as pd
        import pyreadstat
    except ImportError as exc:  # pragma: no cover - acceptance environment has these readers
        raise AnalysisError(
            "DEPENDENCY_MISSING", "Survey labelled fixture dependencies unavailable"
        ) from exc
    frame = pd.DataFrame(
        {
            "outcome": [10.0, 11.5, 12.0, np.nan, 15.0, 16.0, 17.5, 18.0, 20.0, 21.0, 22.0, 23.0],
            "x": [1.0, 2.0, 3.0, 4.0, 2.0, 3.0, 4.0, 5.0, 3.0, 4.0, 5.0, 6.0],
            "weight": [1.0, 1.2, 0.8, 1.0, 1.1, 0.9, 1.3, 0.7, 1.0, 1.0, 1.2, 0.8],
            "stratum": [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2],
            "psu": [1, 1, 2, 2, 3, 3, 1, 1, 2, 2, 3, 3],
        }
    )
    source = root / "survey.sav"
    pyreadstat.write_sav(
        frame,
        source,
        column_labels={
            "outcome": "Synthetic outcome",
            "weight": "Sampling weight",
            "stratum": "Sampling stratum",
            "psu": "Primary sampling unit",
        },
        variable_measure={
            "outcome": "scale",
            "x": "scale",
            "weight": "scale",
            "stratum": "nominal",
            "psu": "nominal",
        },
    )
    store_root = root / "store"
    facade = build_analysis_facade(store_root, import_root=root, export_root=root)
    import_args = {"filename": source.name}
    imported = _authorized(facade, "dataset.import", import_args, request_id="survey-import")
    identity = _identity(imported)
    missing_args = {**identity, "column": "outcome", "missing_values": ["-99"]}
    recoded = _authorized(facade, "dataset.user_missing", missing_args, request_id="survey-missing")
    identity2 = {"dataset_id": identity["dataset_id"], "revision": recoded["data"]["revision"]}
    survey_args = {
        **identity2,
        "outcome": "outcome",
        "weight": "weight",
        "stratum": "stratum",
        "psu": "psu",
    }
    survey = facade.execute("statistics.survey_mean", survey_args, {"request_id": "survey-mean"})
    model_args = {**identity2, "outcome": "outcome", "predictors": ["x"], "covariance": "HC3"}
    model = facade.execute("statistics.model", model_args, {"request_id": "survey-model"})
    diagnostics = facade.execute(
        "statistics.diagnostics",
        {**identity2, "outcome": "outcome", "predictors": ["x"]},
        {"request_id": "survey-diagnostics"},
    )
    scatter_args = {
        **identity2,
        "filename": "survey_residual_proxy.svg",
        "x": "x",
        "y": "outcome",
        "kind": "scatter",
    }
    diagnostic_plot = _authorized(facade, "plot.render", scatter_args, request_id="survey-plot")
    restarted = build_analysis_facade(store_root)
    reopened_model = restarted.execute(
        "statistics.model", model_args, {"request_id": "survey-model"}
    )
    invalid_path = root / "invalid_weight.csv"
    invalid_path.write_text(
        "outcome,weight,stratum,psu\n1,1,A,p1\n2,-1,A,p2\n3,1,B,p1\n4,1,B,p2\n",
        encoding="utf-8",
    )
    invalid_dataset = import_csv(invalid_path)
    try:
        design_weighted_mean(
            invalid_dataset,
            outcome="outcome",
            weight="weight",
            stratum="stratum",
            psu="psu",
        )
    except AnalysisError as exc:
        invalid_error = exc.code
    else:  # pragma: no cover - explicit invariant
        raise AnalysisError("INTEGRITY_FAILURE", "Negative survey weight was accepted")
    return {
        "journey": "survey_modeling",
        "source_format": "sav",
        "dataset": identity2,
        "survey_mean": survey["data"],
        "model": model["data"],
        "diagnostics": diagnostics["data"],
        "diagnostic_plot": diagnostic_plot["data"],
        "restart_result_match": digest(model["data"]) == digest(reopened_model["data"]),
        "injected_failure": invalid_error,
        "offline": True,
    }


def psychometric_journey(workspace: Path) -> dict[str, Any]:
    """Likert import -> reverse scoring -> scale -> reliability -> oracle -> restart."""

    root = _ensure_workspace(workspace) / "psychometric"
    root.mkdir(exist_ok=True)
    rng = np.random.default_rng(22)
    latent = rng.normal(size=80)
    continuous = np.column_stack([latent + rng.normal(scale=0.45, size=80) for _ in range(4)])
    quantiles = [np.quantile(continuous[:, index], [0.2, 0.4, 0.6, 0.8]) for index in range(4)]
    items = np.column_stack(
        [np.digitize(continuous[:, index], quantiles[index]) + 1 for index in range(4)]
    )
    items[:, 3] = 6 - items[:, 3]
    source = root / "likert.csv"
    source.write_text(
        "id,i1,i2,i3,i4\n"
        + "\n".join(
            f"p{index:03d}," + ",".join(str(int(value)) for value in row)
            for index, row in enumerate(items)
        )
        + "\n",
        encoding="utf-8",
    )
    dataset = import_csv(source)
    store = DatasetStore(root / "store")
    store.save(dataset)
    spec = ScaleDefinition(
        "Synthetic engagement",
        "1.0.0",
        ("i1", "i2", "i3", "i4"),
        reverse_items=("i4",),
        minimum=1,
        maximum=5,
        min_answered=3,
        aggregation="mean",
        subscales={"core": ("i1", "i2")},
    )
    scored = score_scale(dataset, spec, row_id="id")
    diagnostic = reliability_diagnostics(
        dataset,
        list(spec.items),
        reverse=list(spec.reverse_items),
        scale_min=1,
        scale_max=5,
        bootstrap_iterations=300,
        seed=19,
    )
    oracle = reliability(
        dataset,
        list(spec.items),
        reverse=list(spec.reverse_items),
        scale_min=1,
        scale_max=5,
    ).as_json()
    reopened = DatasetStore(root / "store").load(dataset.dataset_id, dataset.revision)
    rescored = score_scale(reopened, spec, row_id="id")
    try:
        bad = ScaleDefinition("Bad", "1", spec.items, minimum=5, maximum=1)
        score_scale(dataset, bad)
    except AnalysisError as exc:
        invalid_error = exc.code
    else:  # pragma: no cover
        raise AnalysisError("INTEGRITY_FAILURE", "Invalid scale endpoints accepted")
    return {
        "journey": "psychometric",
        "dataset_revision": dataset.revision,
        "scale_hash": spec.specification_hash,
        "score_summary": {
            "n_total": scored["n_total"],
            "n_valid": scored["n_valid"],
            "n_excluded": scored["n_excluded"],
        },
        "alpha": diagnostic["alpha"],
        "standardized_alpha": diagnostic["standardized_alpha"],
        "omega_total": diagnostic["omega_total_one_factor"],
        "oracle_alpha": oracle["estimate"],
        "alpha_matches_oracle": abs(diagnostic["alpha"] - float(oracle["estimate"])) < 1e-12,
        "restart_score_match": digest(scored) == digest(rescored),
        "limitations": diagnostic["limitations"],
        "injected_failure": invalid_error,
        "offline": True,
    }


def qualitative_audit_journey(workspace: Path) -> dict[str, Any]:
    """Unicode coding -> disagreement/adjudication -> kappa -> durable restart/tamper guard."""

    root = _ensure_workspace(workspace) / "qualitative"
    root.mkdir(exist_ok=True)
    state = QualitativeState()
    texts = {
        "s1": ("امید و فشار در پژوهش 🌱", "case1"),
        "s2": ("همکاری خوب بود اما زمان کم بود", "case2"),
        "s3": ("فشار زیاد و حمایت کم", "case3"),
        "s4": ("حمایت تیمی باعث امید شد", "case4"),
    }
    for source_id, (text, case_id) in texts.items():
        state.project.add_transcript(Transcript(source_id, text, case_id))
    state.add_code(Code("experience", "Experience"), actor="lead")
    state.add_code(Code("positive", "Positive", parent="experience"), actor="lead")
    state.add_code(Code("strain", "Strain", parent="experience"), actor="lead")
    coder_a = {"u1": "positive", "u2": "positive", "u3": "strain", "u4": "positive"}
    coder_b = {"u1": "positive", "u2": "strain", "u3": "strain", "u4": "positive"}
    for index, source_id in enumerate(texts, start=1):
        text = state.project.transcripts[source_id].text
        unit = f"u{index}"
        state.project.annotate(source_id, 0, min(5, len(text)), coder_a[unit], "coder_a", unit)
        state.project.annotate(source_id, 1, min(7, len(text)), coder_b[unit], "coder_b", unit)
    agreement = cohen_kappa(coder_a, coder_b)
    conflict_rows = disagreements(
        state.project, coder_a="coder_a", coder_b="coder_b", unit_ids=list(coder_a)
    )
    ledger = CodingReviewLedger(state.project)
    ledger.decide(2, "accept", reviewer="reviewer_1", rationale="Positive coding fits context")
    ledger.decide(2, "reject", reviewer="reviewer_2", rationale="Strain dominates this unit")
    state.attach_review_ledger(ledger)
    state.add_memo(
        Memo(
            "memo_theme",
            "Theme definition",
            "Positive experiences include explicit hope or support; strain includes pressure.",
            "lead",
            utc_now(),
            code_id="experience",
        )
    )
    matrix = case_code_matrix(state.project)
    store = QualitativeStore(root / "store")
    saved = store.save("qualitative_journey", state)
    reopened = QualitativeStore(root / "store").load("qualitative_journey")
    reopened_ledger = reopened.review_ledger()
    original_annotation = reopened.project.annotations[0]
    revised = Transcript(
        original_annotation.source_id,
        "متن کاملاً متفاوت بدون نقل قول اصلی",
        reopened.project.transcripts[original_annotation.source_id].case_id,
    )
    relocation = propose_relocation(original_annotation, revised)
    require(relocation.status == "missing", "Stale quote unexpectedly reanchored")
    return {
        "journey": "qualitative_audit",
        "source_hashes": matrix["coding_source_hashes"],
        "n_annotations": matrix["n_annotations"],
        "kappa": agreement,
        "disagreements": conflict_rows,
        "review_consensus": reopened_ledger.consensus(),
        "memo_hash": digest(asdict(reopened.memos["memo_theme"])),
        "saved_content_hash": saved["content_hash"],
        "restart_project_hash_match": digest(state.project.to_json())
        == digest(reopened.project.to_json()),
        "stale_source_relocation": asdict(relocation),
        "privacy": "quotes remain in local state; no network or automatic egress",
        "offline": True,
    }


def reproducible_script_journey(workspace: Path) -> dict[str, Any]:
    """Versioned DAG -> receipt -> process replay -> approved runtime -> denial/timeout/R path."""

    root = _ensure_workspace(workspace) / "reproducible_script"
    root.mkdir(exist_ok=True)
    source = root / "data.csv"
    source.write_text("x,y\n1,2\n2,4\n3,5\n4,8\n5,10\n", encoding="utf-8")
    store_root = root / "store"
    facade = build_analysis_facade(
        store_root,
        import_root=root,
        export_root=root,
        execution_root=root,
    )
    import_args = {"filename": source.name}
    imported = _authorized(facade, "dataset.import", import_args, request_id="repro-import")
    identity = _identity(imported)
    plan = AnalysisPlan(
        "repro_plan",
        1,
        (
            AnalysisStep("describe", "statistics.describe", {**identity, "column": "x"}),
            AnalysisStep(
                "correlate",
                "statistics.correlate",
                {**identity, "x": "x", "y": "y", "method": "pearson"},
                dependencies=("describe",),
            ),
        ),
        seed=44,
        rationale="Synthetic deterministic replay check",
    )
    receipt = execute_plan(plan, facade, {"request_id": "repro-plan"})
    receipt_path = root / "receipt.json"
    save_receipt(receipt, receipt_path)
    restored_receipt = load_receipt(receipt_path)
    restarted = build_analysis_facade(store_root)
    replayed = execute_plan(plan, restarted, {"request_id": "repro-plan"})
    replay = verify_replay(restored_receipt, replayed)
    dataset = DatasetStore(store_root).load(identity["dataset_id"], identity["revision"])
    corr_args = {**identity, "x": "x", "y": "y", "method": "pearson"}
    syntax = export_python_script("statistics.correlate", corr_args, dataset)
    syntax_path = root / "correlation_replay.py"
    save_syntax(syntax, syntax_path)
    process = subprocess.run(  # noqa: S603
        [sys.executable, str(syntax_path), str(store_root)],
        cwd=root,
        capture_output=True,
        check=False,
        shell=False,
        timeout=30,
        text=True,
        encoding="utf-8",
    )
    require(process.returncode == 0, "Generated replay process failed", "INTEGRITY_FAILURE")
    script_result = json.loads(process.stdout)
    source_code = (
        "from pathlib import Path; Path('artifact.txt').write_text('stable'); print(6 * 7)"
    )
    runtime_args = {"source": source_code, "timeout_seconds": 5}
    runtime_result = _authorized(facade, "runtime.python", runtime_args, request_id="runtime-ok")
    denied = facade.execute("runtime.python", runtime_args, {"request_id": "runtime-denied"})
    timeout_source = "import time; time.sleep(3)"
    timeout_args = {"source": timeout_source, "timeout_seconds": 1}
    timed_out = _authorized(facade, "runtime.python", timeout_args, request_id="runtime-timeout")
    r_args = {"source": "cat('researchweave-r-ok\\n')", "timeout_seconds": 5}
    r_result = _authorized(facade, "runtime.r", r_args, request_id="runtime-r")
    r_available = shutil.which("Rscript") is not None
    expected_r_status = "ok" if r_available else "failed"
    require(
        r_result["status"] == expected_r_status, "R runtime availability mapping is inconsistent"
    )
    if not r_available:
        require(
            r_result["error"]["code"] == "DEPENDENCY_MISSING", "Missing R not mapped explicitly"
        )
    return {
        "journey": "reproducible_script",
        "plan_hash": plan.spec_hash,
        "receipt_hash": receipt.output_hash,
        "restart_replay": replay,
        "syntax_sha256": syntax.source_sha256,
        "script_result_hash": digest(script_result),
        "facade_correlation_hash": digest(
            facade.execute("statistics.correlate", corr_args, {"request_id": "replay"})["data"]
        ),
        "script_matches_facade": digest(script_result)
        == digest(
            facade.execute("statistics.correlate", corr_args, {"request_id": "replay"})["data"]
        ),
        "runtime": runtime_result["data"],
        "unsigned_denial": denied["error"],
        "timeout_failure": timed_out["error"],
        "r_available": r_available,
        "r_result": r_result["data"] if r_result["status"] == "ok" else r_result["error"],
        "offline": True,
    }


def run_all_journeys(workspace: Path) -> dict[str, Any]:
    """Execute all required synthetic journeys and return one signed trace envelope."""

    root = _ensure_workspace(workspace)
    traces = {
        "intro_stats": intro_stats_journey(root),
        "survey_modeling": survey_modeling_journey(root),
        "psychometric": psychometric_journey(root),
        "qualitative_audit": qualitative_audit_journey(root),
        "reproducible_script": reproducible_script_journey(root),
    }
    payload = {
        "schema": "researchweave.analysis.journeys.v1",
        "generated_at": utc_now(),
        "offline": True,
        "journeys": traces,
    }
    payload["trace_hash"] = digest(traces)
    canonical_json(payload)
    return payload


def save_journey_trace(trace: dict[str, Any], destination: Path) -> None:
    """Persist a deterministic JSON-readable acceptance trace."""

    require(destination.parent.is_dir(), "Journey trace directory missing", "NOT_FOUND")
    require(not destination.exists(), "Journey trace destination exists", "CONFLICT")
    destination.write_bytes(canonical_json(trace))
