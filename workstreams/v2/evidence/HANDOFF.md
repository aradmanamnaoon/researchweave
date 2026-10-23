# Evidence worker handoff

Branch: `rebuild/v2-evidence`; base `af5c862d780d65c62a8c083fbfb64bd08a420092`.

Absolute worker worktree: `D:\coding\codex\researchweave-v2-evidence`.

Relative production path: `src/researchweave/evidence/`.

Canonical final source path: `D:\coding\codex\researchweave\src\researchweave\evidence\`.

All authored production source is tracked at `src/researchweave/evidence/` in branch `rebuild/v2-evidence`; it is expected to appear at `D:\coding\codex\researchweave\src\researchweave\evidence\` only after the final integration branch is successfully fast-forwarded onto the original `main` checkout.

Headless factory: `from researchweave.evidence import build_evidence_facade`. Exposes 39 operations and the machine-readable capabilities manifest. See `API_CATALOG.md` and `TEST_RESULTS.md`.

Tested offline journey: create → import three synthetic sources → anchor exact quote → flag mismatched quote → note → Markdown export → archive → verify → restore → reopen and audit. Review and manuscript tests cover independent blinded disagreement, adjudication, protocol amendments and citation warnings.

SOURCE_LAYOUT_VERIFIED must include tracked index paths, source SLOC, import/compile/test checks and local tip SHA. Unimplemented requirements and priority are in `NEXT_ACTION.md`. No push or merge was performed.

Verified 16 Python files and 2,106 meaningful source lines using `count_sloc.py`; compiler, Ruff, strict mypy and 10 observed behavior tests pass. Target remains 6,000 purposeful source lines; unresolved features are recorded in NEXT_ACTION.md.

Discovery increment: 17 modules, 2,432 meaningful SLOC, 19 tests passed, Ruff/mypy/compile passed. Public metadata requests require an explicitly injected transport and authorization; all provider contract tests used mock responses.
