from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import pytest

from researchweave.evidence.artifact_formats import ArtifactFormatService
from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore
from researchweave.evidence.writing import WritingService


def _project(root: Path) -> tuple[ProjectStore, list[str]]:
    store = ProjectStore.create(root, "Artifacts", "Question", "observational")
    imported = LibraryService(store).import_bibliography(
        (
            "@article{a,title={Unicode شواهد},author={Doe, Ada and Roe, Bea},"
            "year={2024},doi={10.1000/a}}\n"
            "@article{b,title={No DOI},author={Consortium},year={2023}}"
        ).encode(),
        "bibtex",
    )
    return store, [row["id"] for row in imported["references"]]


def test_reference_exports_are_deterministic_and_do_not_invent_identifiers(
    tmp_path: Path,
) -> None:
    store, ids = _project(tmp_path / "project")
    with store:
        service = ArtifactFormatService(store)
        csl = service.export_references("csl-json", reference_ids=ids)
        csl_again = service.export_references("csl-json", reference_ids=ids)
        assert csl["sha256"] == csl_again["sha256"]
        parsed = json.loads(csl["bytes"])
        by_title = {item["title"]: item for item in parsed}
        assert by_title["Unicode شواهد"]["DOI"] == "10.1000/a"
        assert "DOI" not in by_title["No DOI"]
        assert csl["fabricated_identifiers"] == 0

        ris = service.export_references("ris", reference_ids=ids)
        assert b"DO  - 10.1000/a" in ris["bytes"]
        assert ris["bytes"].count(b"DO  - ") == 1

        bibtex = service.export_references("bibtex", reference_ids=ids)
        assert b"researchweave_id" in bibtex["bytes"]
        assert bibtex["warnings"]

        csv_export = service.export_references("csv", reference_ids=ids)
        rows = list(csv.DictReader(io.StringIO(csv_export["bytes"].decode("utf-8-sig"))))
        assert rows[0]["researchweave_id"] in ids
        assert {row["doi"] for row in rows} == {"10.1000/a", ""}


def test_manuscript_markdown_html_and_manifest_checksums(tmp_path: Path) -> None:
    store, _ = _project(tmp_path / "project")
    with store:
        writing = WritingService(store)
        writing.save_section("paper", "Abstract", "Evidence <unsafe> & literal.", {})
        writing.save_section("paper", "Methods", "Line one.\n\nLine two.", {})
        service = ArtifactFormatService(store)
        markdown = service.export_manuscript("paper", "markdown")
        html_export = service.export_manuscript("paper", "html")
        docx_export = service.export_manuscript("paper", "docx")
        assert b"# Abstract" in markdown["bytes"]
        assert b"&lt;unsafe&gt; &amp; literal." in html_export["bytes"]
        assert zipfile.is_zipfile(io.BytesIO(docx_export["bytes"]))
        try:
            pdf_export = service.export_manuscript("paper", "pdf")
        except EvidenceError as exc:
            assert exc.code == "DEPENDENCY_MISSING"
        else:
            assert pdf_export["bytes"].startswith(b"%PDF")
        manifest = service.manifest([markdown, html_export, docx_export])
        assert manifest["deterministic"] is True
        assert len(manifest["artifacts"]) == 3
        assert manifest["manifest_sha256"]


def test_artifact_format_rejects_unknown_format_without_writes(tmp_path: Path) -> None:
    store, _ = _project(tmp_path / "project")
    with store:
        before = store.info().revision
        with pytest.raises(EvidenceError) as unsupported:
            ArtifactFormatService(store).export_references("word")
        assert unsupported.value.code == "UNSUPPORTED_FORMAT"
        assert store.info().revision == before
