"""F34 native-source no-deposit contracts; installed GUI is verified separately."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NativeOpenScienceManifestContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.desktop = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.backend = (ROOT / "crates/researchweave-project/src/open_science_manifest.rs").read_text(encoding="utf-8")
        cls.handler = (ROOT / "crates/researchweave-project/src/handler.rs").read_text(encoding="utf-8")
        cls.atspi = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(encoding="utf-8")

    def test_real_local_read_and_async_stale_response_guards(self) -> None:
        self.assertIn("callback preview-open-science-manifest();", self.ui)
        self.assertIn("Preview integrity-verified redacted research-object manifest without publishing", self.ui)
        self.assertIn('app.on_preview_open_science_manifest({', self.desktop)
        self.assertIn('"project.open_science_manifest_preview"', self.desktop)
        self.assertIn('ui.get_open_science_request_id() != request', self.desktop)
        self.assertIn('active_project.borrow().as_ref() != Some(&project)', self.desktop)
        self.assertIn('project_read_safe(', self.desktop)

    def test_refuses_license_and_consent_approval_without_proof(self) -> None:
        for literal in (
            '"rights_verified":false',
            '"ethics_or_patient_consent_verified":false',
            '"redistribution_authorized":false',
            '"external_deposit_performed":false',
            '"osf_upload_performed":false',
            '"source_titles_and_paths_redacted":true',
            '"source_files_included":false',
            '"physical_file_written":false',
        ):
            self.assertIn(literal, self.backend)
        self.assertIn('("project.open_science_manifest_preview", Effect::Read)', self.handler)
        self.assertIn('hex::encode(Sha256::digest(encoded.as_bytes()))', self.desktop)
        self.assertNotIn('std::process::Command', self.backend)
        self.assertNotIn('reqwest::', self.backend)

    def test_native_xvfb_requires_actual_integrity_and_no_writes(self) -> None:
        self.assertIn(
            "F34_NATIVE_REDACTED_PROJECT_INVENTORY_INTEGRITY_NO_WRITE_NO_DEPOSIT_OK",
            self.atspi,
        )
        self.assertIn('f34_before = project_event_snapshot(original_project)', self.atspi)
        self.assertIn('project_event_snapshot(original_project) != f34_before', self.atspi)
        self.assertIn("publication and OSF deposit are NOT authorized", self.atspi)


if __name__ == "__main__":
    unittest.main()
