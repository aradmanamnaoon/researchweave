# Dependency license inventory

| Direct dependency | Purpose | Initial reported license | Review |
|---|---|---|---|
| PyQt6 | Qt desktop shell | GPL-3.0 free binding | GPL-3.0-only choice |
| pydantic | Typed configuration | MIT | Compatible |
| platformdirs | Platform paths | MIT | Compatible |
| hatchling | Build system | MIT | Build-only |
| pytest, pytest-cov | Tests | MIT | Dev-only |
| ruff | Lint/format | MIT | Dev-only |
| mypy | Type checking | MIT | Dev-only |
| pre-commit | Checks | MIT | Dev-only |
| PyYAML | Skill validator | MIT | Dev-only |

The canonical machine-readable inventory is generated with `pip-licenses` at
[`docs/verification/DEPENDENCY_LICENSES.json`](verification/DEPENDENCY_LICENSES.json), and the
CycloneDX environment SBOM is at [`docs/verification/SBOM.cdx.json`](verification/SBOM.cdx.json).
Resolved versions are recorded in `uv.lock`.

The current inventory includes GPL-3.0 PyQt6, LGPL Qt runtime components, BSD/MIT/Apache scientific
packages, and a small number of MPL/GPL/LGPL dependencies or build tools. A release reviewer must
check redistribution obligations for the exact bundled Windows/Linux/macOS artifacts. The existence
of this inventory is not a legal compatibility opinion.
