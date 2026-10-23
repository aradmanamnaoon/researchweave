from __future__ import annotations

from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.publishing import PublishingService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.writing import WritingService


def _manuscript(store: ProjectStore) -> None:
    imported = LibraryService(store).import_bibliography(
        b"@article{a,title={Known Study},author={Doe, Ada},year={2024},doi={10.1000/a}}\n"
        b"@article{b,title={Sparse Study}}",
        "bibtex",
    )
    first, second = [row["id"] for row in imported["references"]]
    WritingService(store).save_section(
        "paper",
        "Results",
        "Known evidence [@known] and sparse evidence [@sparse].",
        {"known": first, "sparse": second},
    )


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("apa-basic", "Doe, Ada (2024). Known Study. https://doi.org/10.1000/a"),
        ("harvard-basic", "Doe, Ada (2024) Known Study. https://doi.org/10.1000/a"),
        ("vancouver-basic", "[1] Doe, Ada. Known Study. 2024. https://doi.org/10.1000/a"),
    ],
)
def test_basic_bibliography_styles_are_deterministic_and_explicitly_limited(
    tmp_path: Path, style: str, expected: str
) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Bibliography", "Question", "observational"
    ) as store:
        _manuscript(store)
        rendered = PublishingService(store).bibliography("paper", style=style)
        assert expected in rendered["text"]
        assert "[authors unavailable]" in rendered["text"]
        assert "[year unavailable]" in rendered["text"]
        assert rendered["complete_csl_style"] is False
        assert "not a complete CSL implementation" in rendered["style_fidelity"]
        assert rendered == PublishingService(store).bibliography("paper", style=style)


def test_bibliography_unknown_style_is_rejected_without_writes(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Bibliography", "Question", "observational"
    ) as store:
        _manuscript(store)
        before = store.info().revision
        with pytest.raises(EvidenceError):
            PublishingService(store).bibliography("paper", style="invented-style")
        assert store.info().revision == before
