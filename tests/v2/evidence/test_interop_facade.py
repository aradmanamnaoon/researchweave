from __future__ import annotations

import base64
import json
from pathlib import Path

from researchweave.evidence import build_evidence_facade


def _zotero_export() -> bytes:
    return json.dumps(
        [
            {
                "id": "Z1",
                "type": "article-journal",
                "title": "Traceable migration record",
                "author": [{"family": "Doe", "given": "Ada"}],
                "issued": {"date-parts": [[2024]]},
            },
            {"id": "Z2", "type": "article-journal"},
        ]
    ).encode()


def test_facade_migration_loss_audit_preview_import_reopen_undo(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    facade = build_evidence_facade(workspace, allow_local_writes=True)
    created = facade.execute(
        "project.create",
        {"title": "Migration audit", "question": "What survives?", "design": "exploratory"},
        {},
    )
    assert created["status"] == "ok"
    project_id = created["data"]["project_id"]
    encoded = base64.b64encode(_zotero_export()).decode("ascii")

    preview = facade.execute("migration.zotero_preview", {"data_base64": encoded}, {})
    assert preview["status"] == "ok"
    assert preview["data"]["mapped"] == 1
    assert preview["data"]["skipped"] == 1
    assert preview["data"]["writes"] == 0

    imported = facade.execute(
        "migration.zotero_import",
        {"project_id": project_id, "data_base64": encoded},
        {},
    )
    assert imported["status"] == "ok"
    batch_id = imported["data"]["batch_id"]
    assert imported["data"]["receipt"]["imported"] == 1
    assert imported["data"]["receipt"]["skipped"] == 1

    exported = facade.execute(
        "migration.zotero_export",
        {"project_id": project_id, "batch_id": batch_id},
        {},
    )
    assert exported["status"] == "ok"
    assert exported["data"]["exact_original_export"] is True
    assert exported["data"]["sha256"] == preview["data"]["source_sha256"]

    reopened = build_evidence_facade(workspace, allow_local_writes=True)
    receipt = reopened.execute(
        "migration.interop_receipt",
        {"project_id": project_id, "batch_id": batch_id},
        {},
    )
    assert receipt["status"] == "ok"
    assert receipt["data"]["source_sha256"] == preview["data"]["source_sha256"]

    before_failure = (workspace / project_id / "data" / "project.sqlite").read_bytes()
    malformed = base64.b64encode(b"{broken").decode("ascii")
    failed = reopened.execute(
        "migration.zotero_import",
        {"project_id": project_id, "data_base64": malformed},
        {},
    )
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "INVALID_INPUT"
    assert (workspace / project_id / "data" / "project.sqlite").read_bytes() == before_failure

    undone = reopened.execute(
        "migration.interop_undo",
        {"project_id": project_id, "batch_id": batch_id},
        {},
    )
    assert undone["status"] == "ok"
    assert undone["data"]["removed_references"] == 1
    final = build_evidence_facade(workspace).execute(
        "library.references", {"project_id": project_id}, {}
    )
    assert final["status"] == "ok"
    assert final["data"]["records"] == []
