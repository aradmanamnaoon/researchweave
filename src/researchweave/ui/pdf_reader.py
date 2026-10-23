"""Native offline PDF viewing with explicit local-file selection.

QtPdf renders existing PDF pages and never converts scanned images to text,
visits links automatically, extracts confidential pages to a cloud service,
or guesses citations.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPointF, pyqtSignal
from PyQt6.QtPdf import QPdfDocument, QPdfSearchModel
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .contracts import UIError
from .design import named

MAX_PDF_BYTES = 64 * 1024 * 1024
CHUNK = 1024 * 1024
ZOOM_CHOICES = ("Fit width", "Fit page", "100%", "150%", "200%")


@dataclass(frozen=True)
class PDFMetadata:
    path: str
    title: str
    pages: int
    bytes: int
    sha256: str
    rendering_engine: str = "QtPdf"
    local_only: bool = True
    text_layer_verified: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "pages": self.pages,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "rendering_engine": self.rendering_engine,
            "local_only": self.local_only,
            "text_layer_verified": self.text_layer_verified,
            "note": (
                "File hash identifies bytes only. It is not a peer-review, "
                "bibliographic, citation or accessibility certificate."
            ),
        }


def validate_pdf_file(path: str | Path) -> tuple[Path, int, str]:
    """Bounded validation of a user-chosen local path without assuming trust."""
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise UIError("NOT_FOUND", "Selected document is not a regular file.",
                      "Choose an existing local PDF file.")
    if candidate.suffix.casefold() != ".pdf":
        raise UIError("INVALID_INPUT", "Selected document must have a .pdf filename.",
                      "Choose a local PDF document.")
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        raise UIError("NOT_FOUND", "PDF file cannot be accessed.",
                      "Choose a readable local PDF.") from exc
    if size < 8 or size > MAX_PDF_BYTES:
        raise UIError("RESOURCE_LIMIT", "PDF size is outside the 64 MiB preview limit.",
                      "Use a smaller document or create a reduced working copy.")
    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as stream:
            prefix = stream.read(8)
            if not prefix.startswith(b"%PDF-"):
                raise UIError("INVALID_INPUT", "File does not contain a PDF header.",
                              "Choose a valid PDF rather than a renamed file.")
            digest.update(prefix)
            consumed = len(prefix)
            while piece := stream.read(CHUNK):
                consumed += len(piece)
                if consumed > MAX_PDF_BYTES:
                    raise UIError("RESOURCE_LIMIT", "PDF changed while opening.",
                                  "Try a stable copy of the document.")
                digest.update(piece)
        if consumed != size:
            raise UIError("STALE_REVISION", "PDF changed while its hash was being recorded.",
                          "Choose a stable copy of this file.")
    except PermissionError as exc:
        raise UIError("NOT_FOUND", "PDF file is not readable.",
                      "Check local file access permissions.") from exc
    return candidate.resolve(), size, digest.hexdigest()


class PDFReader(QWidget):
    """Accessible single-document QtPdf viewer with bounded page navigation."""

    opened = pyqtSignal(object)
    failed = pyqtSignal(str)
    page_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        named(
            self, "Local PDF reader",
            "Read a selected local PDF. Page numbering is one-based in this interface."
        )
        self.document = QPdfDocument(self)
        self.view = QPdfView(self)
        named(self.view, "Rendered PDF pages")
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.SinglePage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.search_model = QPdfSearchModel(self)
        self.search_model.setDocument(self.document)
        self.view.setSearchModel(self.search_model)
        self.current_path: Path | None = None
        self.metadata: PDFMetadata | None = None

        column = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.load_button = QPushButton("Open local PDF")
        named(self.load_button, "Choose a PDF from local disk")
        self.load_button.clicked.connect(self.choose_file)
        tools.addWidget(self.load_button)
        self.previous_button = QPushButton("Previous page")
        named(self.previous_button, "Go to previous PDF page")
        self.previous_button.clicked.connect(lambda: self.navigate(-1))
        tools.addWidget(self.previous_button)
        self.page_input = QLineEdit("1")
        self.page_input.setMaximumWidth(80)
        self.page_input.setPlaceholderText("Page")
        named(self.page_input, "Current PDF page number")
        self.page_input.returnPressed.connect(self.go_to_entry)
        tools.addWidget(self.page_input)
        self.page_total = QLabel("of 0")
        self.page_total.setAccessibleName("Total PDF pages")
        tools.addWidget(self.page_total)
        self.next_button = QPushButton("Next page")
        named(self.next_button, "Go to next PDF page")
        self.next_button.clicked.connect(lambda: self.navigate(1))
        tools.addWidget(self.next_button)
        self.zoom_picker = QComboBox()
        self.zoom_picker.addItems(ZOOM_CHOICES)
        named(self.zoom_picker, "PDF magnification mode")
        self.zoom_picker.currentTextChanged.connect(self.change_zoom)
        tools.addWidget(self.zoom_picker)
        column.addLayout(tools)
        search_tools = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search verified PDF text layer")
        named(
            self.search_input,
            "Search local PDF text",
            "Search uses QtPdf's local text layer only; scanned image OCR is not inferred.",
        )
        self.search_input.returnPressed.connect(self.search_text)
        search_tools.addWidget(self.search_input)
        self.search_previous = QPushButton("Previous match")
        self.search_previous.clicked.connect(lambda: self.navigate_search(-1))
        named(self.search_previous, "Go to previous PDF text match")
        search_tools.addWidget(self.search_previous)
        self.search_next = QPushButton("Next match")
        self.search_next.clicked.connect(lambda: self.navigate_search(1))
        named(self.search_next, "Go to next PDF text match")
        search_tools.addWidget(self.search_next)
        column.addLayout(search_tools)
        column.addWidget(self.view)
        self.status_label = QLabel(
            "Select a local PDF. No file contents are uploaded or indexed."
        )
        self.status_label.setWordWrap(True)
        named(self.status_label, "PDF document status")
        column.addWidget(self.status_label)
        self.document.pageCountChanged.connect(self._on_pages)
        self.search_model.countChanged.connect(self._sync_search_status)
        navigator = self.view.pageNavigator()
        if navigator is not None:
            navigator.currentPageChanged.connect(self._on_page_change)
        self._sync_enabled()

    def choose_file(self) -> None:
        filename, accepted_filter = QFileDialog.getOpenFileName(
            self, "Open PDF for local viewing", os.path.expanduser("~"),
            "PDF documents (*.pdf)",
        )
        if filename:
            self.open_file(filename)

    def open_file(self, path: str | Path) -> dict[str, Any] | None:
        """Verify and load the selected file; never keep a broken prior page."""
        try:
            candidate, size, digest = validate_pdf_file(path)
        except UIError as exc:
            self.status_label.setText(f"{exc.message} {exc.recovery}")
            self.failed.emit(exc.message)
            return None
        self.document.close()
        self.current_path = None
        self.metadata = None
        error = self.document.load(str(candidate))
        if error != QPdfDocument.Error.None_:
            self.document.close()
            message = {
                QPdfDocument.Error.IncorrectPassword: (
                    "Encrypted PDF needs a password; the viewer cannot open it."
                ),
                QPdfDocument.Error.InvalidFileFormat: (
                    "QtPdf could not interpret this document."
                ),
                QPdfDocument.Error.UnsupportedSecurityScheme: (
                    "The PDF uses an unsupported protection scheme."
                ),
            }.get(error, f"PDF loading failed ({error.name}).")
            self.status_label.setText(message)
            self.failed.emit(message)
            self._sync_enabled()
            return None
        self.current_path = candidate
        self.metadata = PDFMetadata(
            path=str(candidate), title=candidate.name,
            pages=self.document.pageCount(), bytes=size, sha256=digest,
        )
        self.search_model.setDocument(self.document)
        self.search_model.setSearchString("")
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.zoom_picker.setCurrentText("Fit width")
        self.jump(1)
        self._sync_enabled()
        self.status_label.setText(
            f"{candidate.name} · {self.document.pageCount()} pages · "
            f"SHA-256 {digest}\n"
            "Page rendering is local. Verify all quotations and page citations manually."
        )
        info = self.metadata.as_dict()
        self.opened.emit(info)
        return info

    def _sync_enabled(self) -> None:
        count = self.document.pageCount()
        current = self.current_page()
        self.previous_button.setEnabled(count > 0 and current > 1)
        self.next_button.setEnabled(count > 0 and current < count)
        self.page_input.setEnabled(count > 0)
        self.zoom_picker.setEnabled(count > 0)
        self.search_input.setEnabled(count > 0)
        self.search_previous.setEnabled(count > 0 and self.search_model.count() > 0)
        self.search_next.setEnabled(count > 0 and self.search_model.count() > 0)
        self.page_total.setText(f"of {count}")

    def current_page(self) -> int:
        if self.document.pageCount() == 0:
            return 0
        navigator = self.view.pageNavigator()
        if navigator is None:
            return 0
        return max(1, min(
            self.document.pageCount(),
            navigator.currentPage() + 1,
        ))

    def _on_pages(self, count: int) -> None:
        self._sync_enabled()

    def _on_page_change(self, page: int) -> None:
        self.page_input.setText(str(page + 1))
        self._sync_enabled()
        self.page_changed.emit(page + 1)

    def jump(self, page_number: int) -> bool:
        count = self.document.pageCount()
        if count <= 0 or not 1 <= page_number <= count:
            self.status_label.setText(
                f"Page {page_number} is outside the available range 1–{count}."
            )
            return False
        navigator = self.view.pageNavigator()
        if navigator is None:
            self.status_label.setText("PDF navigation is unavailable.")
            return False
        navigator.jump(page_number - 1, QPointF(), 0)
        self.page_input.setText(str(page_number))
        self._sync_enabled()
        return True

    def go_to_entry(self) -> None:
        value = self.page_input.text().strip()
        try:
            page_number = int(value)
        except ValueError:
            self.status_label.setText("Enter a valid page number.")
            return
        if not self.jump(page_number):
            self.page_input.setText(str(self.current_page()))

    def navigate(self, delta: int) -> None:
        self.jump(self.current_page() + delta)

    def change_zoom(self, mode: str) -> None:
        if mode == "Fit width":
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        elif mode == "Fit page":
            self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        elif mode in ("100%", "150%", "200%"):
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(float(mode[:-1]) / 100.0)

    def search_text(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self.search_model.setSearchString("")
            self.status_label.setText(
                "Enter text to search the PDF's existing local text layer."
            )
            self._sync_enabled()
            return
        self.search_model.setSearchString(query)
        self._sync_search_status()

    def _sync_search_status(self) -> None:
        count = self.search_model.count()
        self.search_previous.setEnabled(count > 0)
        self.search_next.setEnabled(count > 0)
        if not self.search_input.text().strip():
            return
        if count == 0:
            self.status_label.setText(
                "No local text-layer matches. This does not imply OCR was attempted."
            )
            return
        current = self.view.currentSearchResultIndex()
        if not 0 <= current < count:
            current = 0
            self.view.setCurrentSearchResultIndex(current)
        result = self.search_model.resultAtIndex(current)
        if result.isValid():
            self.jump(result.page() + 1)
            context = f"{result.contextBefore()}[{self.search_input.text()}]{result.contextAfter()}"
            self.status_label.setText(
                f"Text-layer match {current + 1} of {count} · page {result.page() + 1}.\n"
                f"{context}\nVerify quotation and page reference against the rendered PDF."
            )

    def navigate_search(self, delta: int) -> None:
        count = self.search_model.count()
        if count <= 0:
            self._sync_search_status()
            return
        current = self.view.currentSearchResultIndex()
        if current < 0:
            current = 0
        else:
            current = (current + delta) % count
        self.view.setCurrentSearchResultIndex(current)
        self._sync_search_status()

    def current_page_reference(self) -> dict[str, Any] | None:
        if self.metadata is None or self.current_page() <= 0:
            return None
        return {
            "path": self.metadata.path,
            "sha256": self.metadata.sha256,
            "page": self.current_page(),
            "label": f"{self.metadata.title}, p. {self.current_page()}",
            "verified_text_coordinates": False,
            "note": (
                "Page reference identifies the rendered local PDF page. "
                "Verify quotation text manually before citing."
            ),
        }

    def close_file(self) -> None:
        self.document.close()
        self.current_path = None
        self.metadata = None
        self.search_model.setSearchString("")
        self.search_input.clear()
        self.page_input.setText("1")
        self.status_label.setText("No PDF is open.")
        self._sync_enabled()
