"""Catch unavailable Slint Theme members before expensive desktop link CI.

This guards a narrow source-level typo class; only a real Slint compile
establishes layout/component/type validity.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NativeThemeTokenContract(unittest.TestCase):
    def test_every_used_theme_member_is_defined_in_its_global_declaration(self) -> None:
        ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(
            encoding="utf-8"
        )
        declaration = ui.split("export global Theme {", 1)[1].split("\n}", 1)[0]
        members = set(re.findall(r"\bproperty\s*<[^>]+>\s*([a-z][\w-]*):", declaration))
        used = set(re.findall(r"\bTheme\.([a-z][\w-]*)", ui))
        self.assertGreater(len(members), 30)
        self.assertGreater(len(used), 20)
        self.assertEqual(used - members, set(), "Slint Theme property typo")
        self.assertIn("divider", members)
        self.assertNotIn("outline", used)


if __name__ == "__main__":
    unittest.main()
