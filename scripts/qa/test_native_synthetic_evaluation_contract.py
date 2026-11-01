"""Source wiring/CI obligations for native synthetic-only F44 previews.

Only actual installed Xvfb/AT-SPI or UIA acceptance can establish native UI
behavior; these contracts protect the minimum product/security pathway.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NativeSyntheticEvaluationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = (
            ROOT / "crates/researchweave-desktop/src/f44_synthetic_evaluation.rs"
        ).read_text(encoding="utf-8")
        cls.desktop = (
            ROOT / "crates/researchweave-desktop/src/main.rs"
        ).read_text(encoding="utf-8")
        cls.slint = (
            ROOT / "crates/researchweave-desktop/ui/main.slint"
        ).read_text(encoding="utf-8")
        cls.atspi = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(
            encoding="utf-8"
        )

    def test_adapter_reuses_trusted_scientific_metrics_and_sha_receipts(self) -> None:
        for exact in (
            "gold_commitment(&gold)",
            "prediction_commitment(&predictions)",
            "evaluate_and_render_markdown(request)",
            "rendered.evaluation_provenance_sha256 != report.provenance_sha256",
            'Sha256::digest(rendered.markdown.as_bytes())',
            "!request.synthetic_fixture",
            "report.model_trained_or_validated",
            "report.project_database_verified",
            "MAX_NATIVE_INPUT_BYTES: usize = 128 * 1024",
            "MAX_NATIVE_SLOTS: usize = 1_000",
            "MAX_NATIVE_REPORT_BYTES: usize = 64 * 1024",
            "fn synthetic_sample_has_a_reproducible_redacted_receipt()",
            "fn malformed_stale_or_misrepresented_synthetic_input_fails_closed()",
        ):
            self.assertIn(exact, self.adapter)
        self.assertNotIn("std::fs::", self.adapter)
        self.assertNotIn("reqwest::", self.adapter)

    def test_explicit_native_buttons_invalidate_unsaved_source_and_failed_receipts(self) -> None:
        self.assertIn("mod f44_synthetic_evaluation;", self.desktop)
        self.assertIn("app.on_preview_synthetic_evaluation({", self.desktop)
        self.assertIn("app.on_load_synthetic_evaluation_example({", self.desktop)
        self.assertIn("f44_synthetic_evaluation::preview_synthetic_json", self.desktop)
        self.assertIn('ui.set_synthetic_evaluation_fixture("".into());', self.desktop)
        self.assertIn('ui.set_synthetic_evaluation_open(false);', self.desktop)
        self.assertIn("callback preview-synthetic-evaluation(string);", self.slint)
        self.assertIn("callback load-synthetic-evaluation-example();", self.slint)
        self.assertIn("if root.synthetic-evaluation-open: Rectangle", self.slint)
        self.assertIn("edited(text) => {", self.slint)
        self.assertIn('root.synthetic-evaluation-receipt = "No current receipt after a source edit.";', self.slint)
        self.assertIn(
            "Copyable SHA verified redacted synthetic extraction evaluation receipt",
            self.slint,
        )
        self.assertIn("read-only: true;", self.slint)
        self.assertIn("Clear local synthetic evaluation input and preview", self.slint)
        self.assertIn("No project write or network.", self.desktop)

    def test_installed_native_positive_and_negative_are_strict_ci_requirements(self) -> None:
        markers = (
            "F44_NATIVE_SYNTHETIC_SHA_REDACTED_PREVIEW_NO_WRITE_OK",
            "F44_NATIVE_INVALID_FIXTURE_REFUSED_NO_WRITE_OK",
        )
        for marker in markers:
            self.assertIn(f'print("{marker}")', self.atspi)
            for workflow in (
                ".github/workflows/rust-release-candidate.yml",
                ".github/workflows/release.yml",
            ):
                self.assertIn(marker, (ROOT / workflow).read_text(encoding="utf-8"))
        self.assertIn('read_visible_field_keyboard(', self.atspi)
        self.assertIn('hashlib.sha256(f44_receipt.encode("utf-8"))', self.atspi)
        self.assertIn('project_event_snapshot(original_project) != f44_before', self.atspi)
        self.assertIn('"Synthetic MRI measurement" in f44_receipt', self.atspi)


if __name__ == "__main__":
    unittest.main()
