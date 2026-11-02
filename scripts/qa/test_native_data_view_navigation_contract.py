"""Prevent fuzzy AT-SPI navigation names in installed Linux data QA.

An accessible button's exact name is mandatory for the physical native-click
fallback. Substring matches can find a text node instead of that button.
These source checks do not substitute for a real Xvfb installed GUI run.
"""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DataViewNavigationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(
            encoding="utf-8"
        )
        cls.qa = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(
            encoding="utf-8"
        )

    def test_native_data_view_navigation_uses_exact_accessible_button_identity(self) -> None:
        self.assertIn('accessible-label: "Data View workspace screen";', self.ui)
        self.assertEqual(
            self.qa.count('activate_bounded_control(app, "Data View workspace screen", down=False)'),
            4,
        )
        self.assertNotIn('activate(app, "Data View")', self.qa)
        self.assertNotIn('activate_bounded_control(app, "Data View", down=False)', self.qa)

    def test_no_fuzzy_button_success_or_database_import_substitute(self) -> None:
        self.assertIn('(node.name or "").casefold() == name.casefold()', self.qa)
        self.assertIn('reveal_bounded_control(app, accessible_name, down=down)', self.qa)
        self.assertIn('edit_text(app, "Analysis import path", str(fixture)', self.qa)
        self.assertIn('"import preview ready" in (node.name or "").casefold()', self.qa)
        self.assertIn('"Recently imported dataset identifier and immutable revision"', self.qa)


if __name__ == "__main__":
    unittest.main()
