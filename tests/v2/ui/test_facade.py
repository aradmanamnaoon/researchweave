"""Meaningful local project journeys and intentionally rejected effects."""

from __future__ import annotations

from pathlib import Path

from researchweave.ui import build_ui_facade
from researchweave.ui.facade import UIFacade


def run(facade: UIFacade, operation: str, **args):
    response = facade.execute(operation, args)
    assert response["status"] == "ok", response
    return response["data"]


def test_beginner_journey_roundtrip(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    project = run(
        facade,
        "ui.project.create",
        title="Attention and memory",
        question="How is attention described?",
        study_type="literature",
    )
    pid, revision = project["project_id"], project["revision"]
    source = run(
        facade,
        "ui.source.add",
        project_id=pid,
        expected_revision=revision,
        title="Synthetic example",
        text="A 🧠 is mentioned in this synthetic note.",
        source_label="Synthetic fixture",
    )
    source_id, revision = source["source_id"], source["revision"]
    vote = run(
        facade,
        "ui.review.vote",
        project_id=pid,
        expected_revision=revision,
        source_id=source_id,
        decision="include",
    )
    revision = vote["revision"]
    assert run(facade, "ui.review.counts", project_id=pid)["include"] == 1
    span = run(
        facade,
        "ui.qual.annotate",
        project_id=pid,
        expected_revision=revision,
        source_id=source_id,
        start=2,
        end=3,
        code="emoji",
    )
    assert span["annotation"]["quote"] == "🧠"
    revision = span["revision"]
    notes = run(
        facade,
        "ui.notebook.save",
        project_id=pid,
        expected_revision=revision,
        notebook="Unverified synthetic evidence requires inspection.",
    )
    facade2 = build_ui_facade(tmp_path)
    opened = run(facade2, "ui.project.open", project_id=pid)["project"]
    assert opened["revision"] == notes["revision"]
    assert opened["annotations"][0]["quote"] == "🧠"
    assert opened["notebook"].startswith("Unverified")
    preview = run(facade2, "ui.export.preview", project_id=pid, filename="notes.md")
    assert preview["bytes"] > 40
    denied = facade2.execute(
        "ui.export.write", {"project_id": pid, "filename": "notes.md", "approved": True}
    )
    assert denied["status"] == "failed"
    assert denied["error"]["code"] == "NEEDS_APPROVAL"
    assert not (tmp_path / "exports" / "notes.md").exists()
    allowed = UIFacade(tmp_path, export_authorizer=lambda name: name == "notes.md")
    receipt = run(allowed, "ui.export.write", project_id=pid, filename="notes.md")
    assert Path(receipt["path"]).read_text(encoding="utf-8").startswith("# Attention")
    second_export = allowed.execute("ui.export.write", {"project_id": pid, "filename": "notes.md"})
    assert second_export["error"]["code"] == "CONFLICT"


def test_stale_revision_invalid_screening_and_unicode(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    project = run(
        facade, "ui.project.create", title="Pilot", question="Question?", study_type="qualitative"
    )
    pid = project["project_id"]
    bad = facade.execute(
        "ui.source.add",
        {"project_id": pid, "expected_revision": 0, "title": "Lost", "text": "hello"},
    )
    assert bad["error"]["code"] == "STALE_REVISION"
    assert run(facade, "ui.source.search", project_id=pid)["total"] == 0
    source = run(
        facade, "ui.source.add", project_id=pid, expected_revision=1, title="فارسی", text="a👩🏽‍🔬b"
    )
    rejected = facade.execute(
        "ui.review.vote",
        {
            "project_id": pid,
            "expected_revision": 2,
            "source_id": source["source_id"],
            "decision": "exclude",
            "reason": "",
        },
    )
    assert rejected["error"]["code"] == "INVALID_INPUT"
    assert run(facade, "ui.review.counts", project_id=pid)["pending"] == 1
    preview = facade.execute(
        "ui.notebook.save",
        {"project_id": pid, "expected_revision": 2, "notebook": "should not save"},
        {"preview": True},
    )
    assert preview["data"]["preview_only"]
    assert run(facade, "ui.project.open", project_id=pid)["project"]["notebook"] == ""
    malicious = facade.execute("ui.agent.deny", {"summary": "Delete all files", "approved": True})
    assert malicious["data"]["executed"] is False


def test_csv_counts_and_restricted_exports(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    project = run(
        facade,
        "ui.project.create",
        title="Numeric demo",
        question="Describe synthetic scores",
        study_type="quantitative",
    )
    pid = project["project_id"]
    dataset = run(
        facade,
        "ui.dataset.import",
        project_id=pid,
        expected_revision=1,
        name="Synthetic scores",
        csv_text="score,group\n1,A\n2,B\n,unknown\n4,A\n",
    )
    result = run(
        facade,
        "ui.dataset.describe",
        project_id=pid,
        dataset_id=dataset["dataset_id"],
        column="score",
    )
    assert result["n"] == 3
    assert result["excluded_n"] == 1
    assert result["median"] == 2.0
    assert abs(result["mean"] - 7 / 3) < 1e-12
    malformed = facade.execute(
        "ui.dataset.import",
        {"project_id": pid, "expected_revision": 2, "name": "bad", "csv_text": "a,b\n1\n"},
    )
    assert malformed["error"]["code"] == "INVALID_INPUT"
    traversal = facade.execute(
        "ui.export.preview", {"project_id": pid, "filename": "../sensitive.md"}
    )
    assert traversal["error"]["code"] == "INVALID_INPUT"
    assert run(facade, "ui.project.open", project_id=pid)["project"]["revision"] == 2


def test_preferences_corruption_and_overrides(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    current = run(facade, "ui.preferences.update", theme="dark", scale=1.5)
    assert current["preferences"]["theme"] == "dark"
    assert build_ui_facade(tmp_path).settings.load().scale == 1.5
    invalid = facade.execute("ui.preferences.update", {"theme": "evil"})
    assert invalid["error"]["code"] == "INVALID_INPUT"
    (tmp_path / "ui-preferences.json").write_text("{broken", encoding="utf-8")
    assert facade.settings.load().theme == "light"


def test_deterministic_idempotency(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path)
    args = {"title": "one", "question": "Why?", "study_type": "literature"}
    first = facade.execute("ui.project.create", args, {"request_id": "stable-key"})
    second = facade.execute("ui.project.create", args, {"request_id": "stable-key"})
    assert first == second
    assert len(facade.store.list_projects()) == 1
