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

    def test_unsaved_title_page_reads_visible_native_preview_not_generated_text(self) -> None:
        source = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(
            encoding="utf-8"
        )
        title_page = source.split('title_page_before = project_event_snapshot(original_project)', 1)[1]
        title_page = title_page.split('F04_TITLE_PAGE_EXACT_SHA256_UNSAVED_NO_PROJECT_EVENTS_OK', 1)[0]
        self.assertIn(
            'reveal_bounded_control(app, "Copyable unsaved title page preview", down=True)',
            title_page,
        )
        self.assertIn(
            'title_page_preview = read_visible_field_keyboard(\n'
            '            app, "Copyable unsaved title page preview", force_clipboard=True',
            title_page,
        )
        self.assertNotIn(
            'read_field(app, "Copyable unsaved title page preview")', title_page
        )
        self.assertIn('expected_title_body not in title_page_preview', title_page)
        self.assertIn('receipt_match.group(1) != expected_title_hash', title_page)
        self.assertIn('project_event_snapshot(original_project) != title_page_before', title_page)


if __name__ == "__main__":
    unittest.main()
