"""Source-level guard for the F44 synthetic-only native evaluation slice.

This does not replace installed Linux AT-SPI acceptance or Rust evaluator tests.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeF44SyntheticEvaluationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.desktop = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.adapter = (ROOT / "crates/researchweave-desktop/src/f44_synthetic_evaluation.rs").read_text(encoding="utf-8")
        cls.qa = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(encoding="utf-8")

    def test_native_controls_have_real_typed_callbacks_and_failure_reset(self) -> None:
        for signature in (
            "callback load-synthetic-evaluation-example();",
            "callback preview-synthetic-evaluation(string);",
        ):
            self.assertIn(signature, self.ui)
        for callback in (
            "app.on_load_synthetic_evaluation_example({",
            "app.on_preview_synthetic_evaluation({",
        ):
            self.assertIn(callback, self.desktop)
        self.assertIn("root.preview-synthetic-evaluation(synthetic-eval-input.text);", self.ui)
        self.assertIn("root.synthetic-evaluation-receipt = \"No current receipt after a source edit.\";", self.ui)
        self.assertIn("ui.set_synthetic_evaluation_fixture(\"\".into());", self.desktop)
        self.assertIn("No valid SHA-verified synthetic evaluation receipt", self.desktop)

    def test_adapter_has_strict_bounded_synthetic_only_receipts(self) -> None:
        for constraint in (
            "const MAX_NATIVE_INPUT_BYTES: usize = 128 * 1024;",
            "const MAX_NATIVE_SLOTS: usize = 1_000;",
            "const MAX_NATIVE_REPORT_BYTES: usize = 64 * 1024;",
            "evaluate_and_render_markdown(request)",
            "gold_commitment(&gold)",
            "prediction_commitment(&predictions)",
            "Sha256::digest(rendered.markdown.as_bytes())",
            "if !request.synthetic_fixture",
        ):
            self.assertIn(constraint, self.adapter)
        self.assertNotIn("std::fs::write(", self.adapter)
        self.assertNotIn("std::process::Command", self.adapter)
        self.assertIn("malformed_stale_or_misrepresented_synthetic_input_fails_closed", self.adapter)

    def test_real_linux_native_receipt_and_negative_checks_are_required(self) -> None:
        for marker in (
            "F44_NATIVE_SYNTHETIC_SHA_REDACTED_PREVIEW_NO_WRITE_OK",
            "F44_NATIVE_INVALID_FIXTURE_REFUSED_NO_WRITE_OK",
        ):
            self.assertIn(marker, self.qa)
            for workflow in (
                ".github/workflows/rust-release-candidate.yml",
                ".github/workflows/release.yml",
            ):
                self.assertIn(marker, (ROOT / workflow).read_text(encoding="utf-8"))
        self.assertIn('force_clipboard=True', self.qa)
        self.assertIn("hashlib.sha256(f44_receipt.encode(\"utf-8\"))", self.qa)
        self.assertIn("project_event_snapshot(original_project) != f44_before", self.qa)


if __name__ == "__main__":
    unittest.main()
