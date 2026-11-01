"""Offline fail-closed contracts for the manual pre-tag gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import bump_version

MODULE = Path(__file__).with_name("check_ready.py")
SPEC = importlib.util.spec_from_file_location("release_check_ready", MODULE)
assert SPEC is not None and SPEC.loader is not None
ready = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ready)


def job(name: str, result: str = "success") -> dict[str, str]:
    return {"name": name, "status": "completed", "conclusion": result}


def candidate_jobs() -> list[dict[str, str]]:
    return [
        job("security"), job("verify-complete"),
        *(job(f"native (runner, {platform})") for platform in ready.PLATFORMS),
    ]


def quality_jobs() -> list[dict[str, str]]:
    return [job(f"test ({platform})") for platform in ready.QUALITY]


class ReleasePreflightTests(unittest.TestCase):
    def test_all_45_fully_accepted_features_required_before_tag(self) -> None:
        def ledger(rows: list[str], root: Path) -> None:
            location = root / "docs/verification"
            location.mkdir(parents=True, exist_ok=True)
            (location / "FEATURE_EXPANSION.md").write_text(
                "# Feature acceptance\n\n| ID | Feature | Status | Evidence | Next |\n"
                "| --- | --- | --- | --- | --- |\n"
                + "\n".join(rows) + "\n",
                encoding="utf-8",
            )

        valid = [f"| F{i:02d} | Feature {i} | RELEASE_VERIFIED | Real validated evidence | Complete |"
                 for i in range(1, 46)]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger(valid, root)
            ready.check_feature_scope(root)
            for changed in ("PARTIAL", "IMPLEMENTED_TESTED", "VERIFIED_LOCAL", "MISSING_TARGET"):
                with self.subTest(unsafe_status=changed):
                    modified = valid.copy()
                    modified[39] = modified[39].replace("RELEASE_VERIFIED", changed)
                    ledger(modified, root)
                    with self.assertRaisesRegex(
                        ready.ReleaseBlocked, "not independently RELEASE_VERIFIED"
                    ):
                        ready.check_feature_scope(root)
            for broken in (valid[:-1], valid + [valid[-1]],
                           valid[:-1] + ["| F46 | New | RELEASE_VERIFIED | X | Complete |"]):
                with self.subTest(broken_rows=len(broken)):
                    ledger(broken, root)
                    with self.assertRaises(ready.ReleaseBlocked):
                        ready.check_feature_scope(root)
            ledger(valid, root)
            ready.check_feature_scope(root)
    def test_bump_version_is_scoped_and_monotonic(self) -> None:
        cargo = (
            '[workspace]\nmembers=[]\n[workspace.package]\n'
            'version = "0.2.0"\nedition = "2021"\n'
            '[workspace.dependencies]\nserde = { version = "0.2.0" }\n'
        )
        readme = "Current: v0.2.0; archive: v0.1.2"
        updated_cargo, updated_readme = bump_version.next_contents(
            cargo, readme, current="0.2.0", requested="0.2.1"
        )
        self.assertIn('[workspace.package]\nversion = "0.2.1"', updated_cargo)
        self.assertIn('serde = { version = "0.2.0" }', updated_cargo)
        self.assertEqual(updated_readme, "Current: v0.2.1; archive: v0.1.2")
        with self.assertRaises(bump_version.ReleaseBlocked):
            bump_version.next_contents(cargo, readme, current="0.2.0", requested="0.2.0")
        with self.assertRaises(bump_version.ReleaseBlocked):
            bump_version.next_contents(cargo, readme, current="0.2.0", requested="0.1.9")

    def test_strict_semver(self) -> None:
        self.assertEqual(ready.version_parts("0.2.1"), (0, 2, 1))
        for malformed in ("v0.2.1", "0.02.1", "0.2", "0.2.1rc1", "../0", "0.2.1\n"):
            with self.subTest(version=malformed):
                with self.assertRaises(ready.ReleaseBlocked):
                    ready.version_parts(malformed)

    def test_all_native_platforms_and_complete_required(self) -> None:
        ready.validate_native_jobs(candidate_jobs())
        for name in (j["name"] for j in candidate_jobs()):
            with self.subTest(missing=name):
                without = [j for j in candidate_jobs() if j["name"] != name]
                with self.assertRaises(ready.ReleaseBlocked):
                    ready.validate_native_jobs(without)
        with self.assertRaises(ready.ReleaseBlocked):
            ready.validate_native_jobs(candidate_jobs() + [job("native (runner, macos-arm64)")])

    def test_native_partial_failure_rejected(self) -> None:
        rows = candidate_jobs()
        rows[-1]["conclusion"] = "failure"
        with self.assertRaises(ready.ReleaseBlocked):
            ready.validate_native_jobs(rows)
        rows[-1]["conclusion"] = "success"
        rows[-1]["status"] = "in_progress"
        with self.assertRaises(ready.ReleaseBlocked):
            ready.validate_native_jobs(rows)

    def test_all_four_quality_runners_required(self) -> None:
        ready.validate_quality_jobs(quality_jobs())
        for platform in ready.QUALITY:
            with self.subTest(platform=platform):
                with self.assertRaises(ready.ReleaseBlocked):
                    ready.validate_quality_jobs(
                        [row for row in quality_jobs() if platform not in row["name"]]
                    )

    def test_reject_incomplete_or_wrong_source_runs(self) -> None:
        sha = "a" * 40
        base = {
            "head_sha": sha,
            "head_branch": "main",
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
        }
        native = {"id": 101, "name": "Rust native release candidate", **base}
        quality = {"id": 102, "name": "Rust quality", **base}
        runs = [native, quality]

        def fetch(path: str) -> object:
            if path.endswith("/actions/runs?per_page=100"):
                return {"workflow_runs": runs}
            if "/101/" in path:
                return {"total_count": 6, "jobs": candidate_jobs()}
            if "/102/" in path:
                return {"total_count": 4, "jobs": quality_jobs()}
            raise AssertionError(path)

        self.assertEqual(
            ready.check_hosted_acceptance(sha=sha, root=Path("."), fetch=fetch),
            (101, 102),
        )
        for change in (
            {"head_sha": "b" * 40}, {"head_branch": "mission/foo"},
            {"event": "pull_request"}, {"conclusion": "failure"},
            {"status": "in_progress"},
        ):
            with self.subTest(change=change):
                altered = dict(native, **change)
                runs[:] = [altered, quality]
                with self.assertRaises(ready.ReleaseBlocked):
                    ready.check_hosted_acceptance(sha=sha, root=Path("."), fetch=fetch)
        runs[:] = [native, quality]

        def incomplete(path: str) -> object:
            item = fetch(path)
            if "/101/" in path:
                return {"total_count": 7, "jobs": candidate_jobs()}
            return item

        with self.assertRaises(ready.ReleaseBlocked):
            ready.check_hosted_acceptance(sha=sha, root=Path("."), fetch=incomplete)


if __name__ == "__main__":
    unittest.main()
