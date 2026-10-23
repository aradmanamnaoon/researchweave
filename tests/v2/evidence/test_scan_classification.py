"""Scanned-PDF classification reports image evidence without fabricating OCR."""

from io import BytesIO

from researchweave.evidence.fulltext import FullText, import_document


class Page:
    def __init__(self, text: str, images=None) -> None:
        self.rotation = 0
        if images is not None:
            self.images = images
        self._text = text

    def extract_text(self) -> str:
        return self._text


def _reader(pages):
    class Reader:
        def __init__(self, stream: BytesIO) -> None:
            assert stream.read(5) == b"%PDF-"
            self.pages = pages

    return Reader


def test_image_only_blank_and_unknown_pages_are_distinguished() -> None:
    original = b"%PDF-1.7 self-authored scan fixture"
    document = import_document(
        original,
        "application/pdf",
        pdf_reader_factory=_reader([
            Page("", [object()]),
            Page("", []),
            Page(""),
            Page("Readable text", []),
        ]),
    )
    assert [(page.status, page.scan_evidence) for page in document.pages] == [
        ("needs_ocr", "image_detected"),
        ("empty", "no_image_detected"),
        ("needs_ocr", "unknown_no_text"),
        ("text", "not_applicable"),
    ]
    assert all(page.text == "" for page in document.pages[:3])
    roundtrip = FullText.from_json(document.to_json())
    assert roundtrip == document
