"""Offline, bounded full-text import and revision-bound evidence spans.

Offsets are Python Unicode codepoint offsets within each extracted page/section.
No parser performs OCR or follows document hyperlinks.
"""

from __future__ import annotations

import importlib
import json
import posixpath
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, Protocol

from .errors import EvidenceError, require

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 1500
MAX_PAGES = 1500
MAX_SECTION_CHARS = 3_000_000
VERSION = "rw-fulltext-1"


@dataclass(frozen=True)
class TextPage:
    number: int
    text: str
    sha256: str
    status: str  # text, empty, needs_ocr
    rotation: int = 0
    label: str | None = None
    scan_evidence: str = "not_applicable"


@dataclass(frozen=True)
class FullText:
    media_type: str
    source_sha256: str
    pages: tuple[TextPage, ...]
    extraction_version: str = VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> FullText:
        data = json.loads(payload)
        require(data.get("extraction_version") == VERSION, "Unsupported extraction version")
        pages = tuple(TextPage(**page) for page in data["pages"])
        require(len(pages) <= MAX_PAGES, "Too many document pages", "RESOURCE_LIMIT")
        require(all(page.sha256 == _digest(page.text.encode("utf-8")) for page in pages),
                "Page hash mismatch", "INTEGRITY_ERROR")
        require(all(page.number == n for n, page in enumerate(pages, 1)), "Invalid page numbering")
        return cls(data["media_type"], data["source_sha256"], pages)


@dataclass(frozen=True)
class Highlight:
    source_sha256: str
    page_number: int
    page_sha256: str
    start: int
    end: int
    quote: str
    prefix: str
    suffix: str


class PdfPage(Protocol):
    rotation: int

    def extract_text(self, *args: Any, **kwargs: Any) -> str | None: ...


class PdfReaderLike(Protocol):
    pages: Any


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _page(number: int, text: str, *, status: str = "text", rotation: int = 0,
          label: str | None = None, scan_evidence: str = "not_applicable") -> TextPage:
    require(len(text) <= MAX_SECTION_CHARS, "Extracted section too large", "RESOURCE_LIMIT")
    require(rotation in (0, 90, 180, 270), "Invalid PDF page rotation")
    require(scan_evidence in {
        "not_applicable", "image_detected", "no_image_detected", "unknown_no_text",
    }, "Invalid scan evidence classification")
    return TextPage(number, text, _digest(text.encode("utf-8")), status, rotation, label,
                    scan_evidence)


def _pdf_scan_evidence(pdf_page: PdfPage) -> str:
    """Classify only explicit page-image evidence; never invent OCR results."""
    marker = getattr(pdf_page, "images", None)
    if marker is None:
        return "unknown_no_text"
    try:
        return "image_detected" if len(marker) > 0 else "no_image_detected"
    except (TypeError, AttributeError):
        return "unknown_no_text"


def _validated_zip(data: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            require(len(members) <= MAX_ENTRIES, "Too many archive members", "RESOURCE_LIMIT")
            names: set[str] = set()
            total = 0
            output: dict[str, bytes] = {}
            for item in members:
                name = item.filename
                path = PurePosixPath(name)
                require(name not in names, "Duplicate archive filename", "UNSAFE_DOCUMENT")
                names.add(name)
                require(not name.startswith(("/", "\\")) and "\\" not in name
                        and ".." not in path.parts and ":" not in name and "\x00" not in name,
                        "Unsafe archive path", "UNSAFE_DOCUMENT")
                require((item.external_attr >> 16) & 0o170000 != 0o120000,
                        "Archive symlink prohibited", "UNSAFE_DOCUMENT")
                require(not (item.flag_bits & 1), "Encrypted archive unsupported",
                        "UNSUPPORTED_FORMAT")
                total += item.file_size
                require(total <= MAX_UNCOMPRESSED_BYTES, "Archive expands beyond limit",
                        "RESOURCE_LIMIT")
                if item.is_dir():
                    continue
                with archive.open(item) as source:
                    value = source.read(item.file_size + 1)
                require(len(value) == item.file_size, "Archive entry size mismatch",
                        "UNSAFE_DOCUMENT")
                output[name] = value
            return output
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, ValueError) as exc:
        raise EvidenceError("INVALID_DOCUMENT", "Invalid or unsafe ZIP document",
                            "Use a valid unencrypted DOCX/EPUB file.") from exc


