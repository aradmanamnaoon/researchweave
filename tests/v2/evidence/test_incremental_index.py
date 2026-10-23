from __future__ import annotations

from pathlib import Path

from researchweave.evidence.library import LibraryService
from researchweave.evidence.search_index import LocalIndex
from researchweave.evidence.storage import ProjectStore


def test_incremental_index_tracks_insert_update_delete_and_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(
        root, "Index", "Can local search stay current?", "exploratory"
    ) as store:
        library = LibraryService(store)
        first = library.import_document(b"alpha evidence", "Alpha source", "text/plain")
        index = LocalIndex(store)
        rebuilt = index.rebuild()
        assert rebuilt["sources"] == 1
        assert index.diagnostics()["consistent"]

        imported = library.import_bibliography(
            b"@article{x,title={Beta trial},author={Doe, Ada},year={2024}}", "bibtex"
        )
        sync = index.sync()
        assert sync == {
            "inserted": 1,
            "updated": 0,
            "deleted": 0,
            "unchanged": 1,
            "revision": store.info().revision,
        }
        assert index.search("Beta", kind="reference", auto_rebuild=False)["count"] == 1

        reference_id = imported["references"][0]["id"]
        store.mutate(
            "fixture.reference_title",
            {"reference_id": reference_id, "title": "Gamma trial"},
            lambda conn: conn.execute(
                "UPDATE reference SET title=? WHERE id=?", ("Gamma trial", reference_id)
            ),
            expected_revision=store.info().revision,
        )
        updated = index.sync()
        assert updated["updated"] == 1
        assert index.search("Gamma", kind="reference", auto_rebuild=False)["count"] == 1

        store.mutate(
            "fixture.source_delete",
            {"source_id": first["source_id"]},
            lambda conn: conn.execute(
                "UPDATE sources SET deleted=1 WHERE id=?", (first["source_id"],)
            ),
            expected_revision=store.info().revision,
        )
        deleted = index.sync()
        assert deleted["deleted"] == 1
        assert index.search("alpha", kind="source", auto_rebuild=False)["count"] == 0
        assert index.diagnostics()["consistent"]

    with ProjectStore(root) as reopened:
        index = LocalIndex(reopened)
        assert index.diagnostics()["consistent"]
        assert index.search("Gamma", auto_rebuild=False)["count"] == 1
        assert reopened.audit()["ok"]


def test_incremental_index_unchanged_sync_is_idempotent(tmp_path: Path) -> None:
    with ProjectStore.create(tmp_path / "project", "Index", "Question", "exploratory") as store:
        LibraryService(store).import_document(b"stable", "Stable", "text/plain")
        index = LocalIndex(store)
        index.rebuild()
        first = index.sync()
        second = index.sync()
        assert first["inserted"] == first["updated"] == first["deleted"] == 0
        assert second == first
        assert first["unchanged"] == 1
