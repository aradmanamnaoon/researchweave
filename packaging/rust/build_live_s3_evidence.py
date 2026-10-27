"""Build a non-secret live Liara acceptance record from the real test log."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from verify_live_s3_acceptance import PRODUCER, REQUIRED_STAGES, WORKFLOW_PATH


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--workflow-path", required=True)
    args = parser.parse_args()

    raw = args.log.read_bytes()
    text = raw.decode("utf-8")
    parsed = urlparse(args.endpoint)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host.lower().endswith(".liara.site"):
        raise SystemExit("live acceptance endpoint is not an HTTPS Liara hostname")
    if not re.fullmatch(r"[0-9a-f]{40}", args.head_sha):
        raise SystemExit("head SHA is invalid")
    if not args.run_id.isdigit() or args.run_attempt < 1:
        raise SystemExit("GitHub run provenance is invalid")
    if args.workflow_path != WORKFLOW_PATH:
        raise SystemExit("workflow path is not an approved live-S3 evidence producer")

    checks = {stage: True for stage in REQUIRED_STAGES}
    expected_lines = [f"LIVE_S3_STAGE_OK stage={stage}" for stage in REQUIRED_STAGES]
    expected_lines.append(f"LIVE_S3_ACCEPTANCE_OK provider=liara endpoint_host={host}")
    if text.splitlines() != expected_lines:
        raise SystemExit(
            "live acceptance log must contain only the ordered allowlisted success markers"
        )

    record = {
        "schema": 2,
        "status": "pass",
        "producer": PRODUCER,
        "provider": "liara",
        "provider_name": "Liara",
        "provider_country": "IR",
        "endpoint_host": host,
        "observed_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "head_sha": args.head_sha,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "workflow_path": args.workflow_path,
        "health": "live_checked",
        "checks": checks,
        "evidence_log_sha256": hashlib.sha256(raw).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"LIVE_S3_EVIDENCE_WRITTEN {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