def _xml(data: bytes) -> ET.Element:
    require(len(data) <= MAX_UNCOMPRESSED_BYTES, "XML section too large", "RESOURCE_LIMIT")
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
            "Document entities prohibited", "UNSAFE_DOCUMENT")
    try:
        return ET.fromstring(data)  # noqa: S314 - bounded bytes; DTD/entities rejected above
    except ET.ParseError as exc:
        raise EvidenceError("INVALID_DOCUMENT", "Malformed document XML",
                            "Repair or re-export the document.") from exc


def _docx(data: bytes) -> tuple[TextPage, ...]:
    files = _validated_zip(data)
    require("word/document.xml" in files and "[Content_Types].xml" in files,
            "Missing DOCX document content", "INVALID_DOCUMENT")
    require(not any("vbaProject" in name or name.lower().endswith((".bin", ".exe", ".js"))
                    for name in files), "Executable content in DOCX", "UNSAFE_DOCUMENT")
    # External relationships are never resolved; reject references that would require fetching.
    for name, content in files.items():
        if name.endswith(".rels"):
            root = _xml(content)
            require(not any(el.attrib.get("TargetMode", "").lower() == "external"
                            for el in root.iter()), "External DOCX relationship", "UNSAFE_DOCUMENT")
    root = _xml(files["word/document.xml"])
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for element in root.iter():
        if element.tag == ns + "p":
            chunks = [node.text or "" for node in element.iter()
                      if node.tag in {ns + "t", ns + "instrText"} and node.tag != ns + "instrText"]
            if chunks:
                paragraphs.append("".join(chunks))
    require(bool(paragraphs), "DOCX contains no extractable text", "INVALID_DOCUMENT")
    return (_page(1, "\n".join(paragraphs)),)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.hidden += 1
        elif not self.hidden and tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def _epub(data: bytes) -> tuple[TextPage, ...]:
    files = _validated_zip(data)
    require(files.get("mimetype") == b"application/epub+zip", "Invalid EPUB mimetype")
    container = _xml(files.get("META-INF/container.xml", b""))
    rootfiles = [el.attrib["full-path"] for el in container.iter()
                 if el.tag.endswith("}rootfile") and "full-path" in el.attrib]
    require(len(rootfiles) == 1, "EPUB must contain one package")
    package_path = rootfiles[0]
    require(package_path in files, "Missing EPUB package")
    package = _xml(files[package_path])
    manifest: dict[str, str] = {}
    spine: list[str] = []
    for el in package.iter():
        if el.tag.endswith("}item"):
            if el.attrib.get("media-type") in {"application/xhtml+xml", "text/html"}:
                manifest[el.attrib.get("id", "")] = el.attrib.get("href", "")
        elif el.tag.endswith("}itemref"):
            spine.append(el.attrib.get("idref", ""))
    require(bool(spine), "EPUB reading order is empty")
    pages: list[TextPage] = []
    for item_id in spine:
        require(item_id in manifest, "Missing EPUB spine entry", "INVALID_DOCUMENT")
        href = manifest[item_id].split("#", 1)[0]
        path = posixpath.normpath(posixpath.join(posixpath.dirname(package_path), href))
        require(path in files and not path.startswith("../"), "Unsafe EPUB spine path",
                "UNSAFE_DOCUMENT")
        raw = files[path]
        require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
                "EPUB document entities prohibited", "UNSAFE_DOCUMENT")
        parser = _HTMLText()
        try:
            parser.feed(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError) as exc:
            raise EvidenceError("INVALID_DOCUMENT", "Invalid EPUB text encoding",
                                "Re-export EPUB as UTF-8.") from exc
        pages.append(_page(len(pages) + 1, "".join(parser.parts).strip(), label=path))
        require(len(pages) <= MAX_PAGES, "Too many EPUB sections", "RESOURCE_LIMIT")
    return tuple(pages)


def _pdf(data: bytes, reader_factory: Any = None) -> tuple[TextPage, ...]:
    require(data.startswith(b"%PDF-"), "Invalid PDF signature", "INVALID_DOCUMENT")
    if reader_factory is None:
        try:
            reader_factory = importlib.import_module("pypdf").PdfReader
        except ImportError as exc:
            raise EvidenceError("MISSING_DEPENDENCY", "PDF text parser is not installed",
                                "Install the optional pypdf package to extract PDF text.") from exc
    try:
        reader = reader_factory(BytesIO(data))
        require(not bool(getattr(reader, "is_encrypted", False)),
                "Encrypted PDF unsupported", "UNSUPPORTED_FORMAT")
        require(len(reader.pages) <= MAX_PAGES, "Too many PDF pages", "RESOURCE_LIMIT")
        pages: list[TextPage] = []
        for index, pdf_page in enumerate(reader.pages, 1):
            rotation = int(getattr(pdf_page, "rotation", 0) or 0) % 360
            extracted = pdf_page.extract_text() or ""
            require(isinstance(extracted, str), "PDF returned invalid page content")
            if extracted.strip():
                status, scan_evidence = "text", "not_applicable"
            else:
                scan_evidence = _pdf_scan_evidence(pdf_page)
                status = "empty" if scan_evidence == "no_image_detected" else "needs_ocr"
            pages.append(_page(index, extracted, status=status, rotation=rotation,
                               scan_evidence=scan_evidence))
        return tuple(pages)
    except EvidenceError:
        raise
    except Exception as exc:
        raise EvidenceError("INVALID_DOCUMENT", "PDF parser could not extract pages",
                            "Verify the PDF, or use an alternate text source.") from exc


