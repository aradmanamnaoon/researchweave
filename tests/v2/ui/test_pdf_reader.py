"""Actual QtPdf rendering, local file bounds and page navigation tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from researchweave.ui import build_ui_facade, build_ui_shell
from researchweave.ui.contracts import UIError
from researchweave.ui.pdf_reader import PDFReader, validate_pdf_file


def create_minimal_pdf(path: Path, *, pages: int = 1) -> None:
    """Generate a tiny valid, entirely fictional test PDF with correct xref."""
    if pages != 1:
        raise ValueError("This fixture builds one page.")
    stream = b"BT /F1 16 Tf 35 105 Td (ResearchWeave synthetic PDF) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, entry in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n".encode())
        result.extend(entry)
        result.extend(b"\nendobj\n")
    xref_position = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_position).encode() + b"\n%%EOF\n"
    )
    path.write_bytes(result)


@pytest.fixture
def qt_app():
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    return app


def test_pdf_validation_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "example.pdf"
    create_minimal_pdf(path)
    resolved, size, digest = validate_pdf_file(path)
    assert resolved == path.resolve()
    assert size == len(path.read_bytes())
    assert len(digest) == 64
    (tmp_path / "renamed.pdf").write_text("Fake", encoding="utf-8")
    with pytest.raises(UIError):
        validate_pdf_file(tmp_path / "renamed.pdf")
    with pytest.raises(UIError):
        validate_pdf_file(tmp_path / "missing.pdf")
    bad_suffix = tmp_path / "renamed.txt"
    bad_suffix.write_bytes(path.read_bytes())
    with pytest.raises(UIError):
        validate_pdf_file(bad_suffix)


def test_qtpdf_renders_and_navigation(qt_app, tmp_path: Path) -> None:
    pdf = tmp_path / "simple.pdf"
    create_minimal_pdf(pdf)
    reader = PDFReader()
    receipt = reader.open_file(pdf)
    assert receipt is not None, reader.status_label.text()
    assert receipt["title"] == "simple.pdf"
    assert receipt["local_only"]
    assert receipt["pages"] == 1
    assert reader.current_page() == 1
    assert reader.jump(1)
    assert not reader.jump(2)
    reader.page_input.setText("invalid")
    reader.go_to_entry()
    assert "valid page" in reader.status_label.text()
    reader.change_zoom("150%")
    assert reader.view.zoomFactor() == pytest.approx(1.5)
    reader.change_zoom("Fit page")
    reader.search_input.setText("synthetic")
    reader.search_text()
    for _ in range(20):
        qt_app.processEvents()
        QTest.qWait(10)
        if reader.search_model.count() > 0:
            break
    assert reader.search_model.count() == 1
    assert "page 1" in reader.status_label.text().lower()
    reference = reader.current_page_reference()
    assert reference is not None
    assert reference["page"] == 1
    assert reference["sha256"] == receipt["sha256"]
    assert reference["verified_text_coordinates"] is False
    reader.search_input.setText("not-in-fixture")
    reader.search_text()
    for _ in range(20):
        qt_app.processEvents()
        QTest.qWait(10)
    assert reader.search_model.count() == 0
    assert "ocr" in reader.status_label.text().lower()
    reader.resize(900, 600)
    reader.show()
    qt_app.processEvents()
    assert reader.view.grab().width() > 200
    reader.close_file()
    assert reader.document.pageCount() == 0
    assert reader.metadata is None
    reader.close()


def test_corrupt_pdf_and_desktop_wiring(qt_app, tmp_path: Path) -> None:
    damaged = tmp_path / "damaged.pdf"
    damaged.write_bytes(b"%PDF-1.4\nThis is not a valid PDF document")
    reader = PDFReader()
    result = reader.open_file(damaged)
    assert result is None
    assert "could not" in reader.status_label.text().lower()
    reader.close()
    shell = build_ui_shell(fake_services=build_ui_facade(tmp_path))
    shell.navigate("PDF Reader")
    assert shell.pdf_reader.accessibleName() == "Local PDF reader"
    assert shell.page_heading.text() == "PDF Reader"
    shell.close()
