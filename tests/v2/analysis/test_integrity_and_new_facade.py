import json
from pathlib import Path

import pytest

from researchweave.analysis import build_analysis_facade
from researchweave.analysis.datasets import DatasetStore, import_csv
from researchweave.analysis.errors import AnalysisError


def test_reject_unsafe_custom_dataset_id(tmp_path: Path):
    path = tmp_path / "input.csv"
    path.write_text("x\n1\n2\n", encoding="utf-8")
    with pytest.raises(AnalysisError, match="Invalid dataset ID"):
        import_csv(path, dataset_id="../../../../escape")
    with pytest.raises(AnalysisError, match="Invalid dataset ID"):
        DatasetStore(tmp_path / "store").load("../other", "a" * 64)


def test_stored_revision_detects_modified_payload_even_if_metadata_matches(tmp_path: Path):
    path = tmp_path / "input.csv"
    path.write_text("x\n1\n2\n", encoding="utf-8")
    obj = import_csv(path)
    store = DatasetStore(tmp_path / "store")
    snapshot = store.save(obj)
    envelope = json.loads(snapshot.read_text(encoding="utf-8"))
    envelope["dataset"]["records"][0]["x"] = "999"
    snapshot.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(AnalysisError, match="INTEGRITY_FAILURE"):
        store.load(obj.dataset_id, obj.revision)


def test_new_facade_methods_end_to_end(tmp_path: Path):
    path = tmp_path / "cases.csv"
    path.write_text(
        "duration,event,group\n1,1,A\n2,0,A\n3,1,A\n4,1,B\n5,0,B\n6,1,B\n", encoding="utf-8"
    )
    facade = build_analysis_facade(tmp_path / "store")
    imported = facade.execute(
        "dataset.import",
        {"filename": path.name},
        {"host_authorized": True, "trusted_import_root": tmp_path},
    )
    assert imported["status"] == "ok", imported
    identity = {
        "dataset_id": imported["data"]["dataset_id"],
        "revision": imported["data"]["revision"],
    }
    survival = facade.execute(
        "statistics.survival", {**identity, "duration": "duration", "event": "event"}, {}
    )
    assert survival["status"] == "ok", survival
    assert survival["data"]["n_events"] == 4
    logrank = facade.execute(
        "statistics.logrank",
        {
            **identity,
            "duration": "duration",
            "event": "event",
            "group": "group",
            "levels": ["A", "B"],
        },
        {},
    )
    assert logrank["status"] == "ok", logrank
    assert 0 <= logrank["data"]["p_value"] <= 1
    fleiss = facade.execute(
        "statistics.fleiss", {"rating_counts": [[3, 0], [1, 2], [2, 1], [0, 3]]}, {}
    )
    assert fleiss["status"] == "ok", fleiss
