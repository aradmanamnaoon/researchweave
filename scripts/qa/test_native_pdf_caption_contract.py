"""F37 read-only PDF caption candidate contract; not figure/table extraction."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CaptionPreviewContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.desktop = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.preview = (ROOT / "crates/researchweave-desktop/src/pdf_figure_candidates.rs").read_text(encoding="utf-8")
        cls.engine = (ROOT / "crates/researchweave-desktop/src/pdf_engine.rs").read_text(encoding="utf-8")

    def test_source_bound_caption_only_results_require_human_verification(self) -> None:
        self.assertIn("preview_pdf_figure_table_candidates", self.desktop)
        self.assertIn("Figure/table caption suggestions are unverified", self.desktop)
        self.assertIn("candidate.content_extracted", self.desktop)
        self.assertIn("!candidate.human_confirmation_required", self.desktop)
        self.assertIn("candidate.caption_bounds_points", self.desktop)
        self.assertIn("source_sha256", self.preview)
        self.assertIn("caption_first_line", self.preview)
        self.assertIn("human_confirmation_required", self.preview)
        self.assertIn("content_extracted: false", self.preview)
        self.assertIn("MAX_CAPTIONS_TOTAL: usize = 128", self.preview)
        self.assertIn("MAX_PAGES: usize = 64", self.preview)

    def test_user_can_navigate_but_not_silently_store_unverified_contents(self) -> None:
        self.assertIn("callback scan-pdf-caption-candidates(string, int);", self.ui)
        self.assertIn("Preview unverified local PDF figure and table caption anchors", self.ui)
        self.assertIn("Inspect unverified PDF caption ", self.ui)
        self.assertIn('root.load-pdf(pdf-path.text, "", caption.page-number)', self.ui)
        self.assertIn('source-sha256: string,', self.ui)
        self.assertIn('root.pdf-verified-caption-sha = caption.source-sha256;', self.ui)
        self.assertIn('pdf_engine::render_search_at_verified(', self.desktop)
        self.assertIn('expected_source_sha.as_str()', self.desktop)
        self.assertIn("if ui.get_pdf_caption_request_id() != request_id", self.desktop)
        self.assertIn("ui.get_pdf_local_path() != path", self.desktop)
        self.assertIn("root.pdf-caption-status = \"PDF path changed.", self.ui)
        self.assertIn("A different PDF was selected. Prior caption anchors were cleared", self.desktop)
        self.assertNotIn("INSERT INTO", self.preview)

    def test_native_pdf_source_change_invalidates_stale_render_and_caption_source(self) -> None:
        self.assertIn('callback invalidate-pdf-view();', self.ui)
        self.assertIn('root.invalidate-pdf-view();', self.ui)
        self.assertIn('root.pdf-verified-caption-sha = "";', self.ui)
        self.assertIn('app.on_invalidate_pdf_view({', self.desktop)
        self.assertIn('ui.set_pdf_job(ui.get_pdf_job().wrapping_add(1));', self.desktop)
        self.assertIn('ui.set_pdf_image(Image::default());', self.desktop)
        self.assertIn('if ui.get_pdf_job() != job_id || ui.get_pdf_local_path() != path {', self.desktop)
        self.assertIn('Caption navigation refused:', self.desktop)

    def test_native_pdf_render_has_bounded_input_text_pixels_and_overflow_guards(self) -> None:
        self.assertIn("const MAX_NATIVE_PDF_BYTES: u64 = 128 * 1024 * 1024", self.engine)
        self.assertIn("fn read_bounded_pdf(", self.engine)
        self.assertIn("let contents = read_bounded_pdf(pdf_path)?;", self.engine)
        self.assertIn("use super::{read_bounded_pdf, runtime_library};", self.preview)
        self.assertIn("let bytes = read_bounded_pdf(pdf_path)?;", self.preview)
        self.assertNotIn("read_bounded_find_next_pdf", self.preview)
        self.assertNotIn("tempfile::", self.engine)
        self.assertNotIn("std::fs::read(pdf_path)", self.engine)
        self.assertIn("const MAX_PAGE_TEXT_BYTES: usize = 16 * 1024 * 1024", self.engine)
        self.assertIn("let required = width", self.engine)
        self.assertIn(".checked_mul(height)", self.engine)
        self.assertIn("stride_bytes > render.pixels().len()", self.engine)
        self.assertIn("oversized_sparse_pdf_is_rejected_before_loading_native_pdfium", self.engine)

    def test_pdf_search_and_find_next_bound_native_text_geometry_before_allocating(self) -> None:
        self.assertIn("const MAX_PAGE_GLYPHS: usize = 120_000;", self.engine)
        self.assertIn(".text_with_limit(MAX_PAGE_GLYPHS)", self.engine)
        self.assertNotIn(".text()\n", self.engine)
        self.assertIn("fn matched_glyph_bounds(", self.engine)
        self.assertIn("fn valid_page_rect(", self.engine)


if __name__ == "__main__":
    unittest.main()
