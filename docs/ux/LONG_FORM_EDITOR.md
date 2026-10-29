# Long-form writing: draft persistence, limits, and benchmark evidence

**Scope:** Rust journal implementation in `crates/researchweave-desktop/src/writing_autosave.rs`. This document assesses **local plain-text autosave** and synthetic manuscript lengths; it is not a Word-class editor claim, a paper-pagination claim, or evidence that the Slint UI passed typing/rendering tests.

## What the current implementation guarantees

| Mechanism | Observed source behavior | Limit / remaining risk |
|---|---|---|
| Project isolation | Journal filename is the SHA-256 digest of the project ID, stored under the host-local `writing-drafts/` directory | Files are plaintext on the current device, not encrypted at rest; access controls depend on the host OS and profile |
| Saved data | `Drafts` JSON stores notebook text, manuscript ID, section, citations, body, and two explicit dirty flags | The journal stores one current notebook and one current manuscript section, **not** a multi-page rich text tree |
| Size safety | JSON bytes are checked before writing and before parsing on reload; the reader now caps input to 256 KiB **plus one byte** before rejecting oversized data | **256 KiB per entire serialized draft record**; UTF-8 multibyte scripts, backslash/quote/newline JSON escaping, and other fields all count |
| Replacement | Writes a UUID-suffixed temporary file in the same directory, then renames/replaces the destination; uses Windows `ReplaceFileW` if the target exists | Replacement is atomic in normal local-filesystem conditions, but no `fsync`/directory sync or power-loss durability guarantee is implemented; an existing corrupt committed file is an error |
| Recovery | `load` returns the exact saved text and dirty flags; missing journals return an empty `Drafts` | Failed reads and corrupted/oversized journals return explicit errors rather than silently discarding text |
| Project flush | `main.rs` debounce is 800 ms; it uses the typed evidence router to persist notebook and manuscript sections, then checkpoints cleared flags | A failed/revision-conflicting flush leaves dirty work in the journal. A manuscript flush requires nonempty ID and section; missing metadata cannot be auto-flushed |

This is a bounded **recovery journal**. It is **not** a versioned document database, backup service, crash-consistent filesystem transaction, multi-user conflict merger, or substitute for exporting/backing up a manuscript.

## Deterministic synthetic long-form cases

Tests now generate five synthetic documents with **1, 5, 15, 30, and 50 labeled pages**. Each synthetic “page” is 25 lines of deliberate text with Persian, Arabic, Japanese, Latin, decomposed `e` + combining mark, joined emoji, quote and backslash escaping, and line breaks. The page markers are **test labels, not print layout**. There is no personal data, external document, model output, network request, or benchmark-specific third-party dependency.

The test matrix exercises:

1. **Save and reopen:** Repeat journal serialization/write and fresh disk read seven times per document; compare all fields and dirty flags, then verify SHA-256 of the UTF-8 body against the in-memory original.
2. **Edit cost proxy:** Clone the complete Rust `String` and insert a mixed-language edit near its middle; measure this operation seven times. This is a Rust-side copy/insert cost only, not Slint key-to-paint latency.
3. **Interrupted debounce/recovery:** Save a dirty edited draft, drop the in-memory draft (simulated app restart before routed save), read the journal and verify exact edit plus dirty flags. Simulate a later successful routed save by clearing those flags and saving again; verify reload. **No actual process is terminated; no full project router is invoked by this test.**
4. **Interruption between staging and replacement:** Leave a truncated, orphaned `.tmp` sibling alongside a previously committed journal; verify that a fresh `load` still returns the committed text, and a subsequent valid save succeeds. Explicit corruption of the committed file must fail rather than manufacture a clean document.
5. **Size and failed write handling:** Construct a serialized draft at exactly 262,144 bytes, verify save/reopen, reject a one-byte-larger draft without overwriting the last good file, reject oversized input (including a 1 MiB adversarial file) on bounded load, and reject replacement of a directory without leaking an additional UUID temporary file.

### How to reproduce on a build machine

```powershell
cargo test --locked -p researchweave-desktop writing_autosave::tests -- --nocapture
cargo fmt --all -- --check
cargo clippy --locked -p researchweave-desktop --all-targets --all-features -- -D warnings
```

