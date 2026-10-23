"""Bounded offline PDF text extraction with source/page evidence anchors."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from .errors import AIError
from .retrieval import EvidenceIndex


@dataclass(frozen=True)
class PDFPage:
    page_number: int
    text: str
    source_sha256: str


@dataclass(frozen=True)
class PDFReceipt:
    document_id: str
    pdf_sha256: str
    page_count: int
    indexed_pages: int
    source_ids: tuple[str, ...]
    warnings: tuple[str, ...]


class OfflinePDFImporter:
    """Uses pypdf for text; never executes embedded PDF actions or URLs."""

    def __init__(
        self,
        index: EvidenceIndex,
        *,
        max_pdf_bytes: int = 10_000_000,
        max_pages: int = 64,
        max_text_chars: int = 1_000_000,
    ) -> None:
        if not 1 <= max_pdf_bytes <= 50_000_000:
            raise AIError("INVALID_INPUT", "PDF byte budget is out of range")
        if not 1 <= max_pages <= 1000 or not 1 <= max_text_chars <= 10_000_000:
            raise AIError("INVALID_INPUT", "PDF page or extracted text budget is out of range")
        self.index = index
        self.max_pdf_bytes = max_pdf_bytes
        self.max_pages = max_pages
        self.max_text_chars = max_text_chars

    def extract(self, pdf_bytes: bytes) -> list[PDFPage]:
        if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
            raise AIError("UNSUPPORTED_FORMAT", "Document is not a valid PDF header")
        if len(pdf_bytes) > self.max_pdf_bytes:
            raise AIError("RESOURCE_LIMIT", "PDF exceeds the byte budget")
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise AIError("DEPENDENCY_MISSING", "Install the optional pypdf parser") from exc
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
            if reader.is_encrypted:
                raise AIError("UNSUPPORTED_FORMAT", "Encrypted PDFs require user-side decryption")
            page_count = len(reader.pages)
            if not 1 <= page_count <= self.max_pages:
                raise AIError("RESOURCE_LIMIT", "PDF page count is outside configured budget")
            pages: list[PDFPage] = []
            remaining = self.max_text_chars
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text(extraction_mode="plain") or ""
                if not isinstance(text, str) or len(text) > remaining:
                    raise AIError("RESOURCE_LIMIT", "PDF extracted text exceeds budget")
                remaining -= len(text)
                pages.append(PDFPage(number, text, hashlib.sha256(text.encode()).hexdigest()))
            return pages
        except AIError:
            raise
        except Exception as exc:
            raise AIError("UNSUPPORTED_FORMAT", "PDF parsing or text extraction failed") from exc

    def ingest(
        self,
        document_id: str,
        pdf_bytes: bytes,
        *,
        classification: str = "private",
    ) -> PDFReceipt:
        if (
            not document_id
            or len(document_id) > 80
            or any(
                character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for character in document_id
            )
        ):
            raise AIError("INVALID_INPUT", "Document ID must be a safe stable identifier")
        if classification not in {"public", "private", "restricted"}:
            raise AIError("INVALID_INPUT", "Invalid PDF privacy classification")
        pages = self.extract(pdf_bytes)
        source_prefix = f"pdf:{document_id}:page:"
        existing = [
            row[0]
            for row in self.index.connection.execute(
                "SELECT id FROM sources WHERE substr(id,1,?)=?",
                (len(source_prefix), source_prefix),
            )
        ]
        new_sources: dict[str, tuple[str, str]] = {}
        warnings: list[str] = []
        for page in pages:
            if not page.text.strip():
                warnings.append(f"Page {page.page_number} has no extractable text")
                continue
            source_id = f"{source_prefix}{page.page_number}"
            new_sources[source_id] = (page.text, classification)
        source_ids = list(new_sources)
        remove_ids = [old_id for old_id in existing if old_id not in new_sources]
        if new_sources or remove_ids:
            self.index.ingest_many(new_sources, remove_ids=remove_ids)
        return PDFReceipt(
            document_id,
            hashlib.sha256(pdf_bytes).hexdigest(),
            len(pages),
            len(source_ids),
            tuple(source_ids),
            tuple(warnings),
        )
