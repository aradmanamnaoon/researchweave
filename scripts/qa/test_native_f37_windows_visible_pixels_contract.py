"""Fail-closed source contract for native Windows F37 caption/page pixels.

This verifies authored UIA/physical-screen QA invariants, not execution on an
installed Windows app. Optional pure geometry tests use PowerShell if present.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "crates/researchweave-desktop/tests/windows-uia-smoke.ps1"
)


def function_body(source: str, name: str, next_name: str) -> str:
    start = source.index(f"function {name}(")
    end = source.index(f"function {next_name}(", start)
    return source[start:end]


class WindowsF37VisiblePixelsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.flow = cls.source[cls.source.index("    # F37: real installed PDFium"):cls.source.index(
            "    # Register a real project reference", cls.source.index("    # F37: real installed PDFium")
        )]

    def test_both_accessible_reader_scroll_actions_are_activated_in_native_order(self) -> None:
        flow = self.flow
        self.assertEqual(flow.count("Invoke-F37ReaderScroll $window 'Scroll to rendered PDF page'"), 3)
        self.assertEqual(flow.count("Invoke-F37ReaderScroll $window 'Scroll back to PDF caption tools'"), 3)
        blank = flow.index("$f37BlankCanvas = Get-F37CanvasSample $window")
        first_candidate = flow.index("$f37Figure = Focus-F37CaptionAction")
        rendered = flow.index("$f37RenderedCanvas = Get-F37CanvasSample")
        second_candidate = flow.rindex("$f37Figure = Focus-F37CaptionAction")
        refused = flow.index("$f37RefusedCanvas = Get-F37CanvasSample")
        self.assertLess(blank, first_candidate)
        self.assertLess(first_candidate, rendered)
        self.assertLess(rendered, second_candidate)
        self.assertLess(second_candidate, refused)
        self.assertIn("Invoke-AccessibleButton $Window $Name", function_body(
            self.source, "Invoke-F37ReaderScroll", "Focus-F37CaptionAction"
        ))

    def test_image_capture_uses_real_monitor_intersection_and_identical_screen_roi(self) -> None:
        begin = self.source.index("function Get-F37CanvasSample(")
        end = self.source.index("\ntry {\n    $p = Start-Process", begin)
        helper = self.source[begin:end]
        for required in (
            "'Rendered PDF page'", "Get-F37ReaderViewport $Window",
            "Get-F37PhysicalIntersection @($imageRect, $viewport, $win, $screen)",
            ").WorkingArea", "$visible.Width -lt 116", "$visible.Height -lt 56",
            "$region.Width -lt 100", "$region.Height -lt 40",
            "$covered.Equals($region)", "AutomationElement]::FromPoint",
            "[System.Windows.Automation.Automation]::Compare($hit, $images[0])",
            "$graphics.CopyFromScreen($region.Left, $region.Top, 0, 0, $bitmap.Size)",
            "$sha.ComputeHash($memory.ToArray())", "$digest -ceq $previousHash",
            "throw \"F37 installed PDF screen pixels did not stabilize:",
        ):
            self.assertIn(required, helper)
        self.assertNotIn("CopyFromScreen([int]$imageRect.Left", helper)
        self.assertIn(
            "$f37RenderedCanvas = Get-F37CanvasSample $window $f37BlankCanvas.Region",
            self.flow,
        )
        self.assertIn(
            "$f37RefusedCanvas = Get-F37CanvasSample $window $f37BlankCanvas.Region",
            self.flow,
        )
        self.assertIn("$f37RenderedCanvas.Digest -ceq $f37BlankCanvas.Digest", self.flow)
        self.assertIn("$f37RefusedCanvas.Digest -cne $f37BlankCanvas.Digest", self.flow)

    def test_source_identity_substitution_candidate_and_no_write_gates_remain_strict(self) -> None:
        for invariant in (
            "Test-SelectedFixturePath $current $f37Source",
            "2 candidates", "$f37Digest.Groups[1].Value -cne $f37ExpectedSha",
            "No figure pixels or table cells were extracted",
            "if ($f37Candidates.Count -ne 2)",
            "$f37Verified.Contains($f37ExpectedSha)",
            "$f37ReplacementSha -ceq $f37ExpectedSha",
            "$f37ReplacementSize -ne $f37OriginalSize",
            "Caption navigation refused: PDF source bytes changed since the caption scan",
            "if ($f37StillPresent.Count -ne 0)",
            "Assert-F14Unchanged $f37Before",
        ):
            self.assertIn(invariant, self.flow)
        self.assertEqual(self.flow.count("Assert-F14Unchanged $f37Before"), 3)

    @unittest.skipUnless(shutil.which("powershell") or shutil.which("pwsh"), "PowerShell unavailable")
    def test_real_powershell_geometry_intersection_rounds_inward_and_rejects_empty(self) -> None:
        command = shutil.which("powershell") or shutil.which("pwsh")
        # Parse only the pure rectangle helper from the actual script; no native
        # window, UIA action, desktop capture or process is started.
        path = "'" + str(SCRIPT).replace("'", "''") + "'"
        probe = r"""
Add-Type -AssemblyName System.Drawing
$src = [IO.File]::ReadAllText(__PATH__)
$start = $src.IndexOf('function Get-F37PhysicalIntersection(')
$end = $src.IndexOf('function Invoke-F37ReaderScroll(', $start)
if ($start -lt 0 -or $end -le $start) { throw 'Missing geometry function' }
Invoke-Expression $src.Substring($start, $end - $start)
$a = [Drawing.Rectangle]::new(0, 0, 150, 100)
$b = [Drawing.Rectangle]::new(25, 15, 120, 60)
$c = [Drawing.Rectangle]::new(20, 5, 100, 90)
$result = Get-F37PhysicalIntersection @($a, $b, $c)
if ($result.X -ne 25 -or $result.Y -ne 15 -or
    $result.Width -ne 95 -or $result.Height -ne 60) { throw "Wrong ROI $result" }
$empty = Get-F37PhysicalIntersection @($a, [Drawing.Rectangle]::new(300,300,10,10))
if (-not $empty.IsEmpty) { throw "Accepted offscreen ROI $empty" }
Write-Output 'F37_NATIVE_RECT_INTERSECTION_TEST_OK'
""".replace("__PATH__", path)
        completed = subprocess.run(
            [command, "-NoProfile", "-NonInteractive", "-Command", probe],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("F37_NATIVE_RECT_INTERSECTION_TEST_OK", completed.stdout)


if __name__ == "__main__":
    unittest.main()
