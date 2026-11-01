# Native PDFium bounded render hardening (2026-11-01)

The native PDF Reader's `render_search_at` previously read the entire user-selected PDF directly with `std::fs::read`, unlike the bounded find-next operation. Malformed or oversized PDFs could allocate arbitrarily large input buffers before PDFium performed any checks.

The renderer now shares the single-open-handle bounded reader (`MAX_NATIVE_PDF_BYTES=128 MiB`) used for find-next. Input length is checked before reading and rechecked after the bounded read. Native PDFium is loaded **after** that bound is enforced, so oversized input fails closed even on hosts with no PDFium library installed.

Rendered PDF text is capped at 16 MiB per page. The generated four-channel RGBA bitmap enforces nonzero, checked width×height×4 arithmetic and an explicit 64 MiB limit, verifies stride and input pixel-buffer bounds before indexing, and rejects invalid/inconsistent native output without exposing raw buffers. PDFium's own render output cap remains enabled.

A focused test uses a disposable oversized sparse PDF and verifies rejection before native loading; existing real PDFium render, page navigation, and find-next tests remain intact. Source-contract tests ensure no direct unbounded path read has regressed. Full exact-source native desktop build and installed Windows/macOS/Linux render acceptance are **pending**.

This reduces input size and overflow risk, but it is not a PDF sandbox: native PDFium still executes its parser/render code and must remain pinned, reviewed and security-audited. Cancellation inside one native render call is not supported by this change, and no such claim is made.
