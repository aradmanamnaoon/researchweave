from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore


def test_note_revision_tombstone_history_and_export_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Notebook", "Question", "exploratory") as store:
        library = LibraryService(store)
        source = library.import_document(b"source", "Source", "text/plain")
        note = library.add_note(
            source["source_id"], "Interpretation", "Initial human interpretation."
        )
        revised = library.revise_note(
            note["note_id"],
            "Interpretation",
            "Revised human interpretation.",
            "Researcher",
            "Clarified wording after rereading source.",
        )
        assert revised["note_revision"] == 2
        history = library.note_history(note["note_id"])
        assert [row["revision"] for row in history["revisions"]] == [1, 2]
        assert history["deleted"] is False
        assert "Revised human interpretation." in library.export_notebook()
        deleted = library.delete_note(
            note["note_id"], "Researcher", "Superseded by structured extraction."
        )
        assert deleted["physical_row_preserved"] is True
        assert "Revised human interpretation." not in library.export_notebook()
        with pytest.raises(EvidenceError) as conflict:
            library.revise_note(
                note["note_id"], "Interpretation", "Another edit", "Researcher", "Late edit"
            )
        assert conflict.value.code == "CONFLICT"
    with ProjectStore(root) as reopened:
        library = LibraryService(reopened)
        history = library.note_history(note["note_id"])
        assert history["deleted"] is True
        assert history["tombstone"]["reason"] == "Superseded by structured extraction."
        assert len(history["revisions"]) == 2
        assert (
            reopened.conn.execute(
                "SELECT COUNT(*) FROM notes WHERE id=?", (note["note_id"],)
            ).fetchone()[0]
            == 1
        )
        assert reopened.audit()["ok"]


def test_legacy_note_is_adopted_without_losing_original_timestamp(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Notebook", "Question", "exploratory") as store:
        source = LibraryService(store).import_document(b"source", "Source", "text/plain")
        note_id = "legacy-note"
        original_time = "2024-01-01T00:00:00+00:00"
        store.mutate(
            "fixture.legacy_note",
            {"note_id": note_id},
            lambda conn: conn.execute(
                "INSERT INTO notes VALUES (?,?,?,?,?)",
                (note_id, source["source_id"], "Legacy", "Original", original_time),
            ),
            expected_revision=None,
        )
        library = LibraryService(store)
        library.revise_note(note_id, "Legacy", "Updated", "Researcher", "Adopt old note.")
        history = library.note_history(note_id)
        assert history["revisions"][0]["recorded_at"] == original_time
        assert history["revisions"][0]["body"] == "Original"
