"""Preview-specific relaxation must not affect stable or PR verification."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / ".github/workflows/rust-release-candidate.yml"
STABLE = ROOT / ".github/workflows/release.yml"
UNIX_PACKAGE = ROOT / "packaging/rust/package-unix.sh"


class PreviewReleaseGateTests(unittest.TestCase):
    def test_exception_requires_explicit_preview_dispatch(self):
        body = CANDIDATE.read_text(encoding="utf-8")
        self.assertIn("preview_incomplete_native_acceptance:", body)
        self.assertIn("default: false", body)
        self.assertIn("[[ \"$GITHUB_EVENT_NAME\" == 'workflow_dispatch' ]]", body)
        self.assertIn("[[ \"$GITHUB_REF\" == refs/heads/release/preview-* ]]", body)
        self.assertIn("needs: security", body)
        self.assertEqual(
            body.count("continue-on-error: ${{ inputs.preview_incomplete_native_acceptance == true }}"),
            3,
        )
        for label in (
            "Windows installed candidate UI Automation smoke",
            "macOS normal GUI launch, relaunch and native window acceptance",
            "Full isolated Linux scientific GUI interaction regression",
        ):
            self.assertIn(label, body)
        for label in (
            "Windows installed candidate command-line smoke",
            "Smoke actual macOS/Linux native packages",
            "Linux install, direct AppImage and AT-SPI acceptance",
            "Verify candidate files",
        ):
            self.assertIn(label, body)

    def test_stable_release_remains_strict_and_mac_dmg_verified(self):
        self.assertNotIn(
            "preview_incomplete_native_acceptance",
            STABLE.read_text(encoding="utf-8"),
        )
        script = UNIX_PACKAGE.read_text(encoding="utf-8")
        self.assertIn("for attempt in 1 2 3 4", script)
        self.assertIn('hdiutil verify "$candidate"', script)
        self.assertIn('mv "$dmg_verified" "$dmg_output"', script)
        self.assertIn('test -s "$dmg_output"', script)


if __name__ == "__main__":
    unittest.main()
