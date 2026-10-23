"""Deterministic portable research artifact renderers and fidelity receipts."""

from __future__ import annotations

import csv
import html
import io
import json
import re
from typing import Any

from .errors import require
from .library import LibraryService
from .models import canonical_json, sha256
from .storage import ProjectStore
from .writing import WritingService

_RIS_KIND = {
    "article-journal": "JOUR",
    "journal-article": "JOUR",
    "book": "BOOK",
    "chapter": "CHAP",
    "conference-paper": "CPAPER",
    "thesis": "THES",
}


def _bibtex_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _citation_key(index: int, title: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", title)[:24] or "reference"
    return f"rw{index:04d}{token}"


class ArtifactFormatService:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self.library = LibraryService(store)
        self.writing = WritingService(store)

    def _references(self, reference_ids: list[str] | None = None) -> list[Any]:
        if reference_ids is None:
            rows = self.store.conn.execute("SELECT id FROM reference ORDER BY id").fetchall()
            ids = [str(row["id"]) for row in rows]
        else:
            require(
                len(reference_ids) <= 5000 and len(reference_ids) == len(set(reference_ids)),
                "Reference export selection is invalid",
            )
            ids = sorted(reference_ids)
        return [self.library.get_reference(reference_id) for reference_id in ids]

    def export_references(
        self,
        format_name: str,
        *,
        reference_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        require(
            format_name in {"csl-json", "ris", "bibtex", "csv"},
            "Unsupported reference export format",
            "UNSUPPORTED_FORMAT",
        )
        references = self._references(reference_ids)
        warnings: list[str] = []
        if format_name == "csl-json":
            payload = []
            for reference in references:
                item: dict[str, Any] = {
                    "id": reference.id,
                    "type": reference.kind or "article-journal",
                    "title": reference.title,
                    "author": [{"literal": author} for author in reference.authors],
                }
                if reference.year is not None:
                    item["issued"] = {"date-parts": [[reference.year]]}
                if reference.doi:
                    item["DOI"] = reference.doi
                payload.append(item)
            data = (
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
        elif format_name == "ris":
            lines: list[str] = []
            for reference in references:
                lines.append(f"TY  - {_RIS_KIND.get(reference.kind, 'GEN')}")
                lines.append(f"ID  - {reference.id}")
                lines.append(f"TI  - {reference.title}")
                for author in reference.authors:
                    lines.append(f"AU  - {author}")
                if reference.year is not None:
                    lines.append(f"PY  - {reference.year}")
                if reference.doi:
                    lines.append(f"DO  - {reference.doi}")
                lines.extend(["ER  - ", ""])
            data = "\n".join(lines).encode()
        elif format_name == "bibtex":
            blocks = []
            for index, reference in enumerate(references, 1):
                key = _citation_key(index, reference.title)
                fields = [f"title = {{{_bibtex_escape(reference.title)}}}"]
                if reference.authors:
                    fields.append(
                        "author = {"
                        + " and ".join(_bibtex_escape(author) for author in reference.authors)
                        + "}"
                    )
                if reference.year is not None:
                    fields.append(f"year = {{{reference.year}}}")
                if reference.doi:
                    fields.append(f"doi = {{{_bibtex_escape(reference.doi)}}}")
                fields.append(f"researchweave_id = {{{reference.id}}}")
                blocks.append(
                    "@article{" + key + ",\n  " + ",\n  ".join(fields) + "\n}"
                )
            data = ("\n\n".join(blocks) + ("\n" if blocks else "")).encode()
            warnings.append(
                "BibTeX item type is conservatively rendered as @article; "
                "original ResearchWeave kind remains available in project metadata."
            )
        else:
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "researchweave_id",
                    "title",
                    "authors",
                    "year",
                    "doi",
                    "kind",
                    "metadata_status",
                ],
            )
            writer.writeheader()
            for reference in references:
                writer.writerow(
                    {
                        "researchweave_id": reference.id,
                        "title": reference.title,
                        "authors": "; ".join(reference.authors),
                        "year": reference.year if reference.year is not None else "",
                        "doi": reference.doi or "",
                        "kind": reference.kind,
                        "metadata_status": reference.metadata_status,
                    }
                )
            data = stream.getvalue().encode("utf-8-sig")
        return {
            "format": format_name,
            "bytes": data,
            "sha256": sha256(data),
            "count": len(references),
            "warnings": warnings,
            "fabricated_identifiers": 0,
            "scientific_claims_verified": False,
        }

    def export_manuscript(self, manuscript_id: str, format_name: str) -> dict[str, Any]:
        require(
            format_name in {"markdown", "html"},
            "Unsupported manuscript export format",
            "UNSUPPORTED_FORMAT",
        )
        sections = self.writing.sections(manuscript_id)
        require(bool(sections), "Manuscript not found", "NOT_FOUND")
        markdown = self.writing.render_markdown(manuscript_id)
        if format_name == "markdown":
            data = markdown.encode()
            fidelity = "native_markdown"
        else:
            rendered: list[str] = ["<!doctype html>", '<html lang="en">', "<body>"]
            for section in sections:
                rendered.append(f"<h1>{html.escape(str(section['section']))}</h1>")
                for paragraph in str(section["body"]).split("\n\n"):
                    if paragraph.strip():
                        rendered.append(f"<p>{html.escape(paragraph)}</p>")
            rendered.extend(["</body>", "</html>", ""])
            data = "\n".join(rendered).encode()
            fidelity = "plain_text_structure_preserved_markup_not_interpreted"
        return {
            "format": format_name,
            "bytes": data,
            "sha256": sha256(data),
            "sections": len(sections),
            "fidelity": fidelity,
            "citation_mapping_preserved_in_project": True,
            "submission_performed": False,
        }

    def manifest(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        require(0 < len(artifacts) <= 100, "Artifact manifest count outside bounds")
        items = []
        for artifact in artifacts:
            require(
                isinstance(artifact.get("format"), str)
                and isinstance(artifact.get("sha256"), str),
                "Artifact receipt is incomplete",
            )
            items.append(
                {
                    "format": artifact["format"],
                    "sha256": artifact["sha256"],
                    "bytes": len(artifact.get("bytes", b"")),
                }
            )
        encoded = canonical_json(items).encode()
        return {
            "artifacts": items,
            "manifest_sha256": sha256(encoded),
            "deterministic": True,
        }
