"""Headless entry point over the same integrated application services."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from researchweave.app.composition import build_services
from researchweave.app.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchweave-cli")
    parser.add_argument("--data-dir", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Report integrated local subsystem health")
    subparsers.add_parser("capabilities", help="List registered typed operations")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.data_dir or load_config().data_directory
    services = build_services(root)
    try:
        payload = services.health() if args.command == "health" else services.bus.capabilities()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    finally:
        services.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
