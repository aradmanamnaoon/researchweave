"""F42 native lifecycle source contracts; installed GUI remains separate."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ResearchLifecycleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(encoding="utf-8")
        cls.main = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(encoding="utf-8")
        cls.backend = (ROOT / "crates/researchweave-project/src/guided_lifecycle.rs").read_text(encoding="utf-8")
        cls.handler = (ROOT / "crates/researchweave-project/src/handler.rs").read_text(encoding="utf-8")
        cls.atspi = (ROOT / "scripts/qa/mission-atspi-navigation.py").read_text(encoding="utf-8")

    def test_actual_source_bound_read_only_stages_and_ui_thread_boundary(self) -> None:
        self.assertIn("callback load-research-lifecycle();", self.ui)
        self.assertIn("Toggle source-verified research lifecycle navigator", self.ui)
        self.assertIn("Open research lifecycle stage ", self.ui)
        self.assertIn("app.on_load_research_lifecycle({", self.main)
        self.assertIn('"project.lifecycle_overview"', self.main)
        self.assertIn('"project.lifecycle_overview", Effect::Read', self.handler)
        self.assertIn("ui.get_lifecycle_request_id() != request", self.main)
        self.assertIn("reset_project_visible_state(ui: &MainWindow)", self.main)
        self.assertIn("root.page = stage.target-page;", self.ui)
        self.assertIn('"stage_presence_only":true', self.backend)
        self.assertIn('"scientific_completion_verified":false', self.backend)
        self.assertIn('"analysis_results_examined":false', self.backend)
        self.assertIn('"publishing_status_examined":false', self.backend)
        self.assertIn('"writes":0', self.backend)

    def test_native_private_project_action_checks_no_writes_and_real_navigation(self) -> None:
        self.assertIn(
            "F42_NATIVE_LIFECYCLE_SOURCE_BOUND_NAVIGATION_NO_COMPLETION_CLAIM_OK",
            self.atspi,
        )
        self.assertIn("f42_before = project_event_snapshot(original_project)", self.atspi)
        self.assertIn("project_event_snapshot(original_project) != f42_before", self.atspi)
        self.assertIn("does NOT mean research complete or scientifically validated", self.atspi)
        self.assertIn('nodes_named(app, "Preview protocol")', self.atspi)


if __name__ == "__main__":
    unittest.main()
