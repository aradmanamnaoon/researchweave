"""Guard genuine installed Windows export-field visibility and source receipt.

Source assertions cannot replace the hosted UI Automation receipt.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PS = ROOT / "crates/researchweave-desktop/tests/windows-uia-smoke.ps1"


class NativeManuscriptExportRevealContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = PS.read_text(encoding="utf-8")
        cls.reveal = cls.script.split(
            "function Reveal-ManuscriptExportPath(", 1
        )[1].split("function Reveal-ManuscriptIdAfterNativeScroll(", 1)[0]

    def test_real_visible_edit_is_required_before_writing(self) -> None:
        self.assertIn("'Manuscript export destination path'", self.reveal)
        self.assertIn("[System.Drawing.Rectangle]::Intersect", self.reveal)
        self.assertIn("$item.Current.IsOffscreen", self.reveal)
        self.assertIn("$pixel.Width -ge 100 -and $pixel.Height -ge 18", self.reveal)
        self.assertIn("EnsureLiveFocus $found", self.reveal)
        self.assertIn("[System.Windows.Automation.ScrollPattern]::Pattern", self.reveal)
        self.assertIn("[ResearchWeaveNativeWheel]::mouse_event", self.reveal)
        self.assertIn("$attempt -lt 16", self.reveal)
        self.assertIn("throw \"Manuscript destination Edit was not visible", self.reveal)
        self.assertNotIn("SetValue(", self.reveal)

    def test_physical_save_sha_and_overwrite_refusal_stay_mandatory(self) -> None:
        script = self.script
        self.assertIn("$markdownPath = Reveal-ManuscriptExportPath $window $exportAnchor", script)
        self.assertIn("$markdownPath.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue($physicalMarkdown)", script)
        self.assertIn("if (-not (Test-Path -LiteralPath $physicalMarkdown -PathType Leaf))", script)
        self.assertIn("Get-FileHash -LiteralPath $physicalMarkdown -Algorithm SHA256", script)
        self.assertIn("Repeated physical export modified an existing manuscript file", script)
        self.assertIn("Physical export overwrote a pre-existing file", script)


if __name__ == "__main__":
    unittest.main()
