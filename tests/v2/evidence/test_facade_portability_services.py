from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from researchweave.evidence import build_evidence_facade


def _encoded(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return base64.b64encode(data).decode("ascii")


def _call(facade, operation: str, **arguments):
    result = facade.execute(operation, arguments, {})
    assert result["status"] == "ok", json.dumps(result, ensure_ascii=False)
    return result["data"]


def test_public_facade_exposes_portability_monitoring_and_management(tmp_path: Path) -> None:
    credential = "fixture-secret-value"
    workspace = tmp_path / "workspace"
    facade = build_evidence_facade(workspace, allow_local_writes=True)
    project_id = _call(
        facade,
        "project.create",
        title="Integrated evidence",
        question="Can the project remain traceable?",
        design="systematic_review",
    )["project_id"]
    source = _call(
        facade,
        "library.import",
        project_id=project_id,
        title="Synthetic source",
        media_type="text/plain",
        data_base64=_encoded("portable local evidence"),
    )
    imported = _call(
        facade,
        "library.bibliography_import",
        project_id=project_id,
        format="bibtex",
        data_base64=_encoded(
            "@article{x,title={Traceable Trial},author={Doe, Ada},"
            "year={2024},doi={10.1000/trace}}"
        ),
    )
    reference_id = imported["references"][0]["id"]

    rebuilt = _call(facade, "library.index_rebuild", project_id=project_id)
    assert rebuilt["sources"] == 1
    synced = _call(facade, "library.index_sync", project_id=project_id)
    assert synced["unchanged"] == 2
    assert _call(facade, "library.diagnostics", project_id=project_id)["read_only"]

    collection = _call(
        facade, "library.collection_create", project_id=project_id, name="Included"
    )
    _call(
        facade,
        "library.collection_add",
        project_id=project_id,
        collection_id=collection["collection_id"],
        reference_ids=[reference_id],
    )
    _call(
        facade,
        "library.reference_tag",
        project_id=project_id,
        reference_ids=[reference_id],
        tags=["priority"],
    )
    filtered = _call(
        facade,
        "library.collection_search",
        project_id=project_id,
        collection_id=collection["collection_id"],
        tag="priority",
    )
    assert filtered["records"][0]["id"] == reference_id

    _call(
        facade,
        "reference.watch",
        project_id=project_id,
        reference_id=reference_id,
        provider="manual",
    )
    observation = _call(
        facade,
        "reference.update_observation",
        project_id=project_id,
        reference_id=reference_id,
        provider="manual",
        observed={"title": "Traceable Trial", "is_corrected": True},
    )
    assert observation["correction_reported"] is True
    history = _call(
        facade,
        "reference.update_history",
        project_id=project_id,
        reference_id=reference_id,
    )
    assert history["records"][0]["metadata_updated"] is False

    dmp = _call(
        facade,
        "data_management.create",
        project_id=project_id,
        title="DMP",
        inventory=[{
            "id": "source-1",
            "description": "Synthetic evidence",
            "sensitivity": "internal",
            "location": "project objects",
        }],
        policies={
            "storage": "local",
            "access": "project owner",
            "retention": "review after five years",
            "preservation": "open formats",
            "sharing": "review before sharing",
            "privacy": "synthetic data only",
        },
        rationale="Record handling decisions.",
        unresolved=[],
        author="Researcher",
    )
    rendered = _call(
        facade,
        "data_management.export",
        project_id=project_id,
        plan_id=dmp["plan_id"],
    )
    assert "Data inventory" in rendered["text"]

    recovery = _call(
        facade, "project.recovery_snapshot", project_id=project_id, label="checkpoint"
    )
    snapshots = _call(facade, "project.recovery_list", project_id=project_id)
    assert snapshots["snapshots"][0]["snapshot"] == recovery["snapshot"]

    artifacts = _call(
        facade,
        "project.artifact_export",
        project_id=project_id,
        filename="evidence.rw-artifacts.zip",
    )
    assert Path(artifacts["path"]).is_file()

    clone = _call(
        facade,
        "project.selective_clone",
        project_id=project_id,
        source_ids=[source["source_id"]],
        reference_ids=[reference_id],
    )
    clone_open = _call(
        facade, "project.open", project_id=clone["destination_project_id"]
    )
    assert clone_open["id"] == clone["destination_project_id"]

    encrypted = _call(
        facade,
        "project.archive_encrypted",
        project_id=project_id,
        filename="secure.rwproj.enc",
        password=credential,
    )
    assert encrypted["cipher"] == "AES-256-GCM"
    verified = _call(
        facade,
        "project.archive_encrypted_verify",
        filename="secure.rwproj.enc",
        password=credential,
    )
    assert verified["project_id"] == project_id

    read_only = build_evidence_facade(workspace)
    denied = read_only.execute(
        "library.collection_create",
        {"project_id": project_id, "name": "Denied"},
        {},
    )
    assert denied["error"]["code"] == "NEEDS_APPROVAL"


def test_encrypted_facade_restore_after_local_project_loss(tmp_path: Path) -> None:
    credential = "fixture-backup-value"
    workspace = tmp_path / "workspace"
    facade = build_evidence_facade(workspace, allow_local_writes=True)
    project_id = _call(
        facade,
        "project.create",
        title="Backup survival",
        question="Will encrypted restore preserve identity?",
        design="exploratory",
    )["project_id"]
    _call(
        facade,
        "library.import",
        project_id=project_id,
        title="Source",
        media_type="text/plain",
        data_base64=_encoded("survives"),
    )
    _call(
        facade,
        "project.archive_encrypted",
        project_id=project_id,
        filename="survival.rwproj.enc",
        password=credential,
    )
    shutil.rmtree(workspace / project_id)
    restored = _call(
        facade,
        "project.restore_encrypted",
        filename="survival.rwproj.enc",
        password=credential,
    )
    assert restored["project_id"] == project_id
    reopened = _call(facade, "project.open", project_id=project_id)
    assert reopened["revision"] == 1
