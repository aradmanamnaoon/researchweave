"""Offline reference parsers, identifier hygiene and non-destructive deduplication."""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any

from .errors import EvidenceError, require
from .models import Reference, new_id, sha256

MAX_BIBLIOGRAPHY_BYTES = 4 * 1024 * 1024
MAX_REFERENCES = 5000
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
RIS_TOKEN = re.compile(r"^([A-Z][A-Z0-9])  - (.*)$")


def normalize_doi(value: str | None) -> str | None:
    """Normalize supplied DOI syntax only. Invalid identifiers remain unresolved."""
    if not value:
        return None
    text = value.strip()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.I).strip()
    if not DOI_PATTERN.fullmatch(text) or any(c.isspace() for c in text):
        return None
    return text.lower()


def normalize_title(title: str) -> str:
    decomposed = unicodedata.normalize("NFKD", title).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in decomposed).split())


def _parse_bibtex_fields(body: str) -> dict[str, str]:
    """Small deterministic BibTeX grammar including nested balanced brace values."""
    result: dict[str, str] = {}
    pos = 0
    while pos < len(body):
        pos = _skip_separators(body, pos)
        if pos >= len(body):
            break
        match = re.match(r"([a-zA-Z][\w-]*)\s*=\s*", body[pos:])
        if match is None:
            raise EvidenceError(
                "INVALID_INPUT",
                "Invalid BibTeX field syntax",
                "Correct field names, delimiters and braces.",
            )
        key = match.group(1).lower()
        pos += match.end()
        require(pos < len(body), "Missing BibTeX field value")
        if body[pos] in '{"':
            opening = body[pos]
            closing = "}" if opening == "{" else '"'
            pos += 1
            start = pos
            depth = 1
            escaped = False
            while pos < len(body) and depth:
                char = body[pos]
                if char == "\\":
                    escaped = not escaped
                else:
                    if not escaped and char == opening and opening == "{":
                        depth += 1
                    elif not escaped and char == closing:
                        depth -= 1
                    escaped = False
                pos += 1
            require(depth == 0, "Unclosed BibTeX field")
            value = body[start : pos - 1]
        else:
            start = pos
            while pos < len(body) and body[pos] != ",":
                pos += 1
            value = body[start:pos].strip()
        require(key not in result, "Duplicate BibTeX field")
        result[key] = value.strip()
    return result


def _skip_separators(text: str, position: int) -> int:
    while position < len(text) and (text[position].isspace() or text[position] == ","):
        position += 1
    return position


def parse_bibtex(text: str) -> list[Reference]:
    records: list[Reference] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("@", cursor)
        if start < 0:
            require(not text[cursor:].strip(), "Trailing invalid BibTeX text")
            break
        require(not text[cursor:start].strip(), "Invalid text before BibTeX entry")
        match = re.match(r"@([A-Za-z]+)\s*([({])", text[start:])
        require(match is not None, "Malformed BibTeX entry")
        if match is None:
            raise EvidenceError(
                "INVALID_INPUT", "Malformed BibTeX entry", "Correct the entry syntax."
            )
        kind = match.group(1).lower()
        opening = match.group(2)
        closing = "}" if opening == "{" else ")"
        cursor = start + match.end()
        depth = 1
        quote = False
        escaped = False
        while cursor < len(text) and depth:
            char = text[cursor]
            if char == "\\":
                escaped = not escaped
            else:
                if char == '"' and not escaped:
                    quote = not quote
                elif not quote and char == opening:
                    depth += 1
                elif not quote and char == closing:
                    depth -= 1
                escaped = False
            cursor += 1
        require(depth == 0, "Unclosed BibTeX entry")
        raw = text[start:cursor]
        inside = raw[match.end() : -1]
        comma = inside.find(",")
        require(comma > 0, "BibTeX entry missing citation key")
        citation_key = inside[:comma].strip()
        fields = _parse_bibtex_fields(inside[comma + 1 :])
        title = fields.get("title", "").strip("{}")
        authors = tuple(
            name.strip()
            for name in re.split(r"\s+and\s+", fields.get("author", ""), flags=re.I)
            if name.strip()
        )
        year_text = fields.get("year", "")
        year = int(year_text) if re.fullmatch(r"\d{4}", year_text) else None
        require(bool(citation_key) and len(citation_key) <= 255, "Invalid BibTeX citation key")
        records.append(
            Reference(
                new_id(),
                title,
                authors,
                year,
                normalize_doi(fields.get("doi")),
                kind,
                "bibtex",
                raw,
                provenance={"key": citation_key},
            )
        )
        require(len(records) <= MAX_REFERENCES, "Too many records", "RESOURCE_LIMIT")
    return records


def parse_ris(text: str) -> list[Reference]:
    records: list[Reference] = []
    fields: dict[str, list[str]] = {}
    original: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        matched = RIS_TOKEN.match(line)
        require(matched is not None, "Malformed RIS field")
        if matched is None:
            raise EvidenceError(
                "INVALID_INPUT", "Malformed RIS field", "Correct the RIS tag syntax."
            )
        tag, value = matched.groups()
        if tag == "TY":
            require(not fields, "RIS record missing ER terminator")
        else:
            require("TY" in fields, "RIS record missing TY header")
        fields.setdefault(tag, []).append(value)
        original.append(line)
        if tag == "ER":
            title = next(iter(fields.get("TI", fields.get("T1", [""]))), "")
            year = (fields.get("PY", fields.get("Y1", [""]))[0])[:4]
            records.append(
                Reference(
                    new_id(),
                    title,
                    tuple(fields.get("AU", fields.get("A1", []))),
                    int(year) if year.isdigit() and len(year) == 4 else None,
                    normalize_doi(next(iter(fields.get("DO", [])), "")),
                    fields["TY"][0],
                    "ris",
                    "\n".join(original) + "\n",
                )
            )
            fields, original = {}, []
            require(len(records) <= MAX_REFERENCES, "Too many records", "RESOURCE_LIMIT")
    require(not fields, "RIS record missing ER terminator")
    return records


