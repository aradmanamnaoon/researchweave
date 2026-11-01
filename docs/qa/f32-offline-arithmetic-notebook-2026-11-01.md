# F32 — bounded executable arithmetic cells (2026-11-01)

## Implemented slice

A deterministic **offline arithmetic-only execution runtime** is integrated into the project-scoped native Notebook workspace. This is a useful minimal executable cell vertical slice, **not** a Python/Jupyter/R kernel.

- `notebook.cell_preview` is a read-only operation: it validates a typed `cell:<canonical-uuid>`, expected cell revision, explicit `researchweave-arithmetic-v1` language, and expression (1–512 ASCII bytes); returns a finite numeric result with source digest and approval fingerprint. It cannot write projects, files or execute code.
- `notebook.cell_execute` is registered as an approval-required `Effect::LocalWrite`, requires the same preview digest plus an exact project revision, and appends a new immutable `notebook_entries` row under an isolated `cell:` prefix with a SHA-256 input/record receipt and hash-chained project event. A failed/stale/replayed request cannot silently overwrite a previous cell result.
- `notebook.cell_list` reads the latest saved revisions with conservative bounds, returning code and numeric results while refusing corrupt source digests or an unexpected runtime. The existing long-form notebook and quick-card records are not changed.
- The native Slint panel offers **Preview calculation → Record calculation** with explicit status, edit invalidation, New cell, saved-cell reload and current project binding. Project switching clears the execution panel and approval.

The language supports finite numeric literals, scientific notation, `+`, `-`, `*`, `/`, unary signs, parentheses, `sqrt()`, `ln()`, and `abs()`. The evaluator enforces operation/depth/magnitude limits, finite outputs, and refusal of unsupported syntax, division by zero, invalid function domains, identifiers, shell/Python constructs, and non-ASCII/code injection. It uses **no external process or interpreter**, no filesystem, network or FFI.

Additional data-integrity hardening: each saved cell's exact canonical code/result/runtime record now carries a deterministic `content_sha256` field; list/read recomputes it, verifies the source digest and deterministic result, and refuses nonfinite, unsupported, or altered persisted result values. A disposable-database negative test deliberately changes the most recent stored numeric result while preserving the old checksum and confirms that the native notebook handler refuses to load the tampered record. Hashes detect accidental/content modification and support project provenance; they are not cryptographically authenticated external authorship.

Saved-cell history pagination now avoids the previous native first-100-only truncation: the read-only list accepts a bounded offset and returns the exact total/`has_more` receipt; native controls expose Previous 100 / Next 100 with project-switch reset and fail-closed page/total validation. A disposable 105-cell unit fixture checks both pages and the out-of-range limit. This does not increase the maximum 500-cell project capacity or implement a general notebook kernel. Actual installed button navigation remains subject to the exact-source native CI acceptance gate.

## Verification

Two focused Rust unit tests of the real project service and expression grammar passed locally on a disposable project before GUI additions. The local native source-contract tests, Python syntax check and Rust formatting pass. The private Linux Xvfb/AT-SPI script now exercises a genuine user-entered expression, no-write preview, separately approved project event, actual immutable SQLite cell record and unsafe expression refusal. Both candidate/release workflows require exact three positive markers and fail if Notebook cannot be reached.

**Not yet proven:** exact-source full desktop Rust build, installed Windows/macOS/Linux GUI acceptance, million-cell/long-session performance, actual Python/R/Jupyter kernels, OS sandbox, arbitrary user code, cell dependency graph, run-all/interrupt/restart, dataset revision injection, or durable executable output media. This feature remains **PARTIAL**.

## Reproducible focused checks

```powershell
cargo test --offline --locked -p researchweave-evidence notebook_cells::tests -j 1
python -m unittest discover -s scripts/qa -p 'test_native_*.py' -q
cargo fmt --all -- --check
```

Never call this limited arithmetic runtime a Python sandbox, never use it as an execution loophole, and do not claim hosted GUI markers until the corresponding installed, exact-source log has actually passed.
