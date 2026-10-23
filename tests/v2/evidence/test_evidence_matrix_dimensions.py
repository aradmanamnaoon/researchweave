from __future__ import annotations

from pathlib import Path

from researchweave.evidence.extraction import ExtractedValue, ExtractionService, FieldDefinition
from researchweave.evidence.library import LibraryService
from researchweave.evidence.reviews import ReviewService
from researchweave.evidence.storage import ProjectStore


def test_matrix_preserves_population_timepoint_uncertainty_and_csv(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Matrix", "Question", "systematic_review") as store:
        reference = LibraryService(store).import_bibliography(
            b"@article{x,title={Trial},year={2024}}", "bibtex"
        )["references"][0]
        record = ReviewService(store).register("review", reference["id"], "study-1")
        ExtractionService(store).create_entry(
            record["record_id"],
            FieldDefinition("effect", "number", unit="points"),
            ExtractedValue(
                "effect",
                2.5,
                unit="points",
                original_text="Adjusted mean difference 2.5 points",
                population="Adults aged 18-65",
                timepoint="8 weeks",
                uncertainty="95% CI 1.0 to 4.0",
            ),
            "reviewer",
        )
        row = ExtractionService(store).matrix("review")[0]
        assert row["extracted"]["population"] == "Adults aged 18-65"
        assert row["extracted"]["timepoint"] == "8 weeks"
        assert row["extracted"]["uncertainty"] == "95% CI 1.0 to 4.0"
        csv_text = ExtractionService(store).matrix_csv("review")
        assert "population,timepoint,uncertainty" in csv_text
        assert "95% CI 1.0 to 4.0" in csv_text