def parse_csl_json(text: str) -> list[Reference]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]
    require(
        isinstance(data, list) and len(data) <= MAX_REFERENCES, "CSL JSON requires a bounded list"
    )
    records: list[Reference] = []
    for item in data:
        require(isinstance(item, dict), "CSL JSON entry is not an object")
        issued = item.get("issued", {})
        date_parts = issued.get("date-parts", [[]]) if isinstance(issued, dict) else [[]]
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        authors = item.get("author") or []
        require(isinstance(authors, list), "Invalid CSL author list")
        names: list[str] = []
        for author in authors:
            require(isinstance(author, dict), "Invalid CSL author")
            names.append(
                author.get("literal")
                or " ".join(s for s in (author.get("given"), author.get("family")) if s)
            )
        records.append(
            Reference(
                new_id(),
                str(item.get("title", "")),
                tuple(names),
                year if isinstance(year, int) else None,
                normalize_doi(item.get("DOI")),
                str(item.get("type", "article")),
                "csl-json",
                json.dumps(item, ensure_ascii=False),
            )
        )
    return records


def parse_endnote_xml(text: str) -> list[Reference]:
    require(
        "<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(),
        "XML entity declarations are prohibited",
        "UNTRUSTED_CONTENT",
    )
    root = ET.fromstring(text)  # noqa: S314 - DTD/entities rejected above; bounded input
    records: list[Reference] = []
    for record in root.findall(".//record"):
        title = " ".join(record.findtext(".//titles/title", "").split())
        authors = tuple(a.text.strip() for a in record.findall(".//authors/author") if a.text)
        year_text = record.findtext(".//dates/year", "")
        doi_text = record.findtext(".//electronic-resource-num", "")
        records.append(
            Reference(
                new_id(),
                title,
                authors,
                int(year_text) if re.fullmatch(r"\d{4}", year_text) else None,
                normalize_doi(doi_text),
                "article",
                "endnote-xml",
                ET.tostring(record, encoding="unicode"),
            )
        )
        require(len(records) <= MAX_REFERENCES, "Too many records", "RESOURCE_LIMIT")
    return records


def parse_bibliography(data: bytes, format_name: str) -> list[Reference]:
    require(len(data) <= MAX_BIBLIOGRAPHY_BYTES, "Bibliography exceeds limit", "RESOURCE_LIMIT")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise EvidenceError(
            "INVALID_INPUT", "Bibliography is not UTF-8", "Convert to UTF-8 and import again."
        ) from exc
    parsers = {
        "bibtex": parse_bibtex,
        "ris": parse_ris,
        "csl-json": parse_csl_json,
        "endnote-xml": parse_endnote_xml,
    }
    if format_name not in parsers:
        raise EvidenceError(
            "UNSUPPORTED_FORMAT",
            f"Unsupported format: {format_name}",
            "Export BibTeX, RIS, CSL JSON or EndNote XML.",
        )
    try:
        records = parsers[format_name](text)
    except (ValueError, TypeError, ET.ParseError, json.JSONDecodeError) as exc:
        raise EvidenceError(
            "INVALID_INPUT",
            "Invalid bibliography syntax",
            "Check encoding, required delimiters and field types.",
        ) from exc
    for record in records:
        require(
            record.title.strip() != "" and len(record.title) <= 4096,
            "A reference has no valid title",
        )
    return records


def duplicate_candidates(reference: Reference, others: Iterable[Reference]) -> list[dict[str, Any]]:
    """Suggest candidates, but never collapse distinct records automatically."""
    results: list[dict[str, Any]] = []
    for other in others:
        if other.id == reference.id:
            continue
        score = SequenceMatcher(
            None, normalize_title(reference.title), normalize_title(other.title)
        ).ratio()
        same_doi = bool(reference.doi and other.doi and reference.doi == other.doi)
        conflict_doi = bool(reference.doi and other.doi and reference.doi != other.doi)
        if same_doi or score >= 0.88:
            results.append(
                {
                    "id": other.id,
                    "title_similarity": round(score, 4),
                    "same_doi": same_doi,
                    "identifier_conflict": conflict_doi,
                    "needs_review": True,
                }
            )
    return sorted(
        results, key=lambda item: (not item["same_doi"], -item["title_similarity"], item["id"])
    )


def reference_from_row(row: Any) -> Reference:
    return Reference(
        id=row["id"],
        title=row["title"],
        authors=tuple(json.loads(row["authors_json"])),
        year=row["year"],
        doi=row["doi"],
        kind=row["kind"],
        source_format=row["format"],
        raw=row["raw"],
        metadata_status=row["status"],
        provenance=json.loads(row["metadata_json"]),
    )


def bibliography_digest(records: Iterable[Reference]) -> str:
    payload = "\n".join(sorted(f"{r.doi or ''}|{r.title}|{r.year}|{r.raw}" for r in records))
    return sha256(payload.encode("utf-8"))
