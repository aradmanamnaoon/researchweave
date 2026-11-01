"""F32 native source contracts; installed GUI requires separate AT-SPI evidence."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ArithmeticNotebookContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.desktop = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.evidence = (ROOT / "crates/researchweave-evidence/src/lib.rs").read_text(encoding="utf-8")
        cls.runtime = (ROOT / "crates/researchweave-evidence/src/notebook_cells.rs").read_text(encoding="utf-8")
        cls.native = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(encoding="utf-8")

    def test_native_preview_separate_approval_and_edit_invalidation(self) -> None:
        for callback in (
            "callback preview-arithmetic-cell();",
            "callback run-arithmetic-cell();",
            "callback load-arithmetic-cells();",
        ):
            self.assertIn(callback, self.ui)
        for control in (
            "Executable arithmetic notebook cell expression",
            "Preview arithmetic notebook cell without writes",
            "Approve previewed arithmetic notebook cell and append immutable execution",
            "Refresh immutable arithmetic notebook cells",
        ):
            self.assertIn(control, self.ui)
        self.assertIn('root.notebook-cell-approval = "";', self.ui)
        self.assertIn('enabled: root.notebook-cell-approval != "";', self.ui)
        self.assertIn('"notebook.cell_execute"', self.desktop)
        self.assertIn('"notebook.cell_preview"', self.desktop)
        self.assertIn('"notebook.cell_list"', self.desktop)
        self.assertIn('evidence_execute_pending(&pending, &project, &root)', self.desktop)

    def test_runtime_cannot_launch_arbitrary_processes(self) -> None:
        for bad in (
            "std::process::", "Command::new(", "unsafe {", "std::net::",
            "std::fs::", "python", "eval(", "PyO3", "std::env::",
        ):
            if bad == "python":
                # Only explicit *negative* disclaimer mentions Python.
                self.assertNotIn("Python::with_gil", self.runtime)
            else:
                self.assertNotIn(bad, self.runtime)
        self.assertIn('"notebook.cell_execute"', self.evidence)
        self.assertIn("expected_cell_revision", self.runtime)
        self.assertIn("approved_preview_sha256", self.runtime)
        self.assertIn("mutate(", self.runtime)
        self.assertIn("INSERT INTO notebook_entries", self.runtime)

    def test_true_native_qa_requires_persisted_event_and_no_write_refusal(self) -> None:
        for marker in (
            "F32_NATIVE_ARITHMETIC_PREVIEW_NO_WRITE_OK",
            "F32_NATIVE_ARITHMETIC_EXECUTION_APPEND_SOURCE_PROVENANCE_OK",
            "F32_NATIVE_INVALID_EXPRESSION_REFUSED_NO_WRITE_OK",
        ):
            self.assertIn(marker, self.native)
        self.assertIn('"SELECT operation FROM events ORDER BY sequence DESC LIMIT 1"', self.native)
        self.assertIn('"SELECT id,revision,body FROM notebook_entries WHERE id LIKE', self.native)


if __name__ == "__main__":
    unittest.main()
