"""Guard actual installed Windows UIA F44 synthetic receipt acceptance.

Static checks only; a real Windows installed-executable run must pass as well.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WindowsF44SyntheticReceiptContract(unittest.TestCase):
    def test_installed_win_uia_f44_positive_negative_and_zero_write(self) -> None:
        source = (
            ROOT / "crates/researchweave-desktop/tests/windows-uia-smoke.ps1"
        ).read_text(encoding="utf-8")
        for required in (
            "UIA_F44_SYNTHETIC_SHA_VERIFIED_REDACTED_NO_PROJECT_WRITE_OK",
            "UIA_F44_MALFORMED_FIXTURE_FAIL_CLOSED_NO_PROJECT_WRITE_OK",
            "'Toggle offline synthetic extraction evaluation fixture panel'",
            "'Preview strict synthetic extraction evaluation with no network or project write'",
            "'Copyable SHA verified redacted synthetic extraction evaluation receipt'",
            "[System.Security.Cryptography.SHA256]::Create()",
            "if ($f44ObservedHash -cne $f44Hash -or",
            "Assert-F14Unchanged $f44Before",
            "'No valid SHA-verified synthetic evaluation receipt for this fixture.'",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
