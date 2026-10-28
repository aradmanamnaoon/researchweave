"""Regression tests for real Liara endpoint variants in the release gate.

These synthetic markers exercise validation only. They are not live evidence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_live_s3_acceptance import is_liara_endpoint_host
from verify_live_s3_gui_acceptance import STAGES, validate


class LiaraEndpointValidationTests(unittest.TestCase):
    def test_documented_liara_endpoints_are_accepted(self) -> None:
        for host in (
            "storage.c2.liara.site",
            "storage.iran.liara.space",
            "STORAGE.IRAN.LIARA.SPACE",
        ):
            with self.subTest(host=host):
                self.assertTrue(is_liara_endpoint_host(host))

    def test_fake_or_malformed_hostnames_are_rejected(self) -> None:
        for host in (
            "storage.iran.liara.space.attacker.example",
            "storage.iran.liara.site.evil.org",
            "storage.iran.liara-space.example",
            "storage.iranliara.space",
            "liara.space",
            "storage.iran.liara.space:443",
            "storage.iran.liara.space/path",
            "storage.iran.liara.space?token=secret",
            "127.0.0.1",
            "",
            None,
            10,
        ):
            with self.subTest(host=host):
                self.assertFalse(is_liara_endpoint_host(host))

    def test_gui_sanitized_markers_accept_both_real_domains(self) -> None:
        for host in ("storage.c2.liara.site", "storage.iran.liara.space"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "synthetic-gui.log"
                markers = [f"LIVE_S3_GUI_STAGE_OK stage={stage}" for stage in STAGES]
                markers.append(
                    f"LIVE_S3_GUI_ACCEPTANCE_OK provider=liara endpoint_host={host}"
                )
                path.write_text("\n".join(markers) + "\n", encoding="utf-8")
                validate(path, host)
                with self.assertRaises(ValueError):
                    validate(path, f"{host}.attacker.example")


if __name__ == "__main__":
    unittest.main()
