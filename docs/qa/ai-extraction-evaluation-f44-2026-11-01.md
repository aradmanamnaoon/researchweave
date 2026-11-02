# F44 — deterministic synthetic extraction evaluation

**2026-11-01 | Independent worker-2 slice | Baseline:** `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`

## Scope, integration state and claim boundaries

New Rust file: `crates/researchweave-analysis/src/extraction_evaluation.rs`. No other crate source, `lib.rs`, UI, SQLite schema or Git history was changed. This is a **standalone, tested but not yet crate-registered** analysis primitive; the integration agent must deliberately add `mod extraction_evaluation;` and the appropriate public re-exports in `lib.rs` after reviewing the API. This task explicitly did **not** authorize those edits, so there is no product UI panel or operative production command yet.

The function **scores supplied, previously captured predictions** against supplied **synthetic manually authored gold labels**. It performs no model inference/training, remote calls, research data access or database writes. No measured values below are reported as real model performance, clinically/scientifically validated predictions, verified human adjudication, or reliable calibrated probabilities. The Rust report explicitly sets `synthetic_fixture_only=true`, `model_trained_or_validated=false` and `project_database_verified=false`.

## API and inputs

```rust
pub fn gold_commitment(gold: &[Gold]) -> Result<String, EvaluationError>;
pub fn prediction_commitment(predictions: &[Prediction]) -> Result<String, EvaluationError>;
pub fn evaluate(request: EvaluationRequest) -> Result<EvaluationReport, EvaluationError>;
```

- `EvaluationRequest`: bounded evaluation/predictor labels, `synthetic_fixture=true`, separately supplied frozen gold/prediction SHA-256 commitments, excluded training/tuning source IDs and hashes, immutable `Source` records, `Gold` labels, and `Prediction` decisions. Identical candidate sources in the test set or overlap with declared training/tuning sets cause explicit leakage failure.
- `Source`: unique ID, exact UTF-8 content and externally supplied SHA-256; evaluator recomputes the digest before scoring. Cumulative accepted source content <=16 MiB, <=10,000 sources.
- `Span`: half-open `[start_byte,end_byte)` UTF-8 source offsets, plus exact excerpt. `AnchoredValue`: extracted value literally contained in that excerpt. The whole span must match the immutable source exactly on valid UTF-8 boundaries. Value and **location** must match gold to count as TP; the same text at another offset counts as `WrongAnchor` with one FP and one FN.
- **Resource-hardening follow-on:** each anchored excerpt is capped at **4,096 UTF-8 bytes**, separately from the existing 2,000-byte value cap. Gold and prediction inputs each have an independent **24 MiB conservative commitment budget**, including a per-record 256-byte JSON overhead allowance and 6× worst-case expansion for JSON-escaped string bytes. Each side remains bounded by 50,000 slots; up to 50,000 compact slots are still accepted. `evaluate()` checks **source bytes, all gold sizes, and all prediction sizes before commitment hashing**. The public commitment helpers independently enforce the same relevant annotation budget. All counters use checked addition/multiplication and fail closed on overflow.
- `Gold`: unique source/field slot and `expected: Some(AnchoredValue)` or an explicit `None` (negative gold). Missing gold is not inferred as negative. `Prediction`: exactly one decision per source/field gold slot, one of `Extract { value, confidence }`, `NoValue { confidence }`, or `Abstain { reason }`. Missing, duplicate, unscored, or unknown slots fail closed; confidence is optional finite [0,1] for answered decisions only.
- `EvaluationReport`: aggregate and field-level `Counts`, error rows identifying source ID/field plus expected/predicted values, optional confidence diagnostics, coverage/risk threshold curve, two input commitments and deterministic `provenance_sha256`.

The commitments are independently computable SHA-256 hashes of domain-separated canonical JSON over sorted gold and prediction sets. The revised implementation sorts **borrowed references** rather than cloning every entire anchored record, and uses a byte-bounded streaming `serde_json::to_writer` SHA-256 sink instead of allocating an extra full canonical JSON string. A focused test checks that both commitment hashes match the earlier canonical `serde_json::to_vec` values exactly; their digest format has not changed. The separate provenance serialization is also streamed with a 64 MiB byte ceiling. These changes prevent duplicate excerpt allocation inside commitment code, but the host still must impose a raw request-body cap **before deserializing into `EvaluationRequest`**, since Rust cannot undo upstream allocations.

The commitments prevent unnoticed changes **relative to the given hashes**. They do **not** prove the hashes were frozen before gold disclosure, that human experts labeled the records, or that declared training/tuning exclusions are exhaustive: a trusted host must hold separate access, commit first, adjudicate blinded, and verify the complete training/tuning manifest externally. Arbitrary calls passing both labels and predictions do not prove blinding or prevent label contamination.

## Metric semantics

One scored unit is one explicitly labeled `(source_id, field)` slot:

