# Statistics correctness / bounds wave — 2026-10-31

## Scope and reference

- Owned implementation: `crates/researchweave-analysis/src/power.rs` only. No external API, dependency, shared ledger, UI or Git edits.
- Existing scientific reference: `power::tests::matches_python_statsmodels_power_fixtures`, which contains previously recorded Python statsmodels t-power / sample-size goldens and a normal-approximation two-proportion fixture. Those pre-existing results are **reference values**, not freshly revalidated in this wave.
- Guidance reviewed: `.agents/skills/scientific-test-engineering/SKILL.md`, `.agents/skills/spss-compatible-statistics/SKILL.md`, `.agents/skills/research-methodology-integrity/SKILL.md`.

## Concrete defects corrected in source

1. Fixed-sample independent t and two-proportion power used a fractional group-2 size whenever `n_group1 * ratio` was non-integer (e.g. 40 with ratio 0.991 meant 39.64 participants). Required-N planning already rounded group 2 upward. Both fixed-N procedures now use `ceil(n_group1 * ratio)` with minimum two participants. Returned `n_group2`, effective `group_ratio`, and computed power therefore correspond to the same integer allocation. A group exceeding 10,000,000 or overflowing the representation fails with `ResourceLimit`.
2. Explicit malformed optional values (`alpha`, `ratio`, `target_power`, `confidence`, and t-test `alternative`) silently fell back to defaults. Present-but-invalid values now fail input validation; defaults remain for omitted fields.
3. Required-N searches could skip the final feasible sample-size interval. Doubling from 8,388,608 to 16,777,216 returned a budget error without evaluating possible solutions through 10,000,000. Search bounds now clamp to the last feasible integer `n_group1`; ratio-based maximum ensures group 2 also respects the 10-million planning cap. The same bounds prevent extreme allocation ratios from producing over-budget group counts or saturating casts.

## Deterministic regression coverage added (source present, execution blocked)

- `fixed_n_rounds_allocations_to_whole_participants_and_preserves_oracles`: fractional ratios round to integer allocation and retain the existing independent goldens for t-test power (`d=0.5`, 40/40, alpha .05, power 0.5981469011410998) and two-proportion normal-approximation power (`p1=.4`, `p2=.6`, 80/80, alpha .05, power 0.7214130648946949); verifies 80 with ratio 1.01 becomes 81 participants and increases power.
- `explicit_invalid_options_cannot_silently_become_defaults`: invalid supplied settings and ratios producing more than 10 million participants fail, including `1e308` in both required-N operations.
- `required_proportion_search_checks_last_feasible_group_before_budget_error`: normal-approximation result for `p1=.5`, `p2=.50065`, power target .8 must be in (8,388,608, 10,000,000] per group and minimal when checked against the fixed-N computation at `n-1`.

## Actual local validation and blocker

| Action | Result |
| --- | --- |
| `rustfmt --edition 2021 crates/researchweave-analysis/src/power.rs` | Exit 0; source formatted. |
| `git diff --check -- crates/researchweave-analysis/src/power.rs` | Exit 0; no whitespace errors. |
| `cargo test -p researchweave-analysis --lib power::tests --offline --locked -- --nocapture` using the existing `C:\Users\saba\AppData\Local\Temp\researchweave-mission-20261031-target` | **BLOCKED**, exit 101: Rust/LLVM `no space on device`, `os error 112`, while rebuilding existing cached Arrow / Parquet dependencies. No test case completed or passed in this run. |

The prime expressly requested **no more Cargo builds or tests** after the shared C: disk failure. This report is **source-only correctness reasoning plus formatting/whitespace verification**, and must not be promoted to a tested acceptance claim until targeted offline tests are successfully rerun under adequate storage conditions. Source inspection and existing goldens are not substitutes for execution.

## Remaining integration / UX considerations for prime

**Prime integration update (2026-10-31):** After the resource blocker was relieved by reusing the pre-existing Linux Cargo target, a full offline locked Linux workspace run completed **181 passing tests, zero failures**, including the new power tests. Strict all-target/all-feature workspace Clippy and the offline Linux desktop build also passed. The tested `power.rs` SHA-256 is `53f56bedfc0bc35bf466dfec1684d1cbc06777abe9d42b0387ad25312f7d4719`. This does not prove the power-planning GUI or native Windows/macOS package behavior.

- When a power-planning UI is surfaced, explain that the requested allocation ratio is rounded to integer group counts; show the actual `n_group1`, `n_group2`, and achieved ratio/power together. Reflect explicit invalid-input errors at the corresponding field rather than presenting a silently substituted default.
- Existing accessibility snapshot `docs/qa/mission-xvfb-20261031-r21/statistics-result-nodes.txt` shows prominent descriptives and a collapsible raw JSON result; the visible analysis selector lists descriptives/frequencies/correlation/Welch/linear-model only. Power planning is **not demonstrated** by this snapshot. A user-visible power workflow and its numerical disclosures need separate GUI evidence if part of acceptance.
- Existing limitations still require appropriate method labeling: prospective power assumes effect sizes and error models; the two-proportion routine is a normal approximation that may be unreliable for sparse events. This wave did not validate these statistical assumptions or the native GUI.