def import_document(data: bytes, media_type: str, *, pdf_reader_factory: Any = None) -> FullText:
    """Read a source entirely offline. Inject a PDF reader factory for deterministic tests."""
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_INPUT_BYTES,
            "Invalid or oversized source bytes", "RESOURCE_LIMIT")
    if media_type == "application/pdf":
        pages = _pdf(data, pdf_reader_factory)
    elif media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        pages = _docx(data)
    elif media_type == "application/epub+zip":
        pages = _epub(data)
    elif media_type in {"text/plain", "text/markdown"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError as exc:
            raise EvidenceError("INVALID_DOCUMENT", "Expected UTF-8 text",
                                "Convert source to UTF-8.") from exc
        pages = (_page(1, text),)
    else:
        raise EvidenceError("UNSUPPORTED_FORMAT", "Unsupported source media type",
                            "Use PDF, DOCX, EPUB, or UTF-8 text.")
    return FullText(media_type, _digest(data), pages)


def verify_quote(document: FullText, page_number: int, start: int, end: int,
                 quote: str, *, source_sha256: str | None = None) -> dict[str, Any]:
    """Exact quote verification; normalization differences are diagnostic only."""
    require(type(page_number) is int and 1 <= page_number <= len(document.pages), "Invalid page")
    page = document.pages[page_number - 1]
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(page.text),
            "Invalid quote offsets")
    require(isinstance(quote, str) and 0 < len(quote) <= 20_000, "Invalid quote")
    candidate = page.text[start:end]
    match = candidate == quote
    current = source_sha256 is None or source_sha256 == document.source_sha256
    return {"verified": match and current, "exact_match": match, "source_current": current,
            "page_sha256": page.sha256, "source_sha256": document.source_sha256,
            "reason": "verified" if match and current else
            "source_revision_mismatch" if not current else
            "unicode_or_punctuation_difference" if unicodedata.normalize("NFC", candidate) ==
            unicodedata.normalize("NFC", quote) else "quote_mismatch"}


def create_highlight(document: FullText, page_number: int, start: int, end: int,
                     quote: str) -> Highlight:
    result = verify_quote(document, page_number, start, end, quote)
    require(result["verified"], "Highlight requires an exact source quote", "UNVERIFIED_QUOTE")
    page = document.pages[page_number - 1]
    return Highlight(document.source_sha256, page_number, page.sha256, start, end, quote,
                     page.text[max(0, start - 48):start], page.text[end:end + 48])


def relocate_highlight(highlight: Highlight, updated: FullText) -> dict[str, Any]:
    """Require human review unless a single exact, context-consistent span exists."""
    if (highlight.source_sha256 == updated.source_sha256 and
            1 <= highlight.page_number <= len(updated.pages)):
        page = updated.pages[highlight.page_number - 1]
        if (page.sha256 == highlight.page_sha256 and
                page.text[highlight.start:highlight.end] == highlight.quote):
            return {"status": "unchanged", "verified": True, "page": highlight.page_number,
                    "start": highlight.start, "end": highlight.end}
    matches: list[tuple[int, int, int]] = []
    for page in updated.pages:
        cursor = 0
        while True:
            found = page.text.find(highlight.quote, cursor)
            if found < 0:
                break
            matches.append((page.number, found, found + len(highlight.quote)))
            if len(matches) > 100:
                return {"status": "ambiguous", "verified": False, "matches": []}
            cursor = found + 1
    if len(matches) == 1:
        p, s, e = matches[0]
        page = updated.pages[p - 1]
        if (page.text[max(0, s - len(highlight.prefix)):s] == highlight.prefix and
                page.text[e:e + len(highlight.suffix)] == highlight.suffix):
            return {"status": "relocated", "verified": True, "page": p, "start": s, "end": e}
    return {"status": "ambiguous" if matches else "missing", "verified": False,
            "matches": matches[:10]}
