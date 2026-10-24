"""INT-041 integrated row-linked quality screening acceptance."""

from __future__ import annotations

from pathlib import Path

from researchweave.app.composition import build_services
from researchweave.app.desktop_gateway import DesktopCommandGateway


def _project(gateway: DesktopCommandGateway) -> dict:
    response = gateway.execute(
        "ui.project.create",
        {
            "title": "Quality fixture",
            "question": "Are quality warnings traceable?",
            "study_type": "quantitative",
        },
    )
    assert response["status"] == "ok", response
    return dict(response["data"])


def test_int_041_row_links_lineage_and_test_leakage_fail_visible(tmp_path: Path) -> None:
    services = build_services(tmp_path)
    try:
        gateway = DesktopCommandGateway(services.ui, services.bus)
        project = _project(gateway)
        imported = gateway.execute(
            "ui.dataset.import",
            {
                "project_id": project["project_id"],
                "expected_revision": project["revision"],
                "name": "Synthetic split quality",
                "csv_text": (
                    "subject,split,x,y\n"
                    "s1,train,1,2\n"
                    "s1,test,2,4\n"
                    "s2,train,,6\n"
                    "s3,test,4,8\n"
                ),
            },
        )
        assert imported["status"] == "ok", imported
        dataset = imported["data"]
        result = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project["project_id"],
                "expected_revision": dataset["revision"],
                "method": "analysis.dataset.quality",
                "inputs": {
                    "dataset_id": dataset["dataset_id"],
                    "subject_column": "subject",
                    "split_column": "split",
                    "train_values": ["train"],
                    "test_values": ["test"],
                },
            },
        )
        assert result["status"] == "ok", result
        record = result["data"]["result"]
        warnings = record["estimates"]["warnings"]
        kinds = {item["kind"] for item in warnings}
        assert {"missingness", "duplicate_subject", "test_set_leakage"} <= kinds
        leakage = next(item for item in warnings if item["kind"] == "test_set_leakage")
        assert leakage["row_indices"] == [0, 1]
        assert leakage["dataset_revision"]
        assert isinstance(leakage["transformation"], dict)
        assert record["estimates"]["mutated"] is False
        assert "dataset.quality" in [event["operation"] for event in services.audit.events()]

        before = len(services.ui.store.open(project["project_id"]).analysis_results)
        invalid = gateway.execute(
            "ui.analysis.run",
            {
                "project_id": project["project_id"],
                "expected_revision": result["data"]["revision"],
                "method": "analysis.dataset.quality",
                "inputs": {
                    "dataset_id": dataset["dataset_id"],
                    "split_column": "split",
                    "train_values": ["train"],
                    "test_values": ["test"],
                },
            },
        )
        assert invalid["status"] == "failed", invalid
        assert invalid["error"]["code"] == "INVALID_INPUT"
        assert len(services.ui.store.open(project["project_id"]).analysis_results) == before
    finally:
        services.close()
