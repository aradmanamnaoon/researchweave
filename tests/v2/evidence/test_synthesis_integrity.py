from __future__ import annotations

from pathlib import Path

from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.synthesis import Finding, SynthesisService


def _finding(
    store: ProjectStore,
    text: bytes,
    quote: str,
    direction: str,
    *,
    record_id: str | None = None,
) -> str:
    library = LibraryService(store)
    source = library.import_document(text, f"Source {direction}", "text/plain")
    body = library.source_text(source["source_id"])
    start = body.index(quote)
    anchor = library.add_anchor(source["source_id"], quote, start, start + len(quote))
    return SynthesisService(store).add_finding(Finding(
        question="Effect?", population="Adults", outcome="Outcome",
        measure="mean difference", unit="points", timepoint="8 weeks",
        direction=direction, statement=f"Human-coded {direction} finding",
        anchor_id=anchor["anchor_id"], record_id=record_id,
    ))["id"]


def test_composer_flags_comparable_contradictions_without_inventing_certainty(
    tmp_path: Path,
) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Synthesis", "Question", "systematic_review"
    ) as store:
        positive = _finding(store, b"Outcome increased.", "increased", "positive")
        negative = _finding(store, b"Outcome decreased.", "decreased", "negative")
        service = SynthesisService(store)
        outline = service.compose("Synthesis", [{
            "heading": "Comparable evidence",
            "narrative": "Human-written cautious interpretation.",
            "finding_ids": [positive, negative],
        }])
        section = outline["sections"][0]
        assert outline["unresolved_contradictions"] == 1
        assert section["contradictions"][0]["directions"] == ["negative", "positive"]
        assert "UNRESOLVED_COMPARABLE_FINDING_CONTRADICTION" in section["warnings"]
        assert "EVIDENCE_STRENGTH_NOT_AUTOMATICALLY_ASSESSED" in section["warnings"]
        assert outline["scientific_conclusions_verified"] is False
        rendered = service.export_outline_markdown(outline["id"])
        assert "UNRESOLVED_COMPARABLE_FINDING_CONTRADICTION" in rendered


def test_composer_marks_unsupported_section_explicitly(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Synthesis", "Question", "systematic_review"
    ) as store:
        outline = SynthesisService(store).compose("Synthesis", [{
            "heading": "Interpretation", "narrative": "No finding cited.", "finding_ids": []
        }])
        assert outline["unsupported_sections"] == 1
        assert outline["sections"][0]["warnings"] == ["UNSUPPORTED_NARRATIVE_NO_FINDINGS"]


def test_contradiction_explorer_does_not_overstate_unidentified_findings(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Synthesis", "Question", "systematic_review"
    ) as store:
        _finding(store, b"Outcome increased.", "increased", "positive")
        _finding(store, b"Outcome decreased.", "decreased", "negative")
        group = SynthesisService(store).compare("Effect?")["groups"][0]
        assert group["classification"] == "identity_unresolved_directional_difference"
        assert group["identity_complete"] is False
