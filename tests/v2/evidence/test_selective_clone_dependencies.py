from __future__ import annotations

from pathlib import Path

from researchweave.evidence.citation_graph import CitationGraphService
from researchweave.evidence.collections import CollectionService
from researchweave.evidence.extraction import ExtractedValue, ExtractionService, FieldDefinition
from researchweave.evidence.highlights import HighlightService
from researchweave.evidence.library import LibraryService
from researchweave.evidence.portability import selective_clone
from researchweave.evidence.protocols import ProtocolService
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def test_clone_collection_review_and_protocol_closes_dependencies(tmp_path: Path) -> None:
    root = tmp_path / "source"
    with ProjectStore.create(root, "Clone", "Question", "systematic_review") as store:
        library = LibraryService(store)
        source = library.import_document(b"effect 2 points", "Source", "text/plain")
        anchor = library.add_anchor(source["source_id"], "2 points", 7, 15)["anchor_id"]
        note = library.add_note(source["source_id"], "Interpretation", "Initial note")
        library.revise_note(
            note["note_id"], "Interpretation", "Revised note", "Researcher", "Clarified wording"
        )
        highlight = HighlightService(store).create(source["source_id"], 1, 7, 15, "2 points")
        HighlightService(store).relocate(highlight["highlight_id"], source["source_id"])
        imported = library.import_bibliography(
            b"@article{x,title={Trial},author={Doe, Ada},year={2024}}\n"
            b"@article{y,title={Background},author={Roe, Bea},year={2023}}",
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        second_reference_id = imported["references"][1]["id"]
        CitationGraphService(store).link(
            reference_id,
            second_reference_id,
            anchor,
            "Researcher",
            "The source explicitly links these records.",
        )
        collection = CollectionService(store).create("Included")["collection_id"]
        CollectionService(store).add_members(collection, [reference_id])
        record = ReviewService(store).register("review", reference_id, "study")
        ExtractionService(store).create_entry(
            record["record_id"],
            FieldDefinition("effect", "number", unit="points"),
            ExtractedValue("effect", 2.0, "present", "points", "2 points"),
            "Reviewer",
            anchor_id=anchor,
        )
        protocol = ProtocolService(store).create(
            "Protocol", "Researcher", {"design": "systematic_review", "objective": "Test clone"}
        )
        receipt = selective_clone(
            store,
            tmp_path / "clone",
            source_ids=[],
            reference_ids=[],
            collection_ids=[collection],
            review_ids=["review"],
            protocol_ids=[protocol["protocol_id"]],
        )
        assert receipt["collections"] == 1
        assert receipt["review_records"] == 1
        assert receipt["protocol_versions"] == 1
        assert receipt["dependency_closed_source_ids"] == [source["source_id"]]
        assert receipt["dependency_closed_reference_ids"] == [reference_id]
        assert receipt["note_revisions"] == 2
        assert receipt["highlights"] == 1
    with ProjectStore(tmp_path / "clone") as clone:
        assert clone.audit()["ok"]
        assert clone.conn.execute("SELECT COUNT(*) FROM library_collections").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM collection_members").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM review_records").fetchone()[0] == 1
        assert clone.conn.execute("SELECT source_anchor FROM extractions").fetchone()[0] == anchor
        assert clone.conn.execute("SELECT COUNT(*) FROM protocols").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM note_revisions").fetchone()[0] == 2
        assert clone.conn.execute("SELECT COUNT(*) FROM evidence_highlights").fetchone()[0] == 1
        assert (
            clone.conn.execute("SELECT COUNT(*) FROM evidence_highlight_relocations").fetchone()[0]
            == 1
        )
        assert clone.get_object(source["sha256"]) == b"effect 2 points"


def test_clone_missing_review_is_rejected_without_destination(tmp_path: Path) -> None:
    root = tmp_path / "source"
    destination = tmp_path / "clone"
    with ProjectStore.create(root, "Clone", "Question", "systematic_review") as store:
        import pytest

        from researchweave.evidence.errors import EvidenceError

        with pytest.raises(EvidenceError) as error:
            selective_clone(
                store,
                destination,
                source_ids=[],
                reference_ids=[],
                review_ids=["missing-review"],
            )
        assert error.value.code == "NOT_FOUND"
    assert not destination.exists()
