"""Static-only source contract for the optional offline Liara metadata UI.

This is NOT installed GUI QA, a Rust compiler test, or a live S3 test.
It blocks accidentally wiring the UI to credential/network/sync operations.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = (ROOT / "crates/researchweave-desktop/src/main.rs").read_text(
    encoding="utf-8"
)
UI = (ROOT / "crates/researchweave-desktop/ui/main.slint").read_text(
    encoding="utf-8"
)
CLOUD = (ROOT / "crates/researchweave-cloud/src/lib.rs").read_text(
    encoding="utf-8"
)


class LocalLiaraOptInSourceContract(unittest.TestCase):
    def test_router_exposes_only_local_profile_write(self) -> None:
        router = DESKTOP.split("fn cloud_profile_router(", 1)[1].split(
            "struct PendingCloudProfile", 1
        )[0]
        self.assertIn('"cloud.profile.configure"', router)
        self.assertIn("filter(|cap| matches!(cap.operation.as_str()", router)
        self.assertIn('.register("cloud", handler, allowed)', router)
        self.assertNotIn('router.register("cloud", handler, CloudOperationHandler::capabilities()', router)
        for forbidden in (
            '"cloud.credentials.store"',
            '"cloud.conditional.probe"',
            '"cloud.connection.verify"',
            '"cloud.sync.push"',
            '"cloud.sync.pull"',
        ):
            self.assertNotIn(forbidden, router)

    def test_preview_consent_binds_project_revision_inputs_and_digest(self) -> None:
        profile = DESKTOP.split("fn preview_local_liara_profile(", 1)[1].split(
            "fn refresh_recent_project_shortcuts(", 1
        )[0]
        for required in (
            "active_project_identity(project_path)",
            'Command::new(project_id, "cloud.profile.configure", arguments)',
            "command.expected_revision = Some(revision)",
            "preview.preview = true",
            ".approval_digest()",
            'confirmation != "SAVE LOCAL PROFILE"',
            "pending.project_path != current_project",
            "pending.command.arguments != actual",
            "pending.source_sha256",
            ".issue_approval(&pending.command, 30, now)",
            ".dispatch(&pending.command, Some(&approval), now)",
        ):
            self.assertIn(required, profile)
        self.assertNotIn('"cloud.conditional.probe"', profile)
        self.assertNotIn('"cloud.sync.push"', profile)

    def test_ui_requires_two_actions_and_never_collects_credentials(self) -> None:
        panel = UI.split("Optional Liara encrypted sync — offline profile setup", 1)[
            1
        ].split("Rectangle { vertical-stretch: 1; }", 1)[0]
        for required in (
            "preview-local-liara-profile(",
            "save-local-liara-profile(",
            "cloud-profile-pending",
            "SAVE LOCAL PROFILE",
            "No keys or passwords are requested here",
            "no network",
        ):
            self.assertIn(required.lower(), panel.lower())
        for forbidden in ("access-key", "secret-key", "passphrase", "conditional.probe", "sync.push"):
            self.assertNotIn(forbidden, panel.lower())

    def test_hardened_liara_host_and_cas_remain_separate(self) -> None:
        self.assertIn('host.ends_with(".liara.site")', CLOUD)
        self.assertIn('host.ends_with(".liara.space")', CLOUD)
        self.assertIn("fn liara_profile_refuses_non_liara_hosts_even_over_https()", CLOUD)
        self.assertIn("cloud.conditional.probe", CLOUD)
        self.assertIn("conditional_writes_verified", CLOUD)
        self.assertIn("read_bounded_s3_body", CLOUD)

    def test_cloud_and_desktop_regression_fixtures_use_supported_project_design(self) -> None:
        # Hosted 41383580556 reached the cloud unit suite after successful
        # check/Clippy, then failed before testing a substituted archive because
        # the synthetic project used the unsupported design value "test".
        project = (ROOT / "crates/researchweave-project/src/lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn('"observational"', project)
        self.assertIn('design: "observational".into()', CLOUD)
        self.assertIn('design: "observational".into()', DESKTOP)
        for code in (CLOUD, DESKTOP):
            self.assertNotIn('design: "test".into()', code)
            self.assertNotIn('design: "acceptance".into()', code)


if __name__ == "__main__":
    unittest.main()
