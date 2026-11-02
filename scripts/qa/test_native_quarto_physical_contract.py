"""Guard source-bound inert Quarto physical-export wiring and native QA.

Not evidence of completed installed UIA acceptance; that runs in Windows CI.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NativeQuartoPhysicalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = (
            ROOT / "crates/researchweave-desktop/src/manuscript_quarto_source.rs"
        ).read_text(encoding="utf-8")
        cls.export = (
            ROOT / "crates/researchweave-desktop/src/physical_export.rs"
        ).read_text(encoding="utf-8")
        cls.desktop = (
            ROOT / "crates/researchweave-desktop/src/main.rs"
        ).read_text(encoding="utf-8")
        cls.slint = (
            ROOT / "crates/researchweave-desktop/ui/main.slint"
        ).read_text(encoding="utf-8")
        cls.windows = (
            ROOT / "crates/researchweave-desktop/tests/windows-uia-smoke.ps1"
        ).read_text(encoding="utf-8")

    def test_real_persisted_source_body_is_hash_checked_before_ast_projection(self) -> None:
        for expected in (
            'result["status"] != "ok"',
            'data["manuscript_id"].as_str() != Some(expected_manuscript_id)',
            'data["count"].as_u64() != Some(sections.len() as u64)',
            'entry["body_sha256"]',
            'Sha256::digest(body.as_bytes())',
            'ManuscriptDocument::from_value(&document)',
            '"schema":DOCUMENT_SCHEMA',
            "author_title_page_not_available",
            "plain_section_text_not_rich_formatting",
            "citation_positions_not_available",
            "wrong_identity_sha_duplicates_and_citation_shape_fail_closed",
        ):
            self.assertIn(expected, self.adapter)

    def test_one_use_source_revision_and_no_overwrite_physical_export(self) -> None:
        for expected in (
            '"writing.quarto_source_preview" => Ok("qmd")',
            'if operation == "writing.quarto_source_preview" {',
            'arguments["source_project_revision"]',
            'current.revision != expected_revision',
            'data["renderer_invoked"] != false',
            'data["executable_cells_present"] != false',
            'data["citations_resolved"] != false',
            'data["qmd_sha256"].as_str() != Some(digest.as_str())',
            '"written_to_disk".into(), Value::Bool(false)',
            '"submission_performed".into(), Value::Bool(false)',
            "OpenOptions::new()",
            ".create_new(true)",
            "EXPORT_CONSUMED",
            "persisted_plain_manuscript_quarto_source_requires_one_use_no_overwrite_and_current_revision",
        ):
            self.assertIn(expected, self.export)

    def test_physical_save_reinspects_source_instead_of_trusting_supplied_ast(self) -> None:
        for expected in (
            'pub(super) struct SourceManifest',
            'pub(super) fn attest_source(',
            'let projection = from_inspect(inspected, manuscript_id)?;',
            'if projection.document != *supplied_document',
            'source_document_sha256',
            'citations_sha256',
            'canonical_source_manifest_rejects_forged_ast_and_stale_body_hash',
        ):
            self.assertIn(expected, self.adapter)
        for expected in (
            '"writing.inspect"',
            'manuscript_quarto_source::attest_source(',
            'if source_manifest != pending.source_manifest',
            'quarto_physical_export_refuses_forged_ast_and_in_place_source_tampering',
        ):
            self.assertIn(expected, self.export)

    def test_native_controls_read_real_inspection_and_save_only_after_approval(self) -> None:
        self.assertIn("mod manuscript_quarto_source;", self.desktop)
        self.assertIn("app.on_prepare_quarto_source({", self.desktop)
        self.assertIn('"writing.inspect"', self.desktop)
        self.assertIn('"source_project_revision":before.revision', self.desktop)
        self.assertIn('physical_export::prepare(', self.desktop)
        self.assertIn('"writing.quarto_source_preview"', self.desktop)
        self.assertIn("callback prepare-quarto-source(string);", self.slint)
        self.assertIn(
            "Prepare source bound inert Quarto document from persisted manuscript sections",
            self.slint,
        )
        self.assertIn(
            "Explicitly save verified Quarto source without overwriting files",
            self.slint,
        )

    def test_installed_windows_uia_must_save_real_qmd_and_rehash_without_mutation(self) -> None:
        for exact in (
            "UIA_F31_BOUND_INERT_QUARTO_PHYSICAL_QMD_SHA_NO_OVERWRITE_NO_PROJECT_WRITE_OK",
            'Get-FileHash -LiteralPath $f31Destination -Algorithm SHA256',
            'Assert-F14Unchanged $f31Before',
            "[System.IO.File]::ReadAllText($f31Destination)",
            "execute:`n  enabled: false",
            'text: "Save prepared .qmd";',
        ):
            # Button text appears in Slint; the action target in Windows UIA.
            self.assertIn(exact, self.slint + self.windows)
        marker = 'UIA_F31_BOUND_INERT_QUARTO_PHYSICAL_QMD_SHA_NO_OVERWRITE_NO_PROJECT_WRITE_OK'
        for workflow in (
            '.github/workflows/rust-release-candidate.yml',
            '.github/workflows/release.yml',
        ):
            self.assertIn(marker, (ROOT / workflow).read_text(encoding='utf-8'))


if __name__ == "__main__":
    unittest.main()
