"""Integration tests for actual stored provenance links and graph integrity."""

from __future__ import annotations

from pathlib import Path

from researchweave.evidence.library import LibraryService
from researchweave.evidence.provenance import export_provenance
from researchweave.evidence.storage import ProjectStore


def test_provenance_links_real_sources_notes_and_anchors(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Graph", "Evidence lineage?", "exploratory"
    ) as store:
        library = LibraryService(store)
        source_id = library.import_document(
            b"Traceable synthetic result", "Synthetic", "text/plain"
        )["source_id"]
        note_id = library.add_note(source_id, "Observation", "Researcher authored")["note_id"]
        anchor_id = library.add_anchor(source_id, "Traceable", 0, 9)["anchor_id"]
        graph = export_provenance(store)
        assert graph["valid"]
        assert {source_id, note_id, anchor_id}.issubset(graph["nodes"])
        assert {e["parent"] for e in graph["edges"]} == {source_id}
        assert store.audit()["ok"]
    with ProjectStore(tmp_path / "project") as reopened:
        assert export_provenance(reopened) == graph


def test_provenance_detects_orphan_and_cycles(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Graph", "Missing references?", "exploratory"
    ) as store:
        library = LibraryService(store)
        source_id = library.import_document(b"Synthetic source", "Original", "text/plain")[
            "source_id"
        ]
        note_id = library.add_note(source_id, "Note", "Human review")["note_id"]
        with store.transaction() as conn:
            conn.execute("INSERT INTO lineage VALUES (?, ?, ?)", (source_id, note_id, "circular"))
            conn.execute(
                "INSERT INTO lineage VALUES (?, ?, ?)", (note_id, "missing-resource", "broken")
            )
        result = export_provenance(store)
        assert not result["valid"]
        assert result["cycles"]
        assert any("missing-resource" in orphan for orphan in result["orphan_edges"])


def test_provenance_rejects_tampered_attachment_hash(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Graph", "Hash integrity?", "exploratory") as store:
        source = LibraryService(store).import_document(
            b"Synthetic attachment", "Synthetic", "text/plain"
        )
        digest = source["sha256"]
        store.object_path(digest).write_bytes(b"tampered attachment")
        graph = export_provenance(store)
        assert graph["valid"] is False
        assert graph["attachment_hashes_verified"] is False
        assert graph["nodes"][source["source_id"]]["attachment_integrity"] == "invalid"
        assert graph["attachment_issues"][0]["digest"] == digest
