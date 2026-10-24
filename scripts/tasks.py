"""Portable task runner: uv run --extra dev python scripts/tasks.py [task]."""

import subprocess
import sys

TASKS = {
    "lint": [["ruff", "check", "."], ["ruff", "format", "--check", "."]],
    "format": [["ruff", "format", "."], ["ruff", "check", "--fix", "."]],
    "types": [["mypy", "src"]],
    "test": [["pytest", "-q", "--cov=researchweave", "--cov-report=term-missing"]],
    "skills": [[sys.executable, "scripts/validate_skills.py"]],
    "audit": [["pip-audit", "--local"]],
    "metrics": [
        [
            sys.executable,
            "scripts/measure_source.py",
            "--output",
            "docs/verification/CODE_METRICS.json",
        ]
    ],
    "readme": [[sys.executable, "scripts/verify_readme.py"]],
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        print(f"Usage: python scripts/tasks.py [{'|'.join(TASKS)}]")
        return 2
    for command in TASKS[sys.argv[1]]:
        code = subprocess.call(command)  # noqa: S603 - fixed commands from local TASKS only
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
