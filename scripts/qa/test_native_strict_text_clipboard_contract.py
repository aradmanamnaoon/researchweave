"""Protect fail-closed native editor value verification on private Xvfb.

Some Slint LineEdit controls lack the AT-SPI Text range interface even though
real keyboard entry succeeds. The strict fallback must select and read actual
native editor bytes, not downgrade a scientific-form assertion.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NativeStrictTextClipboardContract(unittest.TestCase):
    def test_strict_native_text_readback_requires_exact_real_clipboard_content(self) -> None:
        source = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"xclip", "-selection", "clipboard", "-i"', source)
        self.assertIn('"ctrl+a", "ctrl+c"', source)
        self.assertIn('if not allow_unreadable and value and not nonempty_mismatch', source)
        self.assertIn('read_visible_field_keyboard(app, name, force_clipboard=True)', source)
        self.assertIn('if actual == value:', source)
        self.assertIn('XVFB_NATIVE_CLIPBOARD_TEXT_READBACK_OK=', source)
        self.assertIn('raise RuntimeError(f"Text never appeared in the real app', source)
        self.assertIn('edit_text(app, "Manuscript find text", "Synthetic")', source)
        self.assertNotIn(
            'edit_text(app, "Manuscript find text", "Synthetic", allow_unreadable=True)',
            source,
        )


if __name__ == "__main__":
    unittest.main()
