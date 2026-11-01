"""Guard native Windows UIA manuscript recovery after title-page scroll.

This source check is not a substitute for installed Windows UI Automation QA.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WindowsManuscriptScrollContract(unittest.TestCase):
    def test_f04_collapse_reveals_real_manuscript_editor_by_keyboard(self) -> None:
        script = (
            ROOT / "crates/researchweave-desktop/tests/windows-uia-smoke.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("function FocusByShiftTab(", script)
        self.assertIn(
            "$manuscriptReferenceAfterF04 = Named $window "
            "([System.Windows.Automation.ControlType]::Edit) "
            "'Manuscript citation reference ID'",
            script,
        )
        self.assertIn(
            "$null = FocusByShiftTab $manuscriptReferenceAfterF04 "
            "([System.Windows.Automation.ControlType]::Edit) 'Manuscript ID' 12",
            script,
        )
        self.assertIn(
            "$f05ManuscriptId = FocusByShiftTab $f05ManuscriptAnchor "
            "([System.Windows.Automation.ControlType]::Edit) 'Manuscript ID' 12",
            script,
        )
        self.assertIn("'Manuscript section body' 35", script)
        self.assertIn(
            "PASS: F04 collapsed native title-page builder previews", script
        )


if __name__ == "__main__":
    unittest.main()
