"""Guard installed Linux project-A reopen identity and bounded QA teardown.

Static source checks are not installed GUI evidence. The hosted AT-SPI suite
must still observe the real project-open receipt, saved note and checklist.
"""

from __future__ import annotations

from pathlib import Path
import unittest


QA = Path(__file__).with_name("mission-atspi-navigation.py")
HOST = Path(__file__).with_name("mission-xvfb-ui-smoke.sh")


class ReopenAndXvfbContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qa = QA.read_text(encoding="utf-8")
        cls.host = HOST.read_text(encoding="utf-8")
        cls.reopen = cls.qa.split('edit_text(app, "Project path", str(original_project))', 1)[1]

    def test_native_project_identity_precedes_card_acceptance(self) -> None:
        self.assertIn('activate_bounded_control(app, "Open project", down=True)', self.reopen)
        self.assertIn('nodes_named(app, "Status: Project opened")', self.reopen)
        self.assertIn('nodes_named(app, f"Project · r{original_revision}")', self.reopen)
        self.assertIn('SELECT revision FROM project', self.reopen)
        self.assertLess(
            self.reopen.index("PROJECT_A_NATIVE_REOPEN_REVISION_VERIFIED"),
            self.reopen.index('activate(app, "Synthesize activity")'),
        )
        self.assertIn('audit(app, "project-a-reopen-not-confirmed", output)', self.reopen)

    def test_card_still_requires_real_accessibility_and_checklist(self) -> None:
        self.assertIn('nodes_named(app, "Edit quick note Synthetic MRI memo")', self.reopen)
        self.assertIn(
            'reveal_bounded_control(app, "Edit quick note Synthetic MRI memo", down=True)',
            self.reopen,
        )
        self.assertIn('audit(app, "project-a-quick-note-reopen-missing", output)', self.reopen)
        self.assertIn('nodes_named(app, "Mark unfinished Research MRI note', self.reopen)
        self.assertIn("QUICK_NOTE_CHECKLIST_REOPEN_PERSISTENCE_OK", self.reopen)
        self.assertIn("QUICK_NOTE_PERSISTED_AFTER_REOPEN_OK", self.reopen)
        self.assertIn("time.monotonic() + 4.0", self.reopen)

    def test_disposable_xvfb_teardown_is_bounded_without_faking_success(self) -> None:
        self.assertIn("timeout --signal=TERM --kill-after=10s 5m", self.host)
        self.assertIn('kill -KILL "$pid"', self.host)
        self.assertIn('wait "$pid"', self.host)
        self.assertIn('wait "$watchdog"', self.host)
        self.assertIn('python3 "$probe"', self.host)
        self.assertIn('> "$output/atspi-navigation.txt" 2>&1', self.host)
        self.assertIn('probe_status=$?', self.host)
        self.assertIn('if (( probe_status != 0 )); then', self.host)
        self.assertIn('exit "$probe_status"', self.host)
        self.assertIn('set -euo pipefail', self.host)
        self.assertIn('ISOLATED_XVFB_TEST_DONE', self.host)


if __name__ == "__main__":
    unittest.main()
