"""Security, corruption and bounded-resource acceptance paths for the V2 UI layer."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from researchweave.ui import build_ui_facade, workflows
from researchweave.ui.contracts import (
    Dataset,
    Preferences,
    Project,
    Source,
    UIError,
    new_id,
    utc_now,
)
from researchweave.ui.presets import WORKSPACE_SCREENS, decode_presets, save_preset
from researchweave.ui.recovery import RecoveryJournal
from researchweave.ui.store import (
    MAX_PROJECT_BYTES,
    MAX_SOURCE_CHARS,
    PreferenceStore,
    ProjectStore,
    decode_project,
)


def assert_error(call, code: str) -> UIError:
    with pytest.raises(UIError) as caught:
        call()
    assert caught.value.code == code
    assert caught.value.recovery
    return caught.value


def basic_project() -> Project:
    timestamp = utc_now()
    return Project(
        id=new_id(),
        title="Synthetic security project",
        question="What should be rejected?",
        study_type="mixed",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_project_decoder_rejects_schema_shape_identifier_and_resource_limits() -> None:
    project = basic_project()
    valid = {"schema_version": 1, "project": asdict(project)}
    assert decode_project(valid).id == project.id
    assert_error(
        lambda: decode_project({"schema_version": 99, "project": asdict(project)}),
        "SCHEMA_MISMATCH",
    )
    assert_error(lambda: decode_project({"schema_version": 1}), "INTEGRITY_FAILURE")
    malformed = {"schema_version": 1, "project": {**asdict(project), "sources": [1]}}
    assert_error(lambda: decode_project(malformed), "INTEGRITY_FAILURE")
    bad_id = {"schema_version": 1, "project": {**asdict(project), "id": "../escape"}}
    assert_error(lambda: decode_project(bad_id), "INTEGRITY_FAILURE")
    huge_source = Source(
        id=new_id(),
        title="Huge",
        text="x" * (MAX_SOURCE_CHARS + 1),
    )
    oversize = {
        "schema_version": 1,
        "project": {**asdict(project), "sources": [asdict(huge_source)]},
    }
    assert_error(lambda: decode_project(oversize), "RESOURCE_LIMIT")


def test_project_store_rejects_bad_paths_corrupt_json_and_stale_writes(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    assert store.list_projects() == []
    assert_error(lambda: store.open("../escape"), "INVALID_INPUT")
    missing_id = new_id()
    assert_error(lambda: store.open(missing_id), "NOT_FOUND")

    project = basic_project()
    saved = store.save(project, expected_revision=0)
    assert saved.revision == 1
    assert_error(lambda: store.save(saved, expected_revision=None), "STALE_REVISION")
    assert_error(
        lambda: store.save(basic_project(), expected_revision=5),
        "STALE_REVISION",
    )

    damaged_id = new_id()
    damaged = tmp_path / "projects" / f"{damaged_id}.json"
    damaged.write_text("{broken", encoding="utf-8")
    assert_error(lambda: store.open(damaged_id), "INTEGRITY_FAILURE")
    damaged.write_text("[]", encoding="utf-8")
    assert_error(lambda: store.open(damaged_id), "INTEGRITY_FAILURE")
    damaged.write_bytes(b"x" * (MAX_PROJECT_BYTES + 1))
    assert_error(lambda: store.open(damaged_id), "RESOURCE_LIMIT")
    assert [item.id for item in store.list_projects()] == [saved.id]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"theme": "neon"}, "INVALID_INPUT"),
        ({"density": "tiny"}, "INVALID_INPUT"),
        ({"scale": 1.25}, "INVALID_INPUT"),
        ({"sidebar_width": 149}, "INVALID_INPUT"),
        ({"window_width": 759}, "INVALID_INPUT"),
        ({"window_height": 489}, "INVALID_INPUT"),
        ({"locale": ""}, "INVALID_INPUT"),
        ({"workspace_presets": [{}] * 51}, "RESOURCE_LIMIT"),
        ({"workspace_presets": ["bad"]}, "INVALID_INPUT"),
        ({"panel_visibility": {"sidebar": 1}}, "INVALID_INPUT"),
        ({"panel_sizes": {"sidebar": "wide"}}, "INVALID_INPUT"),
    ],
)
def test_preference_validation_rejects_invalid_state(
    changes: dict[str, Any],
    code: str,
) -> None:
    preferences = replace(Preferences(), **changes)
    assert_error(lambda: PreferenceStore.validate(preferences), code)


def test_preference_store_falls_back_from_corrupt_old_and_oversize_files(tmp_path: Path) -> None:
    store = PreferenceStore(tmp_path)
    assert store.load() == Preferences()
    store.path.write_text("{bad", encoding="utf-8")
    assert store.load() == Preferences()
    store.path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    assert store.load() == Preferences()
    store.path.write_text("[]", encoding="utf-8")
    assert store.load() == Preferences()
    store.path.write_bytes(b"x" * 32769)
    assert store.load() == Preferences()
    store.save(Preferences(theme="dark", locale="en-US"))
    assert store.load().theme == "dark"


def test_recovery_rejects_bad_targets_stale_corrupt_and_mismatched_hash(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.save(basic_project(), expected_revision=0)
    journal = RecoveryJournal(store)
    assert_error(lambda: journal.save(project.id, "unknown", "x", 1), "INVALID_INPUT")
    assert_error(lambda: journal.save(project.id, "notebook", "x", 0), "STALE_REVISION")
    assert_error(
        lambda: journal.save(project.id, "notebook", "x" * 250_001, 1),
        "RESOURCE_LIMIT",
    )
    assert_error(lambda: journal.inspect(project.id, "notebook"), "NOT_FOUND")

    good = journal.save(project.id, "notebook", "recover me", 1)
    path = journal._path(project.id, "notebook")
    path.write_text("{broken", encoding="utf-8")
    assert_error(lambda: journal.inspect(project.id, "notebook"), "INTEGRITY_FAILURE")
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_id": project.id,
                "field": "notebook",
                "base_revision": 1,
                "text": "recover me",
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    assert_error(lambda: journal.inspect(project.id, "notebook"), "INTEGRITY_FAILURE")
    listing = journal.list(project.id)
    assert listing["drafts"][0]["integrity_error"] == "INTEGRITY_FAILURE"
    path.unlink()
    journal.save(project.id, "notebook", "recover me", 1)
    assert_error(
        lambda: journal.discard(project.id, "notebook", "0" * 64),
        "STALE_REVISION",
    )
    assert journal.discard(project.id, "notebook", good["sha256"])["discarded"] is True


def test_workspace_presets_reject_capacity_and_sanitize_corruption() -> None:
    decoded, warnings = decode_presets("bad", known_screens=WORKSPACE_SCREENS)
    assert decoded == []
    assert warnings
    corrupt = [
        "not-object",
        {"name": ""},
        {"name": "bad-id", "id": 3},
        {"name": "dup", "id": "same"},
        {"name": "dup2", "id": "same"},
    ]
    decoded, warnings = decode_presets(corrupt, known_screens=WORKSPACE_SCREENS)
    assert len(decoded) == 1
    assert len(warnings) == 4
    full = [
        {
            "id": new_id(),
            "name": f"Preset {index}",
            "active_screen": "Dashboard",
        }
        for index in range(50)
    ]
    assert_error(
        lambda: save_preset(
            full,
            {"name": "Overflow", "active_screen": "Dashboard"},
            known_screens=WORKSPACE_SCREENS,
        ),
        "RESOURCE_LIMIT",
    )


def _schema_project() -> tuple[Project, str]:
    project = basic_project()
    source = Source(id=new_id(), title="Synthetic", text="text")
    project.sources.append(source)
    return project, source.id


@pytest.mark.parametrize(
    "fields",
    [
        [],
        [{"name": "1bad", "field_type": "text"}],
        [
            {"name": "dup", "field_type": "text"},
            {"name": "dup", "field_type": "text"},
        ],
        [{"name": "bad", "field_type": "binary"}],
        [{"name": "group", "field_type": "categorical", "categories": []}],
        [
            {
                "name": "group",
                "field_type": "categorical",
                "categories": ["A", "A"],
            }
        ],
    ],
)
def test_extraction_schema_rejects_invalid_field_definitions(
    fields: list[dict[str, Any]],
) -> None:
    project, _ = _schema_project()
    assert_error(
        lambda: workflows.set_extraction_schema(project, title="Form", fields=fields),
        "INVALID_INPUT" if len(fields) != 2 else "CONFLICT",
    )


def test_extraction_value_validation_covers_all_supported_types_and_failures() -> None:
    project, source_id = _schema_project()
    workflows.set_extraction_schema(
        project,
        title="Typed extraction",
        fields=[
            {"name": "text", "field_type": "text", "required": True},
            {"name": "n", "field_type": "integer", "required": True},
            {"name": "x", "field_type": "float", "required": True},
            {"name": "flag", "field_type": "boolean", "required": True},
            {"name": "date", "field_type": "date", "required": True},
            {
                "name": "group",
                "field_type": "categorical",
                "categories": ["A", "B"],
                "required": True,
            },
            {"name": "quote", "field_type": "source-passage", "required": False},
        ],
    )
    base = {
        "text": "ok",
        "n": 3,
        "x": 1.5,
        "flag": True,
        "date": "2026-10-23",
        "group": "A",
        "quote": "source passage",
    }
    saved = workflows.save_extraction(project, source_id=source_id, values=base)
    assert saved["values"]["x"] == 1.5
    cases = [
        ({**base, "n": True}, "INVALID_INPUT"),
        ({**base, "x": "1.5"}, "INVALID_INPUT"),
        ({**base, "x": float("inf")}, "INVALID_INPUT"),
        ({**base, "flag": "true"}, "INVALID_INPUT"),
        ({**base, "date": "23-10-2026"}, "INVALID_INPUT"),
        ({**base, "date": "2026-02-31"}, "INVALID_INPUT"),
        ({**base, "group": "C"}, "INVALID_INPUT"),
        ({**base, "extra": "no"}, "INVALID_INPUT"),
        ({**base, "text": ""}, "INVALID_INPUT"),
    ]
    for values, code in cases:
        assert_error(
            lambda values=values: workflows.save_extraction(
                project, source_id=source_id, values=values
            ),
            code,
        )
    assert_error(
        lambda: workflows.save_extraction(project, source_id=new_id(), values=base),
        "NOT_FOUND",
    )
    empty = basic_project()
    assert_error(
        lambda: workflows.save_extraction(empty, source_id=new_id(), values={}),
        "NOT_FOUND",
    )


def test_variable_analysis_provider_integration_and_notification_denials() -> None:
    project = basic_project()
    project.datasets.append(Dataset(id=new_id(), name="Synthetic", columns=["x"], rows=[["1"]]))
    dataset_id = project.datasets[0].id
    assert_error(
        lambda: workflows.set_variable_metadata(
            project,
            dataset_id=dataset_id,
            variable="missing",
            metadata={"type": "numeric", "role": "outcome"},
        ),
        "NOT_FOUND",
    )
    for metadata in (
        {"type": "bad", "role": "outcome"},
        {"type": "numeric", "role": "bad"},
        {"type": "categorical", "role": "group", "levels": ["A", "A"]},
        {"type": "numeric", "role": "outcome", "missing_codes": ["-99", "-99"]},
    ):
        assert_error(
            lambda metadata=metadata: workflows.set_variable_metadata(
                project, dataset_id=dataset_id, variable="x", metadata=metadata
            ),
            "INVALID_INPUT",
        )
    assert_error(
        lambda: workflows.validate_analysis_result({"method": "x"}),
        "INTEGRITY_FAILURE",
    )
    assert_error(
        lambda: workflows.configure_provider(project, {"mode": "unsupported"}),
        "INVALID_INPUT",
    )
    ollama = workflows.configure_provider(
        project,
        {
            "mode": "local",
            "provider_id": "ollama-local",
            "protocol": "ollama",
            "endpoint": "http://127.0.0.1:11434",
            "model": "synthetic:latest",
            "enabled": True,
        },
    )
    assert ollama["protocol"] == "ollama"
    assert ollama["mode"] == "local"
    assert ollama["credential_present"] is False
    assert ollama["egress_acknowledged"] is False
    assert_error(
        lambda: workflows.configure_provider(
            project,
            {
                "mode": "cloud-api",
                "provider_id": "ollama-remote",
                "protocol": "ollama",
                "endpoint": "https://example.org",
                "model": "synthetic:latest",
                "enabled": True,
            },
        ),
        "INVALID_INPUT",
    )
    assert_error(
        lambda: workflows.configure_provider(
            project,
            {
                "mode": "local",
                "provider_id": "ollama-tools",
                "protocol": "ollama",
                "endpoint": "http://127.0.0.1:11434",
                "model": "synthetic:latest",
                "tool_calling": True,
                "enabled": True,
            },
        ),
        "INVALID_INPUT",
    )
    assert_error(
        lambda: workflows.configure_provider(
            project,
            {
                "mode": "cloud-api",
                "provider_id": "example",
                "enabled": True,
                "credential_present": False,
            },
        ),
        "PROVIDER_UNAVAILABLE",
    )
    assert_error(
        lambda: workflows.configure_provider(
            project,
            {
                "mode": "cloud-api",
                "provider_id": "example",
                "enabled": True,
                "credential_present": True,
                "egress_acknowledged": False,
            },
        ),
        "NEEDS_APPROVAL",
    )
    assert_error(
        lambda: workflows.set_integration(
            project,
            integration_id="crossref",
            connected=True,
            permissions=["reference-metadata"],
        ),
        "DEPENDENCY_MISSING",
    )
    assert_error(
        lambda: workflows.set_integration(
            project,
            integration_id="unknown",
            connected=False,
            permissions=[],
        ),
        "NOT_FOUND",
    )
    assert_error(
        lambda: workflows.add_notification(
            project,
            code="SECRET",
            severity="error",
            message="api_key=super-secret",
            recovery="rotate it",
        ),
        "UNTRUSTED_CONTENT",
    )


def test_csv_export_neutralizes_spreadsheet_formulas_and_collision(tmp_path: Path) -> None:
    facade = build_ui_facade(tmp_path, export_authorizer=lambda _name: True)
    created = facade.execute(
        "ui.project.create",
        {"title": "CSV security", "question": "Safe export?", "study_type": "quantitative"},
    )["data"]
    imported = facade.execute(
        "ui.dataset.import",
        {
            "project_id": created["project_id"],
            "expected_revision": created["revision"],
            "name": "Malicious-looking cells",
            "csv_text": "a,b,c,d\n=2+3,+cmd,-10,@SUM(A1:A2)\n",
        },
    )
    assert imported["status"] == "ok", imported
    preview = facade.execute(
        "ui.export.preview",
        {"project_id": created["project_id"], "filename": "safe.csv"},
    )
    assert preview["status"] == "ok"
    written = facade.execute(
        "ui.export.write",
        {"project_id": created["project_id"], "filename": "safe.csv"},
    )
    assert written["status"] == "ok", written
    assert written["data"]["atomic_write"] is True
    assert written["data"]["collision_policy"] == "refuse-existing"
    assert written["data"]["source_metadata"]["project_id"] == created["project_id"]
    assert written["data"]["source_metadata"]["dataset_id"] == imported["data"]["dataset_id"]
    content = Path(written["data"]["path"]).read_text(encoding="utf-8")
    assert "'=2+3" in content
    assert "'+cmd" in content
    assert "'-10" in content
    assert "'@SUM(A1:A2)" in content
    second = facade.execute(
        "ui.export.write",
        {"project_id": created["project_id"], "filename": "safe.csv"},
    )
    assert second["error"]["code"] == "CONFLICT"
    assert not list((tmp_path / "exports").glob("*.tmp"))
