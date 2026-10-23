from __future__ import annotations

from pathlib import Path

from researchweave.evidence.highlights import HighlightService
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore


def test_persistent_highlight_relocates_and_reopens(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Highlights", "Question", "exploratory") as store:
        library = LibraryService(store)
        first = library.import_document(b"before cited after", "First", "text/plain")
        second = library.import_document(
            b"prefix before cited after suffix", "Second", "text/plain"
        )
        service = HighlightService(store)
        created = service.create(first["source_id"], 1, 7, 12, "cited")
        relocated = service.relocate(created["highlight_id"], second["source_id"])
        assert relocated["status"] == "relocated"
        assert relocated["review_required"] is False
        assert relocated["target"]["start"] == 14
        history = service.history(created["highlight_id"])
        assert history["highlight"]["source_sha256"] == first["sha256"]
        assert history["relocations"][0]["target_source_id"] == second["source_id"]
    with ProjectStore(root) as reopened:
        history = HighlightService(reopened).history(created["highlight_id"])
        assert history["relocations"][0]["status"] == "relocated"
        assert reopened.audit()["ok"]


def test_ambiguous_and_missing_relocation_require_review(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Highlights", "Question", "exploratory"
    ) as store:
        library = LibraryService(store)
        original = library.import_document(b"target phrase", "Original", "text/plain")
        repeated = library.import_document(b"target and target", "Repeated", "text/plain")
        missing = library.import_document(b"nothing here", "Missing", "text/plain")
        service = HighlightService(store)
        highlight = service.create(original["source_id"], 1, 0, 6, "target")
        ambiguous = service.relocate(highlight["highlight_id"], repeated["source_id"])
        assert ambiguous["status"] == "ambiguous"
        assert ambiguous["candidate_count"] == 2 and ambiguous["review_required"]
        absent = service.relocate(highlight["highlight_id"], missing["source_id"])
        assert absent["status"] == "missing" and absent["review_required"]
        history = service.history(highlight["highlight_id"])
        assert history["review_required"] is True
