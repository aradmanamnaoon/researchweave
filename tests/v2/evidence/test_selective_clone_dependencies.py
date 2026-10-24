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
        assert receipt["origin_mappings"] > 0
        cloned_review_id = receipt["destination_review_ids"]["review"]
        assert cloned_review_id != "review"
    with ProjectStore(tmp_path / "clone") as clone:
        assert clone.audit()["ok"]
        assert clone.conn.execute("SELECT COUNT(*) FROM library_collections").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM collection_members").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM review_records").fetchone()[0] == 1
        cloned_anchor = clone.conn.execute(
            "SELECT destination_id FROM clone_origins WHERE entity_kind='anchor' AND source_id=?",
            (anchor,),
        ).fetchone()[0]
        assert cloned_anchor != anchor
        assert (
            clone.conn.execute("SELECT source_anchor FROM extractions").fetchone()[0]
            == cloned_anchor
        )
        assert clone.conn.execute("SELECT COUNT(*) FROM protocols").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM note_revisions").fetchone()[0] == 2
        assert clone.conn.execute("SELECT COUNT(*) FROM evidence_highlights").fetchone()[0] == 1
        assert (
            clone.conn.execute("SELECT COUNT(*) FROM evidence_highlight_relocations").fetchone()[0]
            == 1
        )
        assert clone.get_object(source["sha256"]) == b"effect 2 points"
        origin_rows = clone.conn.execute(
            "SELECT entity_kind,destination_id,source_project_id,source_id,source_project_revision "
            "FROM clone_origins ORDER BY entity_kind,source_id"
        ).fetchall()
        assert len(origin_rows) == receipt["origin_mappings"]
        assert all(row["destination_id"] != row["source_id"] for row in origin_rows)
        assert all(row["source_project_id"] != clone.info().id for row in origin_rows)
        assert all(row["source_project_revision"] > 0 for row in origin_rows)

        cloned_source = clone.conn.execute("SELECT id,digest FROM sources").fetchone()
        assert cloned_source["id"] != source["source_id"]
        assert cloned_source["digest"] == source["sha256"]
        cloned_reference = clone.conn.execute(
            "SELECT id,title FROM reference WHERE title='Trial'"
        ).fetchone()
        assert cloned_reference["id"] != reference_id
        cloned_record = clone.conn.execute(
            "SELECT id,review_id,reference_id FROM review_records"
        ).fetchone()
        assert cloned_record["id"] != record["record_id"]
        assert cloned_record["review_id"] == cloned_review_id
        assert cloned_record["reference_id"] == cloned_reference["id"]

    with ProjectStore(tmp_path / "clone") as reopened:
        assert reopened.audit()["ok"]
        assert (
            reopened.conn.execute("SELECT COUNT(*) FROM clone_origins").fetchone()[0]
            == receipt["origin_mappings"]
        )
        assert (
            reopened.conn.execute("SELECT review_id FROM review_records").fetchone()[0]
            == cloned_review_id
        )


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
