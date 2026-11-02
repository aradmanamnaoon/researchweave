"""Static fail-closed guard for F07 native opt-in workflow (not installed GUI QA)."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CrossrefNativeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.desktop = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.library = (ROOT / "crates/researchweave-library/src/lib.rs").read_text(encoding="utf-8")
        cls.backend = (ROOT / "crates/researchweave-library/src/crossref_doi.rs").read_text(encoding="utf-8")

    def test_no_implicit_network_on_navigation_or_input_edit(self) -> None:
        self.assertIn('callback preview-crossref-doi(string);', self.ui)
        self.assertIn('callback fetch-crossref-doi(string);', self.ui)
        self.assertIn('edited(text) => { root.invalidate-crossref-doi(); }', self.ui)
        self.assertIn('root.preview-crossref-doi(crossref-doi-entry.text);', self.ui)
        self.assertIn('root.fetch-crossref-doi(crossref-doi-entry.text);', self.ui)
        self.assertIn('enabled: root.reference-crossref-ready && !root.reference-crossref-busy;', self.ui)
        self.assertIn('network_requests":0', self.backend)
        self.assertIn('if preview {', self.backend)

    def test_external_effect_requires_one_use_approval_and_fresh_project(self) -> None:
        self.assertIn('("reference.crossref_doi_lookup", Effect::ExternalNetwork)', self.library)
        self.assertIn('library_preview_at(', self.desktop)
        self.assertIn('"reference_crossref"', self.desktop)
        self.assertIn('pending_crossref.borrow_mut().take();', self.desktop)
        self.assertIn('action.arguments.get("allow_network") == Some(&serde_json::Value::Bool(true))', self.desktop)
        self.assertIn('== Some(current_doi.as_str())', self.desktop)
        self.assertIn('library_execute_pending(&action, &path, &data_root)', self.desktop)
        self.assertIn('issue_approval(&command, 30, now)', self.desktop)
        self.assertIn('if active != previewed', self.desktop)
        self.assertIn('info.revision)', self.desktop)

    def test_background_result_is_project_generation_bound_and_no_apply(self) -> None:
        self.assertIn('std::thread::spawn(move || {', self.desktop)
        self.assertIn('slint::invoke_from_event_loop(move || {', self.desktop)
        self.assertIn('if ui.get_reference_crossref_request_id() != job_id', self.desktop)
        self.assertIn('ui.set_reference_crossref_request_id(ui.get_reference_crossref_request_id().wrapping_add(1));', self.desktop)
        self.assertIn('automatic_reference_update":false', self.backend)
        self.assertNotIn('callback apply-crossref', self.ui)
        self.assertIn('redirects(0)', self.backend)


if __name__ == "__main__":
    unittest.main()