| Gold / predictor | Exact-match accounting |
| --- | --- |
| Gold positive, same value and source span | TP |
| Gold positive, different value or valid but different source span | FP **and** FN; one incorrect answered slot |
| Gold negative, extracted any source-supported value | FP; one incorrect answered slot |
| Gold positive, `NoValue` | FN; one incorrect answered slot |
| Gold negative, `NoValue` | TN |
| Gold positive, `Abstain` | FN for **end-to-end** recall; abstained, not counted in answered risk |
| Gold negative, `Abstain` | Abstained, not counted as TN or answered |

`precision = TP/(TP+FP)`, `recall = TP/number_of_positive_gold_slots`, `coverage = answered/total`, and `selective_risk = incorrect_answered/answered`. Precision/recall/risk are **`None`, not fictitious 0 or 1**, where their denominators are zero. Abstention on positive gold decreases end-to-end recall; answered-only selective risk does not hide that missed coverage. All `Counts` include source/field slot cardinalities, FP/FN, TP/TN and abstentions; all `FieldError` entries are sorted deterministically by source/field.

When **every answered decision** has a numeric probability and **at least 20** such decisions exist, the engine computes five fixed-width confidence bins and an empirical ECE, plus selective risk/coverage at confidence thresholds `0, 0.5, 0.75, 0.9, 1`. Confidence always means the supplied estimate of **exact anchored slot correctness**; it is not inherently calibrated. Any missing answered confidence, or fewer than 20 answered slots, **suppresses calibration and threshold curves entirely** with a reason string. Twenty is only a smoke-reporting gate, **not** an adequacy threshold for statistical calibration.

## Executed independent fixture checks

An isolated temporary manifest under `C:\tmp\researchweave-f44-worker2-harness\Cargo.toml` references the new Rust source as a standalone Cargo test root, requiring only the repository's existing `serde`, `serde_json` and `sha2` dependencies. `CARGO_TARGET_DIR=C:\rw-ux-acceptance-build`, `CARGO_BUILD_JOBS=2`, `--offline`, no D-drive Cargo target. This validates compiled runtime behavior **without editing `lib.rs` or the project manifest**.

**Follow-on observed: 15 tests passed, 0 failed** in the same isolated C-cache harness; **focused Clippy `-D warnings` passed** after waiting for the shared C-cache build lock. The synthetic manually computed fixture has 6 labeled source/field slots: TP=1, FP=2, FN=2, TN=2, abstained=1, answered=5; precision and recall each 1/3, coverage 5/6, risk 2/5. This is a known-answer **unit-test fixture, not a model evaluation result**.

Adversarial tests exercise all-negative undefined recall/precision; all-abstain undefined risk; stable digests/report under input permutations; byte-tampered source and train/tune overlap by ID and digest; repeated identical source bytes with different IDs; fabricated spans, invalid UTF-8 byte offsets and unsupported extracted text; unknown, missing or duplicate gold/prediction slots; changed prediction after commitment; JSON field injection; non-finite/out-of-range confidence; **same value extracted from the wrong matching source location**; and minimum-sample five-bin/threshold behavior. No random inputs, clock-dependent comparisons or real data appear in the fixtures.

Five **additional** tests confirm (1) streaming SHA outputs are byte-for-byte equivalent to the earlier canonical JSON commitment, (2) a single 2 MiB forged gold or prediction excerpt is rejected even with misleading existing commitments, (3) **50,000** repeated 320-byte gold/prediction excerpts are rejected by the aggregate budget *before* commitment hashing, (4) exactly **50,000 compact slots** can still commit but **50,001** cannot, and (5) an over-16 MiB source plus arithmetic budget-overflow attempts fail closed before hashing. No test allocates a 50,000 × multi-megabyte repeated payload.

## Remaining acceptance gates

The prime agent should (1) review the typed API and intentionally register/re-export the module; (2) provide a trusted, versioned host mapping from persisted source revision/hash to exact field slots and independently captured prediction snapshots; (3) implement genuinely blinded human annotation and adjudication with a gold lock prior to model-score disclosure; (4) enforce complete train/dev/test leakage exclusions, including near-duplicate sources, shared entities and temporal leakage; (5) conduct representative held-out real evaluation with confidence intervals, prevalence, error analysis and threshold selection strictly on development data; (6) implement optional UI/report export with consent and leakage safeguards. Until then F44's **panel remains unimplemented** and no trained-model or acceptance accuracy claim is justified.

## Resource and verification limits

Only owned new files were edited; no Cargo build output was written to D, no DB was changed, and no commit/push occurred. Workspace-wide CI, analysis-crate registration, native GUI and hosted acceptance were **not run** because these would require out-of-scope changes or heavy builds. In-memory source strings/field error values are appropriate only for synthetic fixtures; the host must add authorization, redaction and safe export defaults before applying a future version to sensitive text. Tests demonstrate deterministic semantics and fail-closed validation, not generalizability to scientific extraction tasks.
