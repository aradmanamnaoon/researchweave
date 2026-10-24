from __future__ import annotations

import zipfile
from pathlib import Path

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.diagnostics import library_diagnostics
from researchweave.evidence.interoperability import InteroperabilityService
from researchweave.evidence.library import LibraryService
from researchweave.evidence.project_format import archive_project
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.workspace_integrity import scan_workspace


def test_diagnostics_distinguish_interop_raw_input_from_true_cas_orphan(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Diagnostics", "Question", "exploratory") as store:
        interop = InteroperabilityService(store)
        interop.import_zotero(b'[{"id":"z1","title":"Owned export","type":"article-journal"}]')
        preserved = store.conn.execute("SELECT raw_digest FROM interop_batches").fetchone()[0]
        orphan = store.put_object(b"unreferenced")
        report = library_diagnostics(store)
        assert preserved not in report["orphan_objects"]
        assert orphan in report["orphan_objects"]


def test_workspace_scanner_is_read_only_and_reports_projects_archives_dependencies(
    tmp_path: Path,
) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute(
        "project.create",
        {"title": "Workspace", "question": "Question", "design": "exploratory"},
        {},
    )
    assert created["status"] == "ok"
    project_id = created["data"]["project_id"]
    root = tmp_path / project_id
    with ProjectStore(root) as store:
        LibraryService(store).import_document(b"source", "Source", "text/plain")
        before_revision = store.info().revision
        exports = tmp_path / "exports"
        exports.mkdir()
        archive_project(store, exports / "valid.rwproj")
    corrupt = tmp_path / "exports" / "corrupt.rwproj"
    with zipfile.ZipFile(corrupt, "w") as archive:
        archive.writestr("not-a-project.txt", "broken")

    report = scan_workspace(tmp_path)
    assert report["read_only"] is True
    assert report["network_queries"] == 0
    assert report["project_index"]["project_ids"] == [project_id]
    assert {row["status"] for row in report["archives"]} == {"invalid", "verified"}
    assert {row["module"] for row in report["dependencies"]} == {
        "cryptography",
        "docx",
        "ebooklib",
        "pypdf",
    }
    assert report["repair_preview"]["automatic"]
    assert any(item["code"] == "INVALID_ARCHIVES" for item in report["issues"])
    with ProjectStore(root) as reopened:
        assert reopened.info().revision == before_revision

    via_facade = facade.execute("workspace.integrity", {}, {})
    assert via_facade["status"] == "ok"
    assert via_facade["data"]["read_only"] is True


def test_workspace_scanner_does_not_authenticate_encrypted_archive_without_password(
    tmp_path: Path,
) -> None:
    exports = tmp_path / "exports"
    exports.mkdir(parents=True)
    (exports / "private.rwproj.enc").write_bytes(b"opaque")
    report = scan_workspace(tmp_path)
    assert report["archives"] == [
        {
            "filename": "private.rwproj.enc",
            "kind": "encrypted-rwproj",
            "status": "authentication_required",
            "verified": False,
            "reason": "Encrypted archive requires its password for authenticated verification.",
        }
    ]
