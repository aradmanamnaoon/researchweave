from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.portability import (
    export_review_packet,
    merge_review_packet,
    preview_review_packet_merge,
)
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def _source_packet(root: Path, packet: Path) -> None:
    with ProjectStore.create(root, "Source", "Which study?", "systematic_review") as store:
        reference = LibraryService(store).import_bibliography(
            (
                b"@article{x,title={Incoming title},author={Doe, Ada},"
                b"year={2024},doi={10.1000/shared}}"
            ),
            "bibtex",
        )["references"][0]
        record = ReviewService(store).register("review-a", reference["id"], "study-a")
        ReviewService(store).vote(
            "review-a", record["record_id"], "reviewer-a", "title_abstract", "include"
        )
        export_review_packet(store, packet, "review-a", confirm_private_export=True)


def test_review_packet_preview_merge_conflict_receipt_and_reopen(tmp_path: Path) -> None:
    packet = tmp_path / "review.rw-review.zip"
    _source_packet(tmp_path / "source", packet)
    target_root = tmp_path / "target"
    with ProjectStore.create(
        target_root, "Target", "Which study?", "systematic_review"
    ) as store:
        existing = LibraryService(store).import_bibliography(
            (
                b"@article{x,title={Local corrected title},author={Doe, Ada},"
                b"year={2024},doi={10.1000/shared}}"
            ),
            "bibtex",
        )["references"][0]
        before = store.info().revision
        preview = preview_review_packet_merge(store, packet)
        assert preview["writes_performed"] is False
        assert preview["potential_conflicts"][0]["doi"] == "10.1000/shared"
        assert store.info().revision == before
        merged = merge_review_packet(
            store,
            packet,
            destination_review_id="imported-review",
            actor="Researcher",
        )
        assert merged["silent_overwrite"] is False
        assert merged["conflict_count"] >= 1
        assert merged["counts"]["records_inserted"] == 1
        assert LibraryService(store).get_reference(existing["id"]).title == "Local corrected title"
        assert store.conn.execute(
            "SELECT COUNT(*) FROM review_packet_origins"
        ).fetchone()[0] >= 2
    with ProjectStore(target_root) as reopened:
        record = reopened.conn.execute(
            "SELECT * FROM review_records WHERE review_id='imported-review'"
        ).fetchone()
        assert record is not None
        assert record["reference_id"] == existing["id"]
        import_row = reopened.conn.execute(
            "SELECT conflicts_json FROM review_packet_imports"
        ).fetchone()
        assert import_row is not None
        assert json.loads(import_row["conflicts_json"])
        assert reopened.audit()["ok"]


def test_review_packet_tamper_is_rejected_before_merge(tmp_path: Path) -> None:
    packet = tmp_path / "review.rw-review.zip"
    _source_packet(tmp_path / "source", packet)
    rewritten = tmp_path / "tampered.rw-review.zip"
    with zipfile.ZipFile(packet) as source, zipfile.ZipFile(rewritten, "w") as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename == "review_records.json":
                data += b" "
            target.writestr(member, data)
    target_root = tmp_path / "target"
    with ProjectStore.create(target_root, "Target", "Question", "systematic_review") as store:
        before = store.info().revision
        with pytest.raises(EvidenceError) as integrity:
            merge_review_packet(store, rewritten, actor="Researcher")
        assert integrity.value.code == "INTEGRITY_FAILURE"
        assert store.info().revision == before
        assert store.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='review_packet_imports'"
        ).fetchone() is None
