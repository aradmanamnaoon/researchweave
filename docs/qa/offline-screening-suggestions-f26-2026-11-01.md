# F26 — deterministic offline screening assistance (non-automated)

Date: 2026-11-01. Implementation: `crates/researchweave-ai/src/screening_suggestions.rs`.

## Exact supported scope

This is a **pure offline, suggest-only lexical baseline** for systematic-review title and abstract screening. The caller supplies a canonical project UUID, existing bounded review identifier, canonical review-record UUID, positive source revision, exact record title/abstract, source SHA-256 of the canonical field-structured source, and bounded PICO synonym groups. It computes case-normalized Unicode token/phrase overlap, surfaces matched phrases, a simple **lexical coverage percentage**, possible preceding negation and a qualitative manual-review priority. It returns deterministic SHA-256-bound output, original record identity and explicit limits.

The percentage is **not an inclusion probability, model confidence, calibration score or effect size**. The `InspectSooner` category is an optional queue priority for human attention, **never a screening decision**. Missing abstracts, detected negation or weak overlap abstain from prioritization. Every input and output requires manual screening. An unrecognized synonym, negated phrase, case report, non-English morphology, study-design mismatch or implicit concept can yield a false negative or false priority; no automatic exclusion exists. The tool performs **zero external requests, no trained-model inference, no project database writes and no retrieval**. The generic module cannot itself verify a supplied UUID is actually owned by a project or that text was fetched from immutable project records; it sets `project_database_verified=false` until the trusted host wires an independently scoped source read.

## Reproducibility and adversarial cases

The implementation has strict serde DTO schemas and bounded inputs (title ≤512 Unicode scalars, abstract ≤12,000, maximum 12 alternatives per category and 48 total, 96 scalars/term, review ID ≤128 UTF-8 bytes, no invalid controls or bidi spoofing). It rejects invalid/noncanonical project/record UUIDs, unsafe review IDs, zero source revision and a supplied source SHA that disagrees with exact structured original text. Terms are never evaluated as commands or natural-language instructions; `ignore all previous instructions` inside the abstract is just data. Negation is a conservative lexical warning, not logical inference. The source and output SHA-256 digests are stable without timestamps or network state.

The scoped Rust unit tests cover multilingual Persian/Unicode matches, exact title/abstract digest recheck, source tampering, malformed UUID, long text, invalid concepts, negation, missing abstract, prompt injection as untrusted text, deterministic outputs, and three explicitly synthetic labeled examples. Synthetic evaluation reports actual fixture counts, missed-priority labeled includes and false-priority labeled excludes; it **does not** report real-world recall, precision, or validated model performance and always records zero automatic exclusions. Any future empirical benchmark must use independent human-reviewed eligibility labels, preregistered threshold/evaluation protocol, temporal or topic held-out data, and a measured false-negative screening safety review.

Run in a low-resource Rust workspace with existing shared cache (do not create another build cache on D):

```powershell
$env:CARGO_TARGET_DIR='C:\rw-ux-acceptance-build'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_BUILD_JOBS='1'
cargo test --offline --locked -p researchweave-ai screening_suggestions -j 1
cargo clippy --offline --locked -p researchweave-ai --all-targets --all-features -j 1 -- -D warnings
cargo fmt --all -- --check
git diff --check
```

## Explicitly unfinished for F26 release acceptance

The feature remains **PARTIAL**: a trusted desktop host must read immutable review records, establish actual project/source ownership, route a visible user-facing review workbench, preserve double-blind reviewer boundaries, provide visible explanation/override and full human vote audit, and verify real provider/model suggestions against a separately labeled corpus if any AI model is added. None of those integration or real GUI acceptance claims follows from this pure helper's source tests. No record may be rejected, excluded, published, or silently written on the basis of this heuristic.
