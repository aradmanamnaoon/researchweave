#!/usr/bin/env python3
"""Fail-closed pre-tag check for the existing native GitHub release workflow.

This script makes NO Git, GitHub, project-data or release changes. It does not
replace installed native GUI acceptance, source review or scientific QA.
Python 3.11+, git, gh (authenticated) are required.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any, Callable


REPOSITORY = "aradmanamnaoon/researchweave"
PLATFORMS = ("windows-x64", "macos-arm64", "macos-x64", "linux-x64")
QUALITY = ("windows-2022", "ubuntu-24.04", "macos-15", "macos-15-intel")
ASSETS = (
    "windows-x64-setup.exe",
    "macos-arm64.dmg",
    "macos-x64.dmg",
    "linux-x86_64.AppImage",
    "linux-amd64.deb",
    "SHA256SUMS.txt",
)
FEATURE_IDS = tuple(f"F{index:02d}" for index in range(1, 46))
FEATURE_RELEASE_STATUS = "RELEASE_VERIFIED"


class ReleaseBlocked(RuntimeError):
    """A missing or unverifiable prerequisite prevents tagging."""


def version_parts(version: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ReleaseBlocked(f"Invalid three-component version: {version!r}")
    return tuple(int(item) for item in version.split("."))  # type: ignore[return-value]


def run_command(*argv: str, cwd: Path) -> str:
    process = subprocess.run(
        argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", check=False,
        timeout=75,
    )
    if process.returncode != 0:
        raise ReleaseBlocked(
            f"{' '.join(argv)} failed ({process.returncode}): {process.stderr.strip()[:500]}"
        )
    return process.stdout.strip()


def github_json(path: str, *, cwd: Path) -> Any:
    raw = run_command("gh", "api", path, cwd=cwd)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseBlocked(f"Invalid GitHub API response from {path}") from exc


def read_workspace_version(root: Path) -> str:
    with (root / "Cargo.toml").open("rb") as handle:
        version = tomllib.load(handle)["workspace"]["package"]["version"]
    if not isinstance(version, str):
        raise ReleaseBlocked("Workspace version is not text")
    return version


def check_workspace_lock(root: Path, version: str) -> None:
    with (root / "Cargo.lock").open("rb") as handle:
        packages = tomllib.load(handle)["package"]
    workspace = [
        item for item in packages
        if item["name"].startswith("researchweave-") and "source" not in item
    ]
    expected = {
        "researchweave-core", "researchweave-crypto", "researchweave-project",
        "researchweave-sync", "researchweave-cloud",
        "researchweave-desktop", "researchweave-analysis", "researchweave-evidence",
        "researchweave-ai", "researchweave-cli", "researchweave-library",
    }
    if {item["name"] for item in workspace} != expected:
        raise ReleaseBlocked("Cargo.lock contains an unexpected local workspace package set")
    if any(item["version"] != version for item in workspace):
        raise ReleaseBlocked("Cargo.lock is out of sync with Cargo.toml; regenerate and test")


def check_readme(root: Path, version: str) -> None:
    readme = (root / "README.md").read_text(encoding="utf-8")
    tag = f"v{version}"
    for suffix in ASSETS:
        name = "SHA256SUMS.txt" if suffix == "SHA256SUMS.txt" else f"ResearchWeave-{tag}-{suffix}"
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
        if url not in readme:
            raise ReleaseBlocked(f"README.md lacks exact release download link: {url}")


def check_feature_scope(root: Path) -> None:
    """Reject a release while any original expansion item lacks full acceptance.

    RELEASE_VERIFIED is deliberately distinct from VERIFIED_LOCAL (partial
    platform coverage) and IMPLEMENTED_TESTED (source/unit-only verification).
    A ledger flag is a necessary operator-reviewed scope receipt, not proof of
    installed GUI acceptance, which the exact-main hosted jobs verify later.
    """
    ledger = root / "docs/verification/FEATURE_EXPANSION.md"
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReleaseBlocked("F01–F45 release acceptance ledger missing") from error
    seen: dict[str, str] = {}
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) < 6 or not re.fullmatch(r"F[0-9]{2}", cells[1]):
            continue
        feature, status = cells[1], cells[3]
        if feature not in FEATURE_IDS:
            raise ReleaseBlocked(f"Unexpected feature ID in release ledger: {feature}")
        if feature in seen:
            raise ReleaseBlocked(f"Duplicate feature ID in release ledger: {feature}")
        seen[feature] = status
    if set(seen) != set(FEATURE_IDS):
        missing = sorted(set(FEATURE_IDS) - set(seen))
        raise ReleaseBlocked(
            f"F01–F45 release acceptance ledger incomplete: "
            f"{len(seen)} entries; missing {', '.join(missing[:10])}"
        )
    incomplete = [(feature, seen[feature]) for feature in FEATURE_IDS
                  if seen[feature] != FEATURE_RELEASE_STATUS]
    if incomplete:
        excerpt = ", ".join(f"{feature}={status}" for feature, status in incomplete[:12])
        raise ReleaseBlocked(
            f"{len(incomplete)} F01–F45 feature targets not independently "
            f"RELEASE_VERIFIED: {excerpt}. Do not tag or publish."
        )


def successful_job(jobs: list[dict[str, Any]], name: str) -> bool:
    return any(
        job.get("name") == name
        and job.get("status") == "completed"
        and job.get("conclusion") == "success"
        for job in jobs
    )


def validate_native_jobs(jobs: list[dict[str, Any]]) -> None:
    if not successful_job(jobs, "security"):
        raise ReleaseBlocked("Native candidate security job has not passed")
    if not successful_job(jobs, "verify-complete"):
        raise ReleaseBlocked("All-platform artifact verification job has not passed")
    for platform in PLATFORMS:
        matches = [
            job for job in jobs
            if job.get("name", "").startswith("native (")
            and platform in job.get("name", "")
            and job.get("status") == "completed"
            and job.get("conclusion") == "success"
        ]
        if len(matches) != 1:
            raise ReleaseBlocked(
                f"Missing exactly one successful installed native job for {platform}"
            )


def validate_quality_jobs(jobs: list[dict[str, Any]]) -> None:
    for runner in QUALITY:
        if not successful_job(jobs, f"test ({runner})"):
            raise ReleaseBlocked(f"Missing successful quality job for {runner}")


def complete_run(
    run: dict[str, Any], *, sha: str, workflow: str
) -> bool:
    return (
        run.get("name") == workflow
        and run.get("head_sha") == sha
        and run.get("head_branch") == "main"
        and run.get("event") == "workflow_dispatch"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
    )


def check_hosted_acceptance(
    *, sha: str, root: Path, fetch: Callable[[str], Any]
) -> tuple[int, int]:
    data = fetch(f"repos/{REPOSITORY}/actions/runs?per_page=100")
    matches = [
        item for item in data["workflow_runs"]
        if item.get("head_sha") == sha and item.get("head_branch") == "main"
        and item.get("event") == "workflow_dispatch"
    ]
    receipts: list[int] = []
    for name, validate in (
        ("Rust native release candidate", validate_native_jobs),
        ("Rust quality", validate_quality_jobs),
    ):
        candidates = sorted(
            (run for run in matches if complete_run(run, sha=sha, workflow=name)),
            key=lambda run: run["id"], reverse=True,
        )
        verified_id: int | None = None
        for candidate in candidates:
            job_data = fetch(
                f"repos/{REPOSITORY}/actions/runs/{candidate['id']}/jobs?per_page=100"
            )
            jobs = job_data.get("jobs", [])
            try:
                if job_data.get("total_count") != len(jobs):
                    raise ReleaseBlocked("Partial GitHub job enumeration")
                validate(jobs)
            except ReleaseBlocked:
                continue
            verified_id = candidate["id"]
            break
        if verified_id is None:
            raise ReleaseBlocked(
                f"No fully successful exact-main, workflow_dispatch {name} receipt "
                f"for {sha}. Trigger the workflow on main and inspect ALL jobs."
            )
        receipts.append(verified_id)
    return receipts[0], receipts[1]


def check_local_state(root: Path, version: str) -> str:
    if run_command("git", "branch", "--show-current", cwd=root) != "main":
        raise ReleaseBlocked("Checkout must be on main, not the mission branch or detached")
    if run_command("git", "status", "--porcelain", cwd=root):
        raise ReleaseBlocked("Working tree must be clean and committed")
    remote = run_command("git", "remote", "get-url", "origin", cwd=root)
    if not re.search(r"(github\.com[:/])aradmanamnaoon/researchweave(\.git)?$", remote):
        raise ReleaseBlocked("origin does not match the intended ResearchWeave repository")
    sha = run_command("git", "rev-parse", "HEAD", cwd=root)
    if not re.fullmatch("[0-9a-f]{40}", sha):
        raise ReleaseBlocked("Invalid local Git commit identity")
    if read_workspace_version(root) != version:
        raise ReleaseBlocked(
            f"Cargo.toml is not version {version}; bump workspace and lock before tagging"
        )
    check_workspace_lock(root, version)
    check_readme(root, version)
    return sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Target x.y.z (without v)")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        version_parts(args.version)
        check_feature_scope(root)
        sha = check_local_state(root, args.version)
        remote = github_json(
            f"repos/{REPOSITORY}/git/ref/heads/main", cwd=root
        )["object"]["sha"]
        if sha != remote:
            raise ReleaseBlocked("Local HEAD is not the exact current GitHub main tip")
        latest = github_json(f"repos/{REPOSITORY}/releases/latest", cwd=root)
        latest_tag = str(latest["tag_name"])
        if not latest_tag.startswith("v") or version_parts(args.version) <= version_parts(latest_tag[1:]):
            raise ReleaseBlocked(f"Target version must exceed latest public {latest_tag}")
        existing = run_command(
            "git", "ls-remote", "--tags", "origin", f"refs/tags/v{args.version}", cwd=root
        )
        if existing:
            raise ReleaseBlocked(f"Remote v{args.version} tag already exists")
        native_run, quality_run = check_hosted_acceptance(
            sha=sha, root=root, fetch=lambda path: github_json(path, cwd=root)
        )
    except (ReleaseBlocked, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"RELEASE BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"PRE-TAG VERIFIED: main={sha} latest={latest_tag}")
    print(f"Native run: https://github.com/{REPOSITORY}/actions/runs/{native_run}")
    print(f"Quality run: https://github.com/{REPOSITORY}/actions/runs/{quality_run}")
    print("Perform an independent product/feature acceptance and confirm the release notes.")
    print("The following commands trigger the existing five-platform GitHub release workflow:")
    print(f'git tag -a v{args.version} -m "ResearchWeave v{args.version}"')
    print(f"git push origin refs/tags/v{args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
