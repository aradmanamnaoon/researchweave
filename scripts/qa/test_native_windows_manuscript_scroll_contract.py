"""Guard native Windows UIA manuscript recovery after title-page scroll.

This source check is not a substitute for installed Windows UI Automation QA.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WindowsManuscriptScrollContract(unittest.TestCase):
    def test_f04_collapse_reveals_real_manuscript_editor_by_bounded_native_scroll(self) -> None:
        script = (
            ROOT / "crates/researchweave-desktop/tests/windows-uia-smoke.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("function Reveal-ManuscriptIdAfterNativeScroll(", script)
        self.assertIn("[System.Windows.Automation.ScrollPattern]::Pattern", script)
        self.assertIn("[ResearchWeaveNativeWheel]::mouse_event(0x0800, 0, 0, 360, [UIntPtr]::Zero)", script)
        self.assertIn("$attempt -lt 12", script)
        self.assertIn("$item.Current.IsOffscreen", script)
        self.assertIn("Installed Manuscript ID remains inaccessible after bounded native UIA/wheel scrolling", script)
        self.assertIn(
            "$manuscriptReferenceAfterF04 = Named $window "
            "([System.Windows.Automation.ControlType]::Edit) "
            "'Manuscript citation reference ID'",
            script,
        )
        self.assertIn(
            "$null = Reveal-ManuscriptIdAfterNativeScroll $window $manuscriptReferenceAfterF04",
            script,
        )
        self.assertIn(
            "$f05ManuscriptId = Reveal-ManuscriptIdAfterNativeScroll $window $f05ManuscriptAnchor",
            script,
        )
        self.assertIn("'Manuscript section body' 35", script)
        self.assertIn(
            "PASS: F04 collapsed native title-page builder previews", script
        )


if __name__ == "__main__":
    unittest.main()
