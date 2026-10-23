"""Run all five synthetic analysis acceptance journeys and persist one trace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from researchweave.analysis.journeys import run_all_journeys, save_journey_trace


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    trace = run_all_journeys(args.workspace)
    save_journey_trace(trace, args.trace)
    print(json.dumps({"trace_hash": trace["trace_hash"], "journeys": sorted(trace["journeys"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
