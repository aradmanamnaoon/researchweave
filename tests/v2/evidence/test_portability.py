from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.extraction import ExtractedValue, ExtractionService, FieldDefinition
from researchweave.evidence.library import LibraryService
from researchweave.evidence.portability import (
    export_research_artifacts,
    export_review_packet,
    merge_review_packet,
    preview_review_packet_merge,
    selective_clone,
)
from researchweave.evidence.protocols import ProtocolService
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def _fixture(root: Path) -> tuple[str, str, str]:
    with ProjectStore.create(
        root, "Portability", "Can evidence travel?", "systematic_review"
    ) as store:
        library = LibraryService(store)
        source = library.import_document(b"portable evidence", "Source", "text/plain")
        library.add_note(source["source_id"], "Interpretation", "Human interpretation.")
        imported = library.import_bibliography(
            b"@article{x,title={Portable study},author={Doe, Ada},year={2024}}", "bibtex"
        )
        reference_id = imported["references"][0]["id"]
        review = ReviewService(store)
        record = review.register("review-1", reference_id, "study-1")
        return store.info().id, source["source_id"], record["record_id"]


def test_artifact_bundle_has_readable_checksummed_manifest(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _fixture(root)
    destination = tmp_path / "export.rw-artifacts.zip"
    with ProjectStore(root) as store:
        receipt = export_research_artifacts(store, destination)
    assert receipt["files"] >= 4
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_attachment_bytes_included"] is False
        assert "references.csv" in archive.namelist()
        for item in manifest["files"]:
            assert len(archive.read(item["path"])) == item["bytes"]


def test_private_review_packet_requires_confirmation_and_excludes_sources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _fixture(root)
    destination = tmp_path / "review.rw-review.zip"
    with ProjectStore(root) as store:
        with pytest.raises(EvidenceError) as denied:
            export_review_packet(store, destination, "review-1")
        assert denied.value.code == "NEEDS_APPROVAL"
        assert not destination.exists()
        receipt = export_review_packet(store, destination, "review-1", confirm_private_export=True)
    assert receipt["privacy"] == "private"
    with zipfile.ZipFile(destination) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["source_full_text_included"] is False
        assert not any(name.startswith("objects/") for name in archive.namelist())


def test_review_packet_redacts_structured_secrets_and_participant_fields(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _, _, record_id = _fixture(root)
    destination = tmp_path / "redacted.rw-review.zip"
    with ProjectStore(root) as store:
        ProtocolService(store).create(
            "Protocol",
            "Researcher",
            {
                "design": "systematic_review",
                "objective": "Test safe review packets",
                "api_key": "super-secret-token",
                "contact": {"email": "participant@example.org"},
            },
        )
        ExtractionService(store).create_entry(
            record_id,
            FieldDefinition("participant_id", "string"),
            ExtractedValue("participant_id", "subject-0042"),
            "Reviewer",
        )
        receipt = export_review_packet(
            store,
            destination,
            "review-1",
            confirm_private_export=True,
            redact_fields=["participant_id"],
        )
    assert receipt["redaction_count"] >= 3
    with zipfile.ZipFile(destination) as archive:
        protocols = json.loads(archive.read("protocols.json"))
        protocol_body = json.loads(protocols[0]["body_json"])
        assert protocol_body["api_key"] == "[REDACTED]"
        assert protocol_body["contact"]["email"] == "[REDACTED]"
        extractions = json.loads(archive.read("extractions.json"))
        assert json.loads(extractions[0]["value_json"]) == "[REDACTED]"
        redactions = json.loads(archive.read("redaction_report.json"))
        assert redactions["redaction_count"] == receipt["redaction_count"]
        assert "participant_id" in redactions["requested_fields"]
        combined = b"".join(
            archive.read(name) for name in archive.namelist() if name.endswith(".json")
        )
        assert b"super-secret-token" not in combined
        assert b"participant@example.org" not in combined
        assert b"subject-0042" not in combined


def test_review_packet_merge_reports_conflicts_without_overwrite_and_survives_reopen(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    packet = tmp_path / "collaboration.rw-review.zip"
    with ProjectStore.create(
        source_root, "Source", "Can packets merge safely?", "systematic_review"
    ) as source:
        library = LibraryService(source)
        imported = library.import_bibliography(
            b"@article{x,title={Incoming Title},author={Doe, Ada},year={2024},doi={10.1000/merge}}",
            "bibtex",
        )
        reference_id = imported["references"][0]["id"]
        review = ReviewService(source)
        record_id = review.register("review-merge", reference_id, None)["record_id"]
        review.vote("review-merge", record_id, "Reviewer A", "title_abstract", "include")
        export_review_packet(
            source,
            packet,
            "review-merge",
            confirm_private_export=True,
        )

    destination_root = tmp_path / "destination"
    with ProjectStore.create(
        destination_root, "Destination", "Can packets merge safely?", "systematic_review"
    ) as destination:
        library = LibraryService(destination)
        imported = library.import_bibliography(
            b"@article{x,title={Local Confirmed Title},author={Doe, Ada},year={2023},"
            b"doi={10.1000/merge}}",
            "bibtex",
        )
        local_reference_id = imported["references"][0]["id"]
        local_record_id = ReviewService(destination).register(
            "review-merge", local_reference_id, None
        )["record_id"]
        ReviewService(destination).vote(
            "review-merge",
            local_record_id,
            "Reviewer A",
            "title_abstract",
            "exclude",
            "Local exclusion rationale",
        )
        preview = preview_review_packet_merge(destination, packet)
        assert preview["writes_performed"] is False
        assert preview["potential_conflicts"]
        revision_before = destination.info().revision
        merged = merge_review_packet(destination, packet, actor="Collaborator")
        assert merged["conflict_count"] >= 2
        assert merged["silent_overwrite"] is False
        assert destination.info().revision == revision_before + 1
        local_reference = destination.conn.execute(
            "SELECT title,year FROM reference WHERE id=?", (local_reference_id,)
        ).fetchone()
        assert tuple(local_reference) == ("Local Confirmed Title", 2023)
        local_vote = destination.conn.execute(
            "SELECT decision,reason FROM votes WHERE review_id=? AND record_id=? AND reviewer=?",
            ("review-merge", local_record_id, "Reviewer A"),
        ).fetchone()
        assert tuple(local_vote) == ("exclude", "Local exclusion rationale")
        persisted = destination.conn.execute(
            "SELECT conflicts_json FROM review_packet_imports WHERE packet_sha256=?",
            (merged["packet_sha256"],),
        ).fetchone()
        assert len(json.loads(persisted["conflicts_json"])) == merged["conflict_count"]
        revision_after_merge = destination.info().revision
        repeated = merge_review_packet(destination, packet, actor="Collaborator")
        assert repeated["already_merged"] is True
        assert repeated["conflicts"] == merged["conflicts"]
        assert destination.info().revision == revision_after_merge

    with ProjectStore(destination_root) as reopened:
        assert reopened.audit()["ok"]
        assert (
            reopened.conn.execute("SELECT COUNT(*) FROM review_packet_imports").fetchone()[0] == 1
        )
        assert reopened.conn.execute("SELECT COUNT(*) FROM reference").fetchone()[0] == 1
        assert reopened.conn.execute("SELECT COUNT(*) FROM review_records").fetchone()[0] == 1


def test_review_packet_merge_rejects_tampered_member(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _fixture(root)
    packet = tmp_path / "packet.rw-review.zip"
    with ProjectStore(root) as store:
        export_review_packet(store, packet, "review-1", confirm_private_export=True)

    tampered = tmp_path / "tampered.rw-review.zip"
    with zipfile.ZipFile(packet) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "references.json":
                data += b" "
            target.writestr(info, data)
    destination = tmp_path / "destination"
    with ProjectStore.create(
        destination, "Destination", "Can packets merge safely?", "systematic_review"
    ) as store:
        before = store.info().revision
        with pytest.raises(EvidenceError) as error:
            merge_review_packet(store, tampered, actor="Collaborator")
        assert error.value.code == "INTEGRITY_FAILURE"
        assert store.info().revision == before
        assert (
            store.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_packet_imports'"
            ).fetchone()
            is None
        )


def test_selective_clone_preserves_dependencies_with_new_project_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    source_project_id, source_id, _ = _fixture(root)
    with ProjectStore(root) as store:
        reference_id = store.conn.execute("SELECT id FROM reference").fetchone()[0]
        receipt = selective_clone(
            store,
            tmp_path / "clone",
            source_ids=[source_id],
            reference_ids=[reference_id],
        )
    assert receipt["source_project_id"] == source_project_id
    assert receipt["destination_project_id"] != source_project_id
    with ProjectStore(tmp_path / "clone") as clone:
        assert clone.audit()["ok"]
        assert clone.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM reference").fetchone()[0] == 1
        assert clone.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
        digest = clone.conn.execute("SELECT digest FROM sources").fetchone()[0]
        assert clone.get_object(digest) == b"portable evidence"


def test_selective_clone_invalid_selection_leaves_no_destination(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _fixture(root)
    destination = tmp_path / "clone"
    with ProjectStore(root) as store:
        with pytest.raises(EvidenceError):
            selective_clone(
                store,
                destination,
                source_ids=["missing"],
                reference_ids=[],
            )
    assert not destination.exists()
