"""Real dataset pagination and screening source selection contracts."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell


def _ok(facade, action, **kwargs):
    response = facade.execute(action, kwargs)
    assert response["status"] == "ok", response
    return response["data"]


def test_dataset_page_and_variable_missingness(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    project = _ok(facade, "ui.project.create", title="Data",
                  question="How large is the invented sample?",
                  study_type="quantitative")
    data = "score,category\n" + "".join(
        f"{i if i % 11 else ''},c{i % 3}\n" for i in range(10_000)
    )
    dataset = _ok(facade, "ui.dataset.import", name="Synthetic large table",
                  csv_text=data, project_id=project["project_id"],
                  expected_revision=project["revision"])
    first = _ok(facade, "ui.dataset.page",
                project_id=project["project_id"], dataset_id=dataset["dataset_id"],
                offset=0, limit=250)
    middle = _ok(facade, "ui.dataset.page",
                 project_id=project["project_id"], dataset_id=dataset["dataset_id"],
                 offset=250, limit=250)
    assert first["total"] == 10_000
    assert len(first["rows"]) == 250
    assert middle["rows"][0] == ["250", "c1"]
    assert len(first["rows"]) < first["total"]
    filtered = _ok(
        facade,
        "ui.dataset.page",
        project_id=project["project_id"],
        dataset_id=dataset["dataset_id"],
        offset=0,
        limit=50,
        filter_text="c2",
        sort_column="score",
        sort_desc=True,
    )
    assert filtered["read_only"] is True
    assert filtered["dataset_total"] == 10_000
    assert filtered["total"] < filtered["dataset_total"]
    assert all("c2" in row for row in filtered["rows"])
    assert filtered["rows"][0][0] >= filtered["rows"][-1][0]
    invalid_sort = facade.execute(
        "ui.dataset.page",
        {
            "project_id": project["project_id"],
            "dataset_id": dataset["dataset_id"],
            "sort_column": "missing-column",
        },
    )
    assert invalid_sort["error"]["code"] == "INVALID_INPUT"
    columns = _ok(facade, "ui.dataset.variables",
                  project_id=project["project_id"], dataset_id=dataset["dataset_id"])
    assert columns["variables"][0]["inferred_type"] == "numeric"
    assert columns["variables"][0]["missing_n"] == 910
    assert columns["variables"][1]["inferred_type"] == "text"
    oversized = facade.execute("ui.dataset.page", {
        "project_id": project["project_id"],
        "dataset_id": dataset["dataset_id"], "limit": 10_000,
    })
    assert oversized["error"]["code"] == "INVALID_INPUT"


def test_review_queue_and_selected_screening(tmp_path: Path) -> None:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    facade = build_ui_facade(tmp_path)
    project = _ok(facade, "ui.project.create", title="Screen",
                  question="Which invented source belongs?",
                  study_type="literature")
    pid = project["project_id"]
    first = _ok(facade, "ui.source.add", title="A", text="invented A",
                project_id=pid, expected_revision=1)
    second = _ok(facade, "ui.source.add", title="B", text="invented B",
                 project_id=pid, expected_revision=2)
    queue = _ok(facade, "ui.review.queue", project_id=pid, decision="pending")
    assert queue["total"] == 2
    window = build_ui_shell(fake_services=facade)
    window.open_project(pid)
    window.navigate("Review")
    assert window.review_queue.count() == 2
    window.review_queue.setCurrentRow(0)
    assert window.current_source_id == first["source_id"]
    window.vote("include")
    included = _ok(facade, "ui.review.queue", project_id=pid, decision="include")
    assert len(included["records"]) == 1
    assert included["records"][0]["source_id"] == first["source_id"]
    assert _ok(facade, "ui.review.counts", project_id=pid)["pending"] == 1
    window.review_filter.setCurrentText("pending")
    assert window.review_queue.count() == 1
    assert window.review_queue.item(0).data(256) == second["source_id"]
    window.close()
