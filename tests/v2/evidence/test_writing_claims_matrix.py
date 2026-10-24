from __future__ import annotations

import csv
import io
from pathlib import Path

from researchweave.evidence.claim_support import ClaimSupportService
from researchweave.evidence.extraction import (
    ExtractedValue,
    ExtractionService,
    FieldDefinition,
)
from researchweave.evidence.library import LibraryService
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.writing import WritingService


def test_manuscript_section_history_diff_and_stale_claim_detection(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Writing", "Question", "observational") as store:
        library = LibraryService(store)
        source = library.import_document(
            b"The observed synthetic outcome improved by 2 points.",
            "Synthetic source",
            "text/plain",
        )
        source_text = library.source_text(source["source_id"])
        quote = "improved by 2 points"
        start = source_text.index(quote)
        anchor = library.add_anchor(source["source_id"], quote, start, start + len(quote))
        writing = WritingService(store)
        body1 = "The outcome improved by 2 points."
        writing.save_section("paper", "Results", body1, {})
        claim = ClaimSupportService(store).add(
            "paper",
            "Results",
            body1,
            0,
            len(body1),
            "Researcher",
            "Supported by the exact source excerpt.",
            anchor_id=anchor["anchor_id"],
        )
        assert claim["classification"] == "evidence_backed"
        assert ClaimSupportService(store).check("paper")["issues"] == []

        body2 = "The outcome improved by approximately 2 points."
        writing.save_section("paper", "Results", body2, {})
        diff = writing.section_diff("paper", "Results", 1, 2)
        assert diff["history_overwritten"] is False
        assert any("approximately" in line for line in diff["diff"])
        checked = ClaimSupportService(store).check("paper")
        assert checked["issues"][0]["code"] == "CLAIM_STALE_AFTER_EDIT"
        assert checked["claim_coverage_complete"] is False
        restored = writing.restore_section(
            "paper", "Results", 1, "Researcher", "Return to the evidence-backed wording"
        )
        assert restored["section_revision"] == 3
        assert writing.sections("paper")[0]["body"] == body1
        assert [row["revision"] for row in writing.section_history("paper", "Results")] == [1, 2, 3]
    with ProjectStore(root) as reopened:
        history = WritingService(reopened).section_history("paper", "Results")
        assert [row["revision"] for row in history] == [1, 2, 3]
        assert history[-1]["body"] == body1
        assert reopened.audit()["ok"]


def test_manuscript_figures_are_versioned_cas_objects_and_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Writing", "Question", "observational") as store:
        writing = WritingService(store)
        first = writing.save_figure(
            "paper",
            "Figure 1",
            "Synthetic flow diagram",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            "image/svg+xml",
            "Researcher",
            "Initial figure",
        )
        revised = writing.save_figure(
            "paper",
            "Figure 1",
            "Revised synthetic flow diagram",
            b"<svg xmlns='http://www.w3.org/2000/svg'><title>Revised</title></svg>",
            "image/svg+xml",
            "Researcher",
            "Caption and source revised",
            figure_id=first["figure_id"],
        )
        assert revised["figure_revision"] == 2
        current = writing.figures("paper")
        assert current[0]["caption"] == "Revised synthetic flow diagram"
        assert store.get_object(current[0]["digest"]).startswith(b"<svg")
    with ProjectStore(root) as reopened:
        assert WritingService(reopened).figures("paper")[0]["revision"] == 2


def test_evidence_matrix_csv_preserves_missingness_units_and_anchor(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Matrix", "Question", "systematic_review"
    ) as store:
        library = LibraryService(store)
        source = library.import_document(b"effect 1.25 points", "Source", "text/plain")
        text = library.source_text(source["source_id"])
        start = text.index("1.25 points")
        anchor = library.add_anchor(
            source["source_id"], "1.25 points", start, start + len("1.25 points")
        )
        reference = library.import_bibliography(
            b"@article{x,title={Matrix study},author={Doe, Ada},year={2024}}", "bibtex"
        )
        record = ReviewService(store).register(
            "review-1", reference["references"][0]["id"], "study-1"
        )
        extraction = ExtractionService(store)
        extraction.create_entry(
            record["record_id"],
            FieldDefinition("effect", "number", unit="points"),
            ExtractedValue(
                "effect",
                1.25,
                "present",
                "points",
                "reported as 1.25 points",
            ),
            "Reviewer",
            anchor_id=anchor["anchor_id"],
        )
        extraction.create_entry(
            record["record_id"],
            FieldDefinition("variance", "number"),
            ExtractedValue("variance", None, "not_reported"),
            "Reviewer",
        )
        exported = extraction.matrix_csv("review-1")
        rows = list(csv.DictReader(io.StringIO(exported)))
        assert rows[0]["unit"] == "points"
        assert rows[0]["source_anchor"] == anchor["anchor_id"]
        assert rows[0]["original_text"] == "reported as 1.25 points"
        assert rows[1]["missingness"] == "not_reported"
        assert rows[1]["value"] == ""
