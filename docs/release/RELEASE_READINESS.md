# Local release-readiness evidence

This document is the local, no-push release handoff for the current ResearchWeave `main` checkout.
It records observed evidence only. Remote publication, tags, package upload, and GitHub release creation
are intentionally outside this mission.

## Repository map and UI-core guardrails

| Area | Purpose | Release treatment |
|---|---|---|
| `src/researchweave/evidence` | Research/evidence/project domain | Core product source; preserve data/provenance semantics |
| `src/researchweave/analysis` | Scientific/statistical analysis | Core product source; preserve reproducibility/oracle tests |
| `src/researchweave/ai` | Optional provider/retrieval/agent layer | Optional overlay; no mandatory provider/account/model |
| `src/researchweave/ui` | PyQt6 desktop workflow | Preserve phase navigation, project mental model, task-specific screens |
| `src/researchweave/app` | Composition, CLI, desktop gateways | Trusted boundary for approval/runtime integration |
| `tests` | Unit/integration/UI/release regressions | Required for release gate |
| `docs` | User, integration, security, verification evidence | Public release documentation |
| `assets` | Original branding and deterministic screenshots | Public assets with manifest/hash evidence |
| `.agents/skills` | Repository-local agent guidance | 27 validated skills; provenance retained |
| `.local-audit`, `prompts` | Private/local mission evidence and instructions | Explicitly ignored; never stage for release |

UI-core identity preserved by the transformation: local-first research workspace, research-phase
navigation, dedicated evidence/data/analysis/review/export screens, restrained editorial visual
system, project-scoped state, explicit approvals, and progressive disclosure. The AI continuation
uses the existing Agent and Providers pages instead of replacing that shell.

## Implementation status

- Provider-agnostic model profiles support local OpenAI-compatible servers and hosted endpoints
  without storing credential values.
- Agent loop supports native tool calls, strict JSON fallback, real streaming, bounded iteration,
  and exact approval for non-read tools.
- Project-scoped conversations survive restart and reuse the existing evidence retrieval index.
- Agent page now contains an embedded project assistant; Providers configures the actual runtime
  policy/profile rather than cosmetic metadata.
- Existing `DurableAgentRuntime` and `LongTaskOrchestrator` were retained; a redundant orchestration
  subsystem was intentionally not added.

## Manual/native QA ledger

Observed on Windows using the real PyQt6 application window and an isolated temporary data root:

| Check | Result |
|---|---|
| Launch packaged/development desktop shell | Pass |
| Create/open deterministic synthetic project | Pass |
| Save local OpenAI-compatible model profile | Pass |
| Restart and reload provider identifier/endpoint/model | Pass |
| Agent Send enabled with active local profile | Pass |
| Real streamed assistant response through loopback OpenAI-compatible fixture | Pass; SSE deltas rendered in Agent |
| Existing manual proposal workflow remains reachable below assistant section | Pass; scrolled into view and previewed read proposal |
| Nonexistent loopback model endpoint | Safe failure: `Assistant: Provider connection failed`; no crash |
| Failed-turn user message persisted | Pass; conversation row observed in SQLite |
| Restart restores assistant history | Pass; prompt visible in Agent transcript |
| Switch Providers to manual mode | Pass; active model becomes `None` |
| Agent Send disabled with no active model | Pass |

No API key was used and no local model was downloaded for this validation.

## Defect log

| Defect | Severity | Fix / retest |
|---|---|---|
| Conversation SQLite connections remained open on Windows because transaction context managers do not close connections | Release blocker | Added explicit per-operation connection context manager with `finally: close()`; exact journey retested and full suite rerun green |
| Desktop shell assumed direct `UIFacade.ai_backend`; production receives `DesktopCommandGateway` | High integration regression | Gateway now exposes typed backend property; UI/composition regressions pass |
| Provider UI previously stored metadata without configuring runtime policy/model selection | Functional gap | Providers now validates/persists/activates real model profiles and respects offline/egress policy |

No known critical/high local blocker remains after the final validation below. External
interoperability and research-duration evidence are listed under limitations rather than hidden.

## Automated validation

- `ruff format --check .`: **395 files already formatted**.
- `ruff check .`: **pass**.
- `mypy src`: **156 source files, 0 issues**.
- `pytest -q`: **729 passed, 10 skipped, 3 warnings**.
- `git diff --check`: **pass**; existing Windows LF→CRLF warning for `tests/ui/test_smoke.py` only.
- skills validator: **27 repository skills valid**.
- broader mission capability inventory: **67 no-login/no-key capabilities observed as available
  during the mission**; mission-only UI automation packages were removed by the final locked sync; see
  [`../DEVELOPER_CAPABILITIES.md`](../DEVELOPER_CAPABILITIES.md).
