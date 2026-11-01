# F44 synthetic evaluation technical receipt export

Source: `crates/researchweave-analysis/src/extraction_evaluation_export.rs` exports `evaluate_and_render_markdown(EvaluationRequest)`.

The wrapper first invokes the existing strict `evaluate` flow. It refuses non-synthetic requests, changed supplied frozen gold/prediction commitments, mismatched content SHA-256, declared held-out/training overlaps, invalid or out-of-bounds anchored spans, duplicate slots and other evaluator guards. It never trains a model, verifies independent gold custody or writes to disk/network.

After successful synthetic evaluation, the output contains a deterministic UTF-8 Markdown technical receipt with the report schema/ID, supplied synthetic predictor label, canonical evaluator provenance SHA-256, frozen input commitments, whole-cohort and field-level TP/FP/FN/TN/abstention, defined/undefined precision-recall and selective risk, and explicit synthetic/no-model-validation limitations. Unique field rows and byte output are bounded; Markdown/HTML-sensitive field text is escaped. Individual source excerpts, gold labels and predicted values are deliberately omitted. An additional SHA-256 of exact exported Markdown bytes is returned so a future host can verify the payload before any physical approved export.

The result is a data-minimized synthetic **technical fixture receipt**, not peer-reviewed evidence, real model performance, a calibration guarantee, an external preregistration, or a production evaluation dashboard. No on-disk export/UI is wired yet. The ledger remains **PARTIAL**.

Initial unit tests cover deterministic exact SHA, Unicode fixture, Markdown injection escaping, synthetic-only label, absence of source and individual values, analytically known 1-of-1 exact anchored result, and refusal of real/mutated-gold inputs. Native project-scoped adjudication and physical file-no-overwrite still require separate implementation and acceptance.
