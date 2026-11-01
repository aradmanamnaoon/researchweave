"""F41 GUI source contract; not a substitute for real installed AT-SPI QA."""

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeObsidianContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.main = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.evidence = (ROOT / "crates/researchweave-evidence/src/lib.rs").read_text(encoding="utf-8")
        cls.exchange = (ROOT / "crates/researchweave-evidence/src/obsidian_roundtrip.rs").read_text(encoding="utf-8")
        cls.atspi = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(encoding="utf-8")

    def test_explicit_three_phase_ui_and_edit_invalidates_approval(self) -> None:
        for callback in (
            "callback export-quick-note-obsidian(string);",
            "callback preview-quick-note-obsidian(string);",
            "callback import-quick-note-obsidian(string, string);",
        ):
            self.assertIn(callback, self.ui)
        for name in (
            "Export selected quick note as local Obsidian Markdown text",
            "Editable Obsidian Markdown note exchange",
            "Preview edited Obsidian Markdown without changing project",
            "Approve previewed Obsidian Markdown as a new immutable note revision",
        ):
            self.assertIn(name, self.ui)
        self.assertIn("root.quick-note-obsidian-approval = \"\";", self.ui)
        self.assertIn("enabled: root.quick-note-obsidian-approval != \"\";", self.ui)
        self.assertIn('root.quick-note-obsidian-status = "Selected quick note changed.', self.ui)
        self.assertIn('root.quick-note-obsidian-status = "Quick note selection cleared.', self.ui)

    def test_real_project_boundary_and_no_automatic_remote_or_database_fallback(self) -> None:
        for operation in (
            "knowledge.obsidian_export_note",
            "knowledge.obsidian_import_preview",
            "knowledge.obsidian_import",
        ):
            self.assertIn(operation, self.main)
            self.assertIn(operation, self.evidence)
        self.assertIn('"quick-note-obsidian"', self.main)
        self.assertIn('data["card_id"] != ui.get_quick_note_selected_id().as_str()', self.main)
        self.assertIn("evidence_preview_at(", self.main)
        self.assertIn("evidence_execute_pending(&pending, &project, &root)", self.main)
        self.assertIn("preview[\"data\"][\"writes\"] != 1", self.main)
        self.assertIn("hex::encode(Sha256::digest(markdown.as_bytes()))", self.main)
        self.assertRegex(self.exchange, r'mutate\(\s*store,\s*"knowledge\.obsidian_import"')
        self.assertIn('"source_json_sha256"', self.exchange)
        self.assertIn('"physical_file_written":false', self.exchange)
        self.assertNotIn("reqwest::", self.exchange)

    def test_actual_isolated_native_qa_retains_readback_and_persistence_checks(self) -> None:
        for marker in (
            "F41_NATIVE_MARKDOWN_SOURCE_SHA_READBACK_AND_EXPORT_NO_WRITE_OK",
            "F41_NATIVE_MARKDOWN_IMPORT_PREVIEW_NO_WRITE_OK",
            "F41_NATIVE_OBSIDIAN_APPROVED_APPEND_PRESERVES_HISTORY_AND_METADATA_OK",
        ):
            self.assertIn(marker, self.atspi)
        self.assertIn(
            '"Editable Obsidian Markdown note exchange", force_clipboard=True', self.atspi
        )
        self.assertIn('imported_event != ("knowledge.obsidian_import",)', self.atspi)
        self.assertIn("imported_card_rows[:-1] != prior_card_rows", self.atspi)


if __name__ == "__main__":
    unittest.main()
