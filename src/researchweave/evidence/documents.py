"""Bounded offline text extraction and verifiable quote anchoring."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from .errors import EvidenceError, require
from .models import EvidenceAnchor, new_id, sha256

MAX_TEXT_BYTES = 16 * 1024 * 1024


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def extract_text(data: bytes, media_type: str) -> tuple[str, dict[str, str]]:
    require(len(data) <= MAX_TEXT_BYTES, "Text exceeds extraction limit", "RESOURCE_LIMIT")
    if media_type not in {"text/plain", "text/markdown", "text/html"}:
        raise EvidenceError("UNSUPPORTED_FORMAT", "Text extraction adapter unavailable",
                            "Use UTF-8 text or add a licensed PDF/DOCX adapter.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise EvidenceError("INVALID_INPUT", "Document text is not UTF-8",
                            "Convert the document to UTF-8.") from exc
    if media_type == "text/html":
        parser = _TextExtractor()
        parser.feed(text)
        text = "".join(parser.parts)
    return text, {"body_sha256": sha256(text.encode("utf-8")),
                  "extraction_version": "rw-text-1", "source_type": media_type}


def check_quote(body: str, quote: str, start: int, end: int) -> bool:
    """Verify exact codepoint offsets; never fuzzy-confirm a scientific quotation."""
    require(isinstance(start, int) and isinstance(end, int) and
            0 <= start <= end <= len(body), "Invalid quote offsets")
    require(bool(quote) and len(quote) <= 20_000, "Invalid quoted text")
    return body[start:end] == quote


def find_quote_locations(body: str, quote: str, *, limit: int = 20) -> list[tuple[int, int]]:
    require(bool(quote) and len(quote) <= 20_000, "Invalid quote")
    locations: list[tuple[int, int]] = []
    for match in re.finditer(re.escape(quote), body):
        locations.append((match.start(), match.end()))
        if len(locations) >= limit:
            break
    return locations


def make_anchor(source_id: str, body: str, quote: str, start: int, end: int,
                page: int | None = None) -> EvidenceAnchor:
    require(page is None or isinstance(page, int) and page > 0,
            "Page must be a positive integer")
    return EvidenceAnchor(new_id(), source_id, quote, start, end, page,
                          sha256(body.encode("utf-8")), check_quote(body, quote, start, end))


def relocate_anchor(anchor: EvidenceAnchor, changed_body: str) -> dict[str, object]:
    matches = find_quote_locations(changed_body, anchor.quote, limit=3)
    if len(matches) == 1:
        return {"status": "unique-exact-match", "start": matches[0][0],
                "end": matches[0][1], "verified": True}
    if not matches:
        return {"status": "unresolved", "verified": False}
    return {"status": "ambiguous", "matches": matches, "verified": False}
