from __future__ import annotations

import argparse
import re
from pathlib import Path


STAGES = (
    "connection",
    "encrypted_push",
    "conflict_preservation",
    "history",
    "encrypted_pull",
    "local_cleanup",
)


def validate(log_path: Path, expected_endpoint_host: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]+\.liara\.site", expected_endpoint_host):
        raise ValueError("expected endpoint host is not a Liara hostname")
    raw = log_path.read_bytes()
    if len(raw) > 32 * 1024:
        raise ValueError("live GUI evidence log is unexpectedly large")
    text = raw.decode("utf-8")
    forbidden = (
        "authorization:",
        "access_key",
        "secret_key",
        "session_token",
        "aws_access_key_id",
        "aws_secret_access_key",
    )
    lowered = text.lower()
    if any(token in lowered for token in forbidden):
        raise ValueError("live GUI evidence log contains credential-like material")
    expected = [f"LIVE_S3_GUI_STAGE_OK stage={stage}" for stage in STAGES]
    expected.append(
        f"LIVE_S3_GUI_ACCEPTANCE_OK provider=liara endpoint_host={expected_endpoint_host}"
    )
    if text.splitlines() != expected:
        raise ValueError(
            "live GUI evidence log must contain only the ordered allowlisted success markers"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--expected-endpoint-host", required=True)
    args = parser.parse_args()
    validate(args.log, args.expected_endpoint_host)
    print("LIVE_S3_GUI_EVIDENCE_OK")


if __name__ == "__main__":
    main()
