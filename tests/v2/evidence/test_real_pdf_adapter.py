from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from researchweave.evidence.errors import EvidenceError
from researchweave.evidence.fulltext import import_document, verify_quote


def _text_pdf(text: str) -> bytes:
    """Build a tiny self-authored one-page PDF with a standard Type1 font."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_real_pypdf_text_extraction_and_quote_anchor() -> None:
    data = _text_pdf("Synthetic public-domain evidence sentence.")
    document = import_document(data, "application/pdf")
    assert len(document.pages) == 1
    page = document.pages[0]
    assert page.status == "text"
    assert "Synthetic public-domain evidence sentence." in page.text
    start = page.text.index("public-domain evidence")
    verified = verify_quote(
        document, 1, start, start + len("public-domain evidence"), "public-domain evidence"
    )
    assert verified["verified"] is True
    assert verified["page_sha256"] == page.sha256


def test_real_pypdf_encrypted_document_is_rejected_without_decryption_attempt() -> None:
    reader = PdfReader(BytesIO(_text_pdf("Encrypted synthetic fixture.")))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("fixture-password")
    target = BytesIO()
    writer.write(target)
    with pytest.raises(EvidenceError) as encrypted:
        import_document(target.getvalue(), "application/pdf")
    assert encrypted.value.code == "UNSUPPORTED_FORMAT"