The benchmark test emits `WRITING_BENCH_CSV` rows with pages, Unicode character count, serialized JSON bytes, median microseconds for journal save/reopen/Rust copy+insert (seven samples), and one interrupted-recovery elapsed time. Measurements are **diagnostic**, machine/drive/cache dependent, and have no pass/fail time thresholds. Integrity assertions, size checks and error-handling assertions are deterministic. Avoid treating the median of seven quick operations as a reproducible production latency estimate.

## Measurements and evidence

**Observed Windows run (29 October 2026, Rust 1.99.1, debug-test profile, temporary files on C:)**:

`cargo test --locked -p researchweave-desktop writing_autosave::tests -- --nocapture` — **5 passed, 0 failed; 35 other desktop tests filtered**, on **both** runs (first compile 4m 11s and tests 0.33s; final recompile 51.07s and tests 0.35s). The table is from the final source run.

| Synthetic pages | Body Unicode scalar values | Serialized JSON bytes | Save median (µs) | Reopen median (µs) | Rust copy + middle insert median (µs) | Dirty edit journal save + recovery read (µs) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2,455 | 3,917 | 4,931 | 102 | 3 | 2,209 |
| 5 | 12,275 | 18,645 | 2,564 | 196 | 6 | 14,406 |
| 15 | 36,825 | 55,465 | 3,202 | 387 | 15 | 4,611 |
| 30 | 73,650 | 110,695 | 3,596 | 651 | 51 | 10,475 |
| 50 | 122,750 | 184,335 | 7,574 | 1,184 | 82 | 14,342 |

**How to interpret:** The 50-page synthetic JSON occupies 184,335 / 262,144 bytes (approximately **70.3%** of the allowed journal). All five sizes passed lossless UTF-8 round-trip and dirty recovery assertions; the exactly-at-limit and one-byte-over cases also passed. Save timings are **not monotonically increasing** (the 1-page median was slower than 5-page), consistent with OS/file cache and scheduling noise; this is not evidence of a sudden size-independent optimization. Measured middle insertion excludes cursor search, JSON serialization, Slint layout, paint, accessibility, native IME, and full project-router persistence. Single-shot recovery timing is not a median; notably it varied from 3.2 ms to 14.4 ms for the 5-page case between the two runs. No performance threshold was inferred or enforced from this run.

**Additional validation:** Strict targeted Clippy `cargo clippy --locked -p researchweave-desktop --all-targets --all-features -- -D warnings` **passed** (1m 53s). `rustfmt --check --edition 2021 crates/researchweave-desktop/src/writing_autosave.rs`, the edited file's `git diff --check`, and the final **repository-wide** `cargo fmt --all -- --check` all **passed**. An earlier format check failed while another worker was editing `main.rs`; that file was corrected independently and was never touched by this worker.

The **256 KiB limit is unchanged**. Larger manuscripts, escaped characters, or simultaneous lengthy notebook content may exceed it even when they contain fewer than 50 user-visible pages. New editor features, new screenshots, and native cross-platform acceptance are **not verified** by these tests. The original worktree had concurrent uncommitted GUI changes during compilation; the statistics above pertain to the Rust autosave unit tests, not a fresh release acceptance candidate.

## Word-class/editor acceptance not covered

The current Slint editor uses a **plain-text TextEdit**. This source-level test cannot establish document page layout, cursor responsiveness on a 50-page draft, multi-style rich text, headings/styles, footnotes, tables, comments, tracked changes, accessibility tree navigation, clipboard round trips, native IME composition, RTL caret positioning, or exact export fidelity. Those need actual GUI work and native UX testing at 100%, 150%, and 200% zoom on Windows, macOS (Intel/ARM), and Linux. Testing a 50-page journal proves only that a bounded synthetic text body can be serialized/reopened **when its entire JSON record fits within 256 KiB**.

The current UI also performs whole-document draft text transfers; after editing, it will serialize full JSON rather than incrementally saving a changed paragraph. A plausible next optimization is debounced partial editing or a streaming/segmented document representation, but raising the bound without measuring memory, latency, recovery semantics and corruption behavior would be unsafe.
