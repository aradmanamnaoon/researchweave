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
        self.assertIn('root.load-pdf(pdf-path.text, pdf-query.text, caption.page-number)', self.ui)
        self.assertIn("if ui.get_pdf_caption_request_id() != request_id", self.desktop)
        self.assertIn("ui.get_pdf_local_path() != path", self.desktop)
        self.assertNotIn("INSERT INTO", self.preview)


if __name__ == "__main__":
    unittest.main()
