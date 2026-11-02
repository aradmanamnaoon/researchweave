"""Source checks for the compact native PDF reader's outer scroll boundary.

These tests verify the authored Slint structure and security-sensitive control
callbacks; native UIA/AT-SPI accessibility still requires installed GUI QA.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


UI = Path(__file__).resolve().parents[2] / "crates/researchweave-desktop/ui/main.slint"


def slint_block(source: str, marker: str) -> str:
    """Return a balanced Slint block, ignoring braces in strings/comments."""
    start = source.index(marker) + len(marker)
    depth = 1
    in_string = False
    in_line_comment = False
    escaped = False
    for index in range(start, len(source)):
        ch = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        prev_char = source[index - 1] if index > 0 else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == "/" and next_char == "/" and prev_char != "/":
            in_line_comment = True
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"Unclosed Slint region: {marker}")


class PdfReaderScrollableLayoutContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = UI.read_text(encoding="utf-8")
        cls.reader = slint_block(cls.source, "if root.page == 7: Rectangle {")
        cls.outer = slint_block(cls.reader, "pdf-reader-scroll := ScrollView {")

    def test_pdf_image_and_caption_list_both_belong_to_outer_scroll(self) -> None:
        self.assertIn("accessible-role: region;", self.outer)
        self.assertIn('accessible-label: "Scrollable PDF captions and page";', self.outer)
        self.assertIn("vertical-stretch: 1;", self.outer)
        self.assertIn("if root.pdf-caption-candidates.length > 0: ScrollView {", self.outer)
        self.assertIn('accessible-label: "PDF caption anchor preview status "', self.outer)
        self.assertIn('accessible-label: "Rendered PDF page";', self.outer)
        self.assertIn("pdf-fit := Rectangle {", self.outer)
        self.assertIn("pdf-page-canvas := Rectangle {", self.outer)
        self.assertIn("source: root.pdf-image;", self.outer)
        self.assertIn("if root.pdf-highlight-visible: Rectangle {", self.outer)
        self.assertRegex(self.outer, r"min-height:\s*380px;\s*preferred-height:\s*480px;")
        self.assertIn("clip: true;", self.outer)
        self.assertLess(
            self.outer.index("if root.pdf-caption-candidates.length > 0: ScrollView {"),
            self.outer.index('accessible-label: "Rendered PDF page";'),
        )

    def test_navigation_is_fixed_above_scroll_with_keyboard_reachable_jumps(self) -> None:
        before = self.reader[:self.reader.index("pdf-reader-scroll := ScrollView {")]
        for name in (
            "PDF file path", "Choose local PDF with native file picker",
            "PDF search query", "Open PDF", "Search PDF", "Previous PDF page",
            "Next PDF page", "Find next PDF matching page",
        ):
            self.assertIn(f'accessible-label: "{name}";', before)
        self.assertIn("min(pdf-page-canvas.y,", before)
        self.assertIn("pdf-reader-scroll.content-height - pdf-reader-scroll.visible-height", before)
        self.assertIn("pdf-reader-scroll.content-y = 0px;", before)
        self.assertIn('accessible-label: "Scroll to rendered PDF page";', before)
        self.assertIn('accessible-label: "Scroll back to PDF caption tools";', before)
        self.assertEqual(self.reader.count("pdf-reader-scroll := ScrollView {"), 1)
        self.assertEqual(self.reader.count("for caption in root.pdf-caption-candidates:"), 1)

    def test_pdf_source_verification_and_caption_safety_callbacks_are_preserved(self) -> None:
        for statement in (
            "root.invalidate-pdf-view();",
            'root.pdf-verified-caption-sha = "";',
            "root.scan-pdf-caption-candidates(pdf-path.text, root.pdf-caption-request-id);",
            "root.pdf-verified-caption-sha = caption.source-sha256;",
            'root.load-pdf(pdf-path.text, "", caption.page-number);',
            "root.load-pdf(pdf-path.text, pdf-query.text, root.pdf-page-number - 1);",
            "root.load-pdf(pdf-path.text, pdf-query.text, root.pdf-page-number + 1);",
            "root.pdf-caption-candidates = [];",
        ):
            self.assertIn(statement, self.reader)
        self.assertIn("No extracted figure or table contents.", self.reader)
        self.assertNotIn("project.save", self.outer)


if __name__ == "__main__":
    unittest.main()
