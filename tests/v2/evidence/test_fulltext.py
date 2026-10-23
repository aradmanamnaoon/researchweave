"""Synthetic offline coverage for full-text import and exact evidence spans."""

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.fulltext import (
    FullText,
    create_highlight,
    import_document,
    relocate_highlight,
    verify_quote,
)
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore


def archive(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for name, content in entries.items():
            zipped.writestr(name, content)
    return output.getvalue()


def docx(*, external: bool = False) -> bytes:
    entries = {
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            '<w:r><w:t>Evidence</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>\u0645\u062a\u0646</w:t></w:r></w:p></w:body></w:document>'
        ).encode(),
    }
    if external:
        entries["word/_rels/document.xml.rels"] = (
            b'<Relationships><Relationship Target="https://example.com/" '
            b'TargetMode="External"/></Relationships>'
        )
    return archive(entries)


def epub() -> bytes:
    return archive({
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": (
            b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b'<rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>'
        ),
        "OPS/book.opf": (
            b'<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
            b'<item id="c1" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
            b'</manifest><spine><itemref idref="c1"/></spine></package>'
        ),
        "OPS/chapter.xhtml": (
            b'<html><body><h1>Chapter heading</h1><p>Chapter one</p>'
            b'<script>evil()</script></body></html>'
        ),
    })


def test_pdf_rotated_and_scan_pages_have_no_fake_ocr() -> None:
    class Page:
        def __init__(self, rotation: int, text: str) -> None:
            self.rotation, self.text = rotation, text

        def extract_text(self) -> str:
            return self.text

    class Reader:
        def __init__(self, stream: BytesIO) -> None:
            assert stream.read(5) == b"%PDF-"
            self.pages = [Page(90, "Rotated evidence"), Page(0, "")]

    original = b"%PDF-1.7 synthetic reader fixture"
    document = import_document(original, "application/pdf", pdf_reader_factory=Reader)
    assert document.pages[0].rotation == 90
    assert document.pages[0].text == "Rotated evidence"
    assert document.pages[1].status == "needs_ocr"
    assert document.pages[1].text == ""
    assert FullText.from_json(document.to_json()) == document


