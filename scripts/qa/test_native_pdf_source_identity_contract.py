"""Static regression guards for F37's *real Windows UIA* source-identity gate.

These checks inspect actual source and the installed-app QA harness. They do
not claim to have launched Windows, proved PDFium extraction, or observed UIA.
The installed native gate remains windows-uia-smoke.ps1.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "crates/researchweave-desktop"


class PdfSourceIdentityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = (DESKTOP / "src/pdf_engine.rs").read_text(encoding="utf-8")
        cls.scan = (DESKTOP / "src/pdf_figure_candidates.rs").read_text(
            encoding="utf-8"
        )
        cls.desktop = (DESKTOP / "src/main.rs").read_text(encoding="utf-8")
        cls.ui = (DESKTOP / "ui/main.slint").read_text(encoding="utf-8")
        cls.native_qa = (DESKTOP / "tests/windows-uia-smoke.ps1").read_text(
            encoding="utf-8"
        )

    def test_exact_bounded_bytes_verified_before_native_pdfium_input(self) -> None:
        verified = self.engine.split(
            "pub fn render_search_at_verified(", 1
        )[1].split("fn verify_source_sha256(", 1)[0]
        self.assertLess(
            verified.index("let contents = read_bounded_pdf(pdf_path)?;"),
            verified.index("verify_source_sha256(&contents, expected_sha256)?;"),
        )
        self.assertLess(
            verified.index("verify_source_sha256(&contents, expected_sha256)?;"),
            verified.index("render_search_at_bytes(contents, query, page_index)"),
        )
        self.assertIn("Sha256::digest(bytes)", self.engine)
        self.assertIn("source bytes changed since the caption scan", self.engine)
        self.assertIn("let bytes = read_bounded_pdf(pdf_path)?;", self.scan)
        self.assertIn("Sha256::digest(&bytes)", self.scan)

    def test_slint_caption_provenance_reaches_verified_render(self) -> None:
        self.assertIn("source-sha256: string,", self.ui)
        self.assertIn(
            "root.pdf-verified-caption-sha = caption.source-sha256;", self.ui
        )
        self.assertIn(
            "pdf_engine::render_search_at_verified(", self.desktop
        )
        self.assertIn("expected_source_sha.as_str()", self.desktop)
        self.assertIn("root.invalidate-pdf-view();", self.ui)
        self.assertIn("ui.set_pdf_image(Image::default());", self.desktop)
        self.assertIn("Caption navigation refused:", self.desktop)
        self.assertIn(
            "if ui.get_pdf_job() != job_id || ui.get_pdf_local_path() != path {",
            self.desktop,
        )

    def test_actual_windows_native_qa_has_no_mock_or_skipped_gate(self) -> None:
        qa = self.native_qa
        # The F37 snapshot executes before the F14 end-of-script journey.
        # A C# type declared in a here-string is NOT registered until Add-Type.
        self.assertEqual(
            qa.count("Add-Type -TypeDefinition $f14ReadonlySqliteSource -ErrorAction Stop"),
            1,
        )
        self.assertLess(
            qa.index("Add-Type -TypeDefinition $f14ReadonlySqliteSource -ErrorAction Stop"),
            qa.index("function Get-F14ProjectSnapshot("),
        )
        self.assertLess(qa.index("function Get-F14ProjectSnapshot("), qa.index("$f37Before = Get-F14ProjectSnapshot $temporary"))
        self.assertIn("function Write-F37CaptionPdf(", qa)
        self.assertIn("[IO.File]::WriteAllBytes($Path, $bytes)", qa)
        self.assertIn("function Get-F37CanvasSample(", qa)
        self.assertIn("$graphics.CopyFromScreen(", qa)
        self.assertIn("function Focus-F37CaptionAction(", qa)
        self.assertIn("FocusByTab $Anchor", qa)
        self.assertIn("Select-FileThroughNativeDialog $window", qa)
        self.assertIn("Read-F37CaptionStatus $window", qa)
        self.assertIn("Get-F14ProjectSnapshot $temporary", qa)
        self.assertIn("Assert-F14Unchanged $f37Before", qa)
        self.assertIn("$f37ReplacementSize -ne $f37OriginalSize", qa)
        self.assertIn("$f37ReplacementSha -ceq $f37ExpectedSha", qa)
        self.assertIn("$f37RefusedCanvas -cne $f37BlankCanvas", qa)
        self.assertIn(
            "UIA_F37_NATIVE_CAPTION_SOURCE_SHA_VERIFIED_SAME_PATH_SUBSTITUTION_REFUSED_"
            "STALE_PIXELS_CLEARED_NO_PROJECT_WRITE_OK",
            qa,
        )
        self.assertRegex(
            qa,
            re.compile(
                r"\$f37Figure\.GetCurrentPattern\(\[System\.Windows\.Automation\."
                r"InvokePattern\]::Pattern\)\.Invoke\(\)"
            ),
        )
        # Other acceptance gates must not be sacrificed to make F37 pass.
        for protected in (
            "UIA_F14_KEEP_SEPARATE_COLD_RESTART_SOURCEBOUND_ROW_WITH_NO_WRITE_OK",
            "UIA_F43_INDEXED_PDF_SUGGEST_ONLY_NATIVE_NEGATIVE_NO_PROJECT_WRITES_OK",
            "UIA_F44_SYNTHETIC_SHA_VERIFIED_REDACTED_NO_PROJECT_WRITE_OK",
        ):
            self.assertIn(protected, qa)


if __name__ == "__main__":
    unittest.main()
