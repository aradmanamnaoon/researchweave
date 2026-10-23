# Repository instructions

ResearchWeave is a GPL-3.0-only Python 3.12 + PyQt6 desktop research platform at bootstrap. Later the user will place `CODEX_MASTER_PROMPT.md` in this repository. Read that entire specification when present and implement it iteratively with reviewable, tested vertical slices; do not infer that planned features already work.

- Keep Qt in `app/` or `ui/`; scientific methods must stay usable independently from Qt widgets.
- Use type annotations and `src/` packaging. Preserve cross-platform behavior and UTF-8 paths.
- Design opt-in provider interfaces, permission-checked agent actions, versioned local data schemas and auditable research workflows.
- Respect private manuscripts, sensitive research datasets and credentials. Telemetry defaults to off; remote data transfer must be explicit.
- Never fabricate citations, research findings, statistics or benchmark results. Verify provenance and prevent leakage.
- Review relevant `.agents/skills/*/SKILL.md` before changes; these skill files contain guidance, not executable permissions.
- Install with `uv sync --extra dev`, run app via `uv run researchweave`; run lint/types/test/skills with `uv run --extra dev python scripts/tasks.py <name>`.
- Preserve unrelated work, do not modify global Codex configuration and never push or publish without authorization.