- current source metric: **51,222 substantive Python SLOC across 156 files**.
- `pip-audit --local`: **no known vulnerabilities**; local `researchweave` package is skipped
  because it is not a PyPI distribution.
- final post-build filesystem disposition audit: **27,211 files** = 616 `KEEP_PUBLIC`, 7,025
  `DELETE_GENERATED`, 19,570 `IGNORE_LOCAL`; no public candidate requires quarantine/removal.
  The increase in generated files is the expected ignored PyInstaller `build/`/`dist/` output from the
  final portable-package rebuild.
- fresh secret scan across all tracked + intended untracked public candidates: **338 findings in 27
  files**, all within the already-reviewed synthetic fixture/hash/scanner-output categories; no new
  AI/runtime source file produced a secret candidate.
- final Windows portable rebuild: **170,209,243 bytes**, SHA-256
  `639D7F98FE42F0CA212066763718B70014DEA54493FDBB7FDDB9C681AA38630C`; extracted executable
  startup and user-data-retention smoke tests both passed.
- reachable Git history scan: **194 commits / 652 historical paths / 0 high-confidence secret hits**.

## Release checklist

| Gate | Status | Evidence / limitation |
|---|---|---|
| Product launch/core workflows | Pass locally | Full suite + native Windows operation |
| AI overlay safety | Pass locally | No-key local configuration, exact approval architecture, safe failure path |
| Manual QA | Pass for exercised Windows paths | Native Providers/Agent/restart/error paths observed |
| Engineering | Pass | Ruff, mypy, pytest, metrics, dependency audit |
| Repository hygiene | Pass locally | File disposition + history scans; `.gitignore` protects local/private/generated classes |
| README/screenshots | Pass after current refresh | Deterministic screenshot set and manifest; README link validator required before handoff |
| Hosted provider/live connector interoperability | Not claimed | Requires opt-in user-owned endpoints/accounts |
| 120-minute active research log | **Not verified** | Reference artifacts exist, but retained evidence cannot prove active minutes; see research evidence |
| Remote publication | Pending at readiness snapshot | Final local gates are green; repository/tag/release publication follows this snapshot |

Because the master prompt makes the research-duration log a completion question, the repository
must **not** be described as satisfying every line of that prompt until the missing active-time log
is genuinely completed. This is an evidence limitation, not a known application defect.

## Release-notes draft

### ResearchWeave V2 — local-first integrated research workspace

This release candidate combines evidence management, scientific analysis, reproducible project
workflows, a redesigned PyQt6 desktop shell, and optional controlled AI assistance. The desktop
keeps its local-first workflow usable without accounts, API keys, network access, or model downloads.
AI model configuration now lives in Providers and project-scoped assistance is embedded in Agent,
with real streaming and explicit approval boundaries for non-read tools. The Windows release path,
screenshots, test suite, dependency audit, and native desktop workflows have been revalidated locally.

## Troubleshooting quick reference

- **No AI model selected:** open Providers; core ResearchWeave workflows remain fully usable.
- **Local model connection fails:** verify the local server is running and its OpenAI-compatible
  endpoint/model identifier matches the provider profile. ResearchWeave fails safely without
  switching to a remote provider.
- **Hosted model blocked:** desktop offline mode or missing egress acknowledgement intentionally
  prevents remote requests. Only the configured endpoint host is allowlisted.
- **Credential error:** configure an environment-variable **name** in Providers and provide its
  value outside ResearchWeave; plaintext credentials are not stored in `model-providers.json`.
- **Test cleanup fails on Windows:** ensure no older ResearchWeave process is still using the data
  directory. The conversation store itself now closes each per-operation connection explicitly.

## Security, dependency, and architecture references

- [`../security/THREAT_MODEL.md`](../security/THREAT_MODEL.md)
- [`../verification/SECRETS_REVIEW.md`](../verification/SECRETS_REVIEW.md)
- [`../verification/PIP_AUDIT.json`](../verification/PIP_AUDIT.json)
- [`../DEPENDENCY_LICENSES.md`](../DEPENDENCY_LICENSES.md)
- [`../../workstreams/v2/ai/API_CATALOG.md`](../../workstreams/v2/ai/API_CATALOG.md)
- [`../../README.md`](../../README.md)

## Final review commands

```powershell
git status --short --branch
git diff --check
git diff -- README.md docs workstreams/v2/ai src/researchweave tests
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src
uv run --extra dev pytest -q
uv run --extra dev --extra formats python scripts/tasks.py readme
```

At the time this readiness snapshot was written, no `git push`, remote tag, GitHub release, or package
publication had yet been performed. Those publication steps intentionally follow the final local gates.
