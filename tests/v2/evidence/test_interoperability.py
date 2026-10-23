from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.interoperability import (
    InteroperabilityService,
    VaultRecord,
    ZoteroLocalBridge,
    preview_obsidian_vault,
    preview_zotero_export,
)
from researchweave.evidence.storage import ProjectStore


def _zotero_export() -> bytes:
    return json.dumps([
        {
            "id": "Z1",
            "type": "article-journal",
            "title": "Unicode شواهد",
            "author": [{"family": "Doe", "given": "Ada"}],
            "issued": {"date-parts": [[2024]]},
            "DOI": "https://doi.org/10.1000/TRACE",
            "collections": ["systematic-review"],
            "notes": ["screen manually"],
            "attachments": [{"title": "PDF", "path": "not-in-csl-export"}],
            "custom": "preserved in raw export",
        },
        {
            "id": "Z2",
            "type": "article-journal",
            "author": [{"literal": "No title consortium"}],
        },
    ], ensure_ascii=False).encode("utf-8")


def test_zotero_export_preview_import_receipt_reopen_and_undo(tmp_path: Path) -> None:
    data = _zotero_export()
    preview = preview_zotero_export(data)
    assert preview["read"] == 2
    assert preview["mapped"] == 1
    assert preview["skipped"] == 1
    assert preview["records"][0]["doi"] == "10.1000/trace"
    assert "attachment_metadata_preserved_but_attachment_bytes_not_in_csl_json" in (
        preview["information_loss"]
    )

    root = tmp_path / "project"
    with ProjectStore.create(root, "Interop", "Can migration be audited?", "exploratory") as store:
        service = InteroperabilityService(store)
        imported = service.import_zotero(data)
        assert imported["receipt"]["imported"] == 1
        batch_id = imported["batch_id"]
        reference_id = imported["reference_ids"][0]
        row = store.conn.execute(
            "SELECT metadata_json,raw FROM reference WHERE id=?", (reference_id,)
        ).fetchone()
        assert json.loads(row["metadata_json"])["batch_id"] == batch_id
        assert "preserved in raw export" in row["raw"]
        receipt = service.receipt(batch_id)
        assert store.get_object(receipt["raw_digest"]) == data
    with ProjectStore(root) as reopened:
        service = InteroperabilityService(reopened)
        assert service.receipt(batch_id)["undone"] is False
        undone = service.undo(batch_id)
        assert undone["removed_references"] == 1
    with ProjectStore(root) as reopened:
        assert reopened.conn.execute("SELECT COUNT(*) FROM reference").fetchone()[0] == 0
        assert InteroperabilityService(reopened).receipt(batch_id)["undone"] is True
        assert reopened.audit()["ok"]


def test_zotero_undo_refuses_downstream_review_dependency(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Interop", "Question", "systematic_review"
    ) as store:
        service = InteroperabilityService(store)
        imported = service.import_zotero(_zotero_export())
        reference_id = imported["reference_ids"][0]
        store.mutate(
            "fixture.review_dependency",
            {"reference_id": reference_id},
            lambda conn: conn.execute(
                "INSERT INTO review_records VALUES (?,?,?,?,?)",
                ("record-1", "review-1", reference_id, "study-1", "title_abstract"),
            ),
            expected_revision=store.info().revision,
        )
        with pytest.raises(EvidenceError) as conflict:
            service.undo(imported["batch_id"])
        assert conflict.value.code == "CONFLICT"
        assert store.conn.execute(
            "SELECT COUNT(*) FROM reference WHERE id=?", (reference_id,)
        ).fetchone()[0] == 1


def test_obsidian_bidirectional_roundtrip_links_and_path_traversal(tmp_path: Path) -> None:
    records = [
        VaultRecord("Methods/Index.md", b"# Index\nSee [[Result]] and ![[Figure]]."),
        VaultRecord("Methods/Result.md", "نتیجه".encode()),
        VaultRecord("Methods/Figure.md", b"asset metadata note"),
    ]
    preview = preview_obsidian_vault(records)
    assert preview["records"][0]["wikilinks"] == ["Methods/Result.md"]
    assert preview["records"][0]["embeds"] == ["Methods/Figure.md"]
    assert preview["records"][0]["unresolved_targets"] == []
    with pytest.raises(EvidenceError) as traversal:
        VaultRecord("../secret.md", b"no")
    assert traversal.value.code == "UNSAFE_DOCUMENT"
    with pytest.raises(EvidenceError):
        preview_obsidian_vault([VaultRecord("safe.md", b"[[../secret]]")])

    root = tmp_path / "project"
    with ProjectStore.create(root, "Vault", "Can backlinks survive?", "exploratory") as store:
        service = InteroperabilityService(store)
        imported = service.import_obsidian(records)
        batch_id = imported["batch_id"]
    with ProjectStore(root) as reopened:
        service = InteroperabilityService(reopened)
        exported = service.export_obsidian(batch_id)
        exported_hashes = {item["relative_path"]: item["sha256"] for item in exported["files"]}
        expected_hashes = {
            record.relative_path: __import__("hashlib").sha256(record.content).hexdigest()
            for record in records
        }
        assert exported_hashes == expected_hashes
        assert len(exported["links"]) == 2
        undone = service.undo(batch_id)
        assert undone["soft_deleted_sources"] == 3
    with ProjectStore(root) as reopened:
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM sources WHERE deleted=0"
        ).fetchone()[0] == 0


class _ZoteroTransport:
    def __init__(self, status: int = 200, payload: object | None = None) -> None:
        self.status = status
        self.payload = [] if payload is None else payload
        self.calls: list[tuple[str, str, bytes | None]] = []

    def request(self, method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
        self.calls.append((method, path, body))
        return self.status, json.dumps(self.payload).encode("utf-8")


def test_zotero_local_bridge_read_only_default_forbidden_and_revoked_grant() -> None:
    transport = _ZoteroTransport(payload=[{"key": "A"}])
    bridge = ZoteroLocalBridge(transport)
    read = bridge.request("GET", "/api/users/0/items")
    assert read["read_only"] is True
    assert transport.calls == [("GET", "/api/users/0/items", None)]

    with pytest.raises(EvidenceError) as denied:
        bridge.request("POST", "/api/users/0/items", body=b"{}")
    assert denied.value.code == "NEEDS_APPROVAL"
    assert len(transport.calls) == 1

    revoked = ZoteroLocalBridge(_ZoteroTransport(status=403))
    with pytest.raises(EvidenceError) as forbidden:
        revoked.request("GET", "/api/users/0/items")
    assert forbidden.value.code == "AUTHORIZATION_REVOKED"
