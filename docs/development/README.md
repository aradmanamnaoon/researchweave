# Development

Use `uv sync --locked --extra dev` to reproduce locked package versions. Launch with `uv run researchweave`. Check lint, types, tests and skills using `uv run --extra dev python scripts/tasks.py {lint|types|test|skills}`. Windows development uses PowerShell 5.1; the task runner is platform-independent Python. macOS and Linux GUI smoke checks require their Qt platform dependencies and real host verification.