def test_real_pypdf_extracts_self_authored_rotated_text() -> None:
    pypdf = pytest.importorskip("pypdf")
    generic = pytest.importorskip("pypdf.generic")
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = generic.DictionaryObject(
        {
            generic.NameObject("/Type"): generic.NameObject("/Font"),
            generic.NameObject("/Subtype"): generic.NameObject("/Type1"),
            generic.NameObject("/BaseFont"): generic.NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[generic.NameObject("/Resources")] = generic.DictionaryObject(
        {
            generic.NameObject("/Font"): generic.DictionaryObject(
                {generic.NameObject("/F1"): font_ref}
            )
        }
    )
    stream = generic.DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 200 Td (Golden evidence text) Tj ET")
    page[generic.NameObject("/Contents")] = writer._add_object(stream)
    page.rotate(90)
    binary = BytesIO()
    writer.write(binary)

    document = import_document(binary.getvalue(), "application/pdf")
    assert document.extraction_version == "rw-fulltext-1"
    assert document.pages[0].rotation == 90
    assert document.pages[0].text.strip() == "Golden evidence text"
    assert document.pages[0].status == "text"
    assert document.pages[0].sha256


def test_pdf_no_parser_and_corruption() -> None:
    with pytest.raises(EvidenceError) as exc:
        import_document(b"not pdf", "application/pdf")
    assert exc.value.code == "INVALID_DOCUMENT"
    with pytest.raises(EvidenceError) as exc:
        import_document(b"%PDF-1.4\n", "application/pdf")
    assert exc.value.code in {"MISSING_DEPENDENCY", "INVALID_DOCUMENT"}


def test_docx_and_epub_preserve_real_text() -> None:
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    word = import_document(docx(), media)
    assert [page.text for page in word.pages] == ["Evidence", "\u0645\u062a\u0646"]
    assert word.pages[0].section_kind == "Heading1"
    assert word.pages[0].heading == "Evidence"
    assert word.pages[1].section_kind == "paragraph"
    book = import_document(epub(), "application/epub+zip")
    assert "Chapter one" in book.pages[0].text
    assert "evil" not in book.pages[0].text
    assert book.pages[0].label == "OPS/chapter.xhtml"
    assert book.pages[0].section_kind == "epub_spine_item"
    assert book.pages[0].heading == "Chapter heading"


def test_document_section_metadata_persists_after_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with ProjectStore.create(root, "Sections", "What was imported?", "exploratory") as store:
        source = LibraryService(store).import_document(docx(), "Structured DOCX", media)
        before = LibraryService(store).source_pages(source["source_id"])
        assert before["pages"][0]["heading"] == "Evidence"
        assert before["pages"][0]["section_kind"] == "Heading1"
    with ProjectStore(root) as reopened:
        after = LibraryService(reopened).source_pages(source["source_id"])
        assert after["pages"] == before["pages"]


def test_reject_external_relationships_and_archive_traversal() -> None:
    with pytest.raises(EvidenceError) as exc:
        import_document(docx(external=True),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert exc.value.code == "UNSAFE_DOCUMENT"
    malicious = archive({"../escape": b"x", "word/document.xml": b"y"})
    with pytest.raises(EvidenceError) as exc:
        import_document(malicious,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert exc.value.code == "UNSAFE_DOCUMENT"


def test_reject_archive_bombs_and_duplicate_paths() -> None:
    binary = BytesIO()
    with zipfile.ZipFile(binary, "w") as output:
        output.writestr("same", "first")
        output.writestr("same", "second")
    with pytest.raises(EvidenceError, match="Duplicate"):
        import_document(binary.getvalue(), "application/epub+zip")


def test_quote_is_exact_and_source_revision_bound() -> None:
    document = import_document("A caf\u00e9. \u201cQuoted\u201d".encode(), "text/plain")
    assert verify_quote(document, 1, 2, 6, "caf\u00e9")["verified"]
    result = verify_quote(document, 1, 2, 6, "cafe\u0301")
    assert not result["verified"]
    assert result["reason"] == "unicode_or_punctuation_difference"
    assert not verify_quote(document, 1, 8, 16, '"Quoted"')["verified"]
    assert not verify_quote(document, 1, 2, 6, "caf\u00e9", source_sha256="0" * 64)["verified"]
    with pytest.raises(EvidenceError):
        create_highlight(document, 1, 2, 6, "invented")


def test_highlight_survives_serialization_and_safe_relocation() -> None:
    source = import_document(b"before cited after", "text/plain")
    anchor = create_highlight(source, 1, 7, 12, "cited")
    assert relocate_highlight(anchor, FullText.from_json(source.to_json()))["status"] == "unchanged"
    changed = import_document(b"before cited after extra", "text/plain")
    relocated = relocate_highlight(anchor, changed)
    assert relocated["verified"] and relocated["status"] == "relocated"
    repeated = import_document(b"before cited after cited", "text/plain")
    assert relocate_highlight(anchor, repeated)["status"] == "ambiguous"
    assert not relocate_highlight(anchor, repeated)["verified"]


def test_hash_tampering_detected_on_reload() -> None:
    original = import_document(b"immutable", "text/plain")
    tampered = original.to_json().replace("immutable", "different")
    with pytest.raises(EvidenceError) as exc:
        FullText.from_json(tampered)
    assert exc.value.code == "INTEGRITY_ERROR"


def test_source_limit_and_unsupported_media() -> None:
    with pytest.raises(EvidenceError) as exc:
        import_document(b"a" * (32 * 1024 * 1024 + 1), "text/plain")
    assert exc.value.code == "RESOURCE_LIMIT"
    with pytest.raises(EvidenceError) as exc:
        import_document(b"text", "application/octet-stream")
    assert exc.value.code == "UNSUPPORTED_FORMAT"
