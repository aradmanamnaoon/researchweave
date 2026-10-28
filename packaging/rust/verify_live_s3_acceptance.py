"""Verify provenance-bound, redacted live Liara acceptance evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


PRODUCER = "researchweave-live-s3-evidence-v2"
WORKFLOW_PATH = ".github/workflows/rust-live-iranian-s3-acceptance.yml"
REQUIRED_STAGES = (
    "connection",
    "conditional_write",
    "encrypted_push",
    "encrypted_pull",
    "second_device_restore",
    "conflict_preservation",
    "history",
    "cleanup",
)
TOP_LEVEL_KEYS = {
    "schema",
    "status",
    "producer",
    "provider",
    "provider_name",
    "provider_country",
    "endpoint_host",
    "observed_at_utc",
    "head_sha",
    "run_id",
    "run_attempt",
    "workflow_path",
    "health",
    "checks",
    "evidence_log_sha256",
}
FORBIDDEN_LOG_PATTERNS = (
    "aws_access_key_id",
    "aws_secret_access_key",
    "secret_access_key",
    "session_token=",
    "authorization:",
    "x-amz-security-token",
)

# Liara documents bucket-specific endpoints under liara.site; its older
# compatible S3 endpoint (storage.iran.liara.space) is also in active use.
# Never accept a generic S3 domain as proof of Iranian-provider acceptance.
LIARA_ENDPOINT_SUFFIXES = (".liara.site", ".liara.space")


def is_liara_endpoint_host(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(re.fullmatch(r"[A-Za-z0-9.-]+", value))
        and any(value.lower().endswith(suffix) for suffix in LIARA_ENDPOINT_SUFFIXES)
    )


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8-sig"), object_pairs_hook=_pairs_no_duplicates
    )
    if not isinstance(value, dict):
        raise ValueError("live S3 evidence must be a JSON object")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("observed_at_utc must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("observed_at_utc is not a valid RFC3339 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("observed_at_utc must be UTC")
    return parsed


def _verify_log(log_path: Path, data: dict[str, Any]) -> None:
    raw = log_path.read_bytes()
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise ValueError("live S3 evidence log is empty or exceeds 8 MiB")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != data["evidence_log_sha256"]:
        raise ValueError("live S3 evidence log SHA-256 mismatch")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("live S3 evidence log is not UTF-8") from exc
    lowered = text.lower()
    for pattern in FORBIDDEN_LOG_PATTERNS:
        if pattern in lowered:
            raise ValueError("live S3 evidence log contains forbidden credential material")
    expected_lines = [f"LIVE_S3_STAGE_OK stage={stage}" for stage in REQUIRED_STAGES]
    expected_lines.append(
        f"LIVE_S3_ACCEPTANCE_OK provider=liara endpoint_host={data['endpoint_host']}"
    )
    if text.splitlines() != expected_lines:
        raise ValueError(
            "live S3 evidence log must contain only the ordered allowlisted success markers"
        )


def verify(
    evidence_path: Path,
    log_path: Path,
    *,
    expected_head_sha: str,
    expected_run_id: str,
    expected_run_attempt: int,
    expected_workflow_path: str,
) -> None:
    data = _load_json(evidence_path)
    if set(data) != TOP_LEVEL_KEYS:
        missing = sorted(TOP_LEVEL_KEYS - set(data))
        extra = sorted(set(data) - TOP_LEVEL_KEYS)
        raise ValueError(f"unexpected live S3 evidence keys; missing={missing} extra={extra}")
    if type(data["schema"]) is not int or data["schema"] != 2:
        raise ValueError("unsupported live S3 evidence schema")
    if data["status"] != "pass" or data["health"] != "live_checked":
        raise ValueError("live S3 evidence does not record a completed live check")
    if data["producer"] != PRODUCER:
        raise ValueError("unexpected live S3 evidence producer")
    if data["provider"] != "liara" or data["provider_name"] != "Liara":
        raise ValueError("this release gate requires the verified Liara acceptance workflow")
    if data["provider_country"] != "IR":
        raise ValueError("provider_country must be IR")

    endpoint_host = data["endpoint_host"]
    if not is_liara_endpoint_host(endpoint_host):
        raise ValueError("endpoint_host is not an accepted Liara DNS hostname")

    observed = _parse_utc(data["observed_at_utc"])
    now = datetime.now(timezone.utc)
    if observed > now + timedelta(minutes=5) or now - observed > timedelta(days=7):
        raise ValueError("live S3 evidence is future-dated or older than seven days")

    if not re.fullmatch(r"[0-9a-f]{40}", expected_head_sha):
        raise ValueError("expected head SHA is invalid")
    if data["head_sha"] != expected_head_sha:
        raise ValueError("live S3 evidence head SHA does not match the release source")
    if not expected_run_id.isdigit() or data["run_id"] != expected_run_id:
        raise ValueError("live S3 evidence run ID mismatch")
    if type(data["run_attempt"]) is not int or data["run_attempt"] != expected_run_attempt:
        raise ValueError("live S3 evidence run attempt mismatch")
    if data["workflow_path"] != expected_workflow_path:
        raise ValueError("live S3 evidence workflow path mismatch")
    if expected_workflow_path != WORKFLOW_PATH:
        raise ValueError("live S3 evidence must come from the dedicated protected workflow")

    checks = data["checks"]
    if not isinstance(checks, dict) or set(checks) != set(REQUIRED_STAGES):
        raise ValueError("live S3 evidence checks are incomplete or unexpected")
    for stage in REQUIRED_STAGES:
        if checks[stage] is not True:
            raise ValueError(f"live S3 acceptance check did not pass: {stage}")

    digest = data["evidence_log_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("evidence_log_sha256 must be a lowercase SHA-256 digest")
    _verify_log(log_path, data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-run-attempt", required=True, type=int)
    parser.add_argument("--expected-workflow-path", required=True)
    args = parser.parse_args()
    try:
        verify(
            args.evidence,
            args.log,
            expected_head_sha=args.expected_head_sha,
            expected_run_id=args.expected_run_id,
            expected_run_attempt=args.expected_run_attempt,
            expected_workflow_path=args.expected_workflow_path,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Live Iranian S3 release gate rejected: {exc}") from exc
    print("LIVE_IRANIAN_S3_RELEASE_GATE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
