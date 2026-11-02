# F37 — native PDF figure/table caption-anchor preview (2026-11-01)

## Implemented slice

The native PDF Reader now has a bounded read-only **Find figure/table captions** preview, using the existing pinned native PDFium runtime and the local PDF chosen by the user. The engine is in `crates/researchweave-desktop/src/pdf_figure_candidates.rs`.

The source is read once under a size budget, hashed with SHA-256, and its positioned PDF text layer scanned under explicit page/glyph/candidate budgets. Candidate labels such as `Figure 1`, `Fig. 2`, and `Table 3` have typed page index/number, optional page label, page rotation and caption glyph bounding rectangle in PDF points (not figure or table geometry), plus a bounded, **uncalibrated** labeling heuristic. The native panel displays a small preview, navigates directly to the original source page on click, and identifies the SHA-256 source provenance. Scans run on a worker thread and suppress stale responses when project, request or file selection changes.

Changing the PDF path manually or choosing another PDF in the native file dialog invalidates all previous candidate previews and their in-flight request IDs, preventing a stale caption control from silently navigating a different selected file. This is a UI/source routing guard, not an automatic proof that a file's bytes cannot be replaced externally at the same path.

This is **not actual figure image extraction, table cell extraction, OCR, or proven caption-to-visual association**. The pinned `firecrawl-pdfium 0.1.0` text API does not expose sufficient image/drawing-object enumeration for these claims. Every candidate is explicitly `content_extracted=false` and `human_confirmation_required=true`; no inferred figure/table content is silently persisted. Page coordinates reference caption glyphs only. A heuristic score is not calibrated statistical confidence.

## Verification and remaining gates

The new source includes five targeted Rust tests for candidate detection and geometry rejection, bounds, explicit provenance flags and an optional native PDFium+lopdf fixture when that runtime is available. Local Rust formatting and 19 native source-contract tests pass; full desktop compilation was deliberately stopped when C drive fell below the safety floor, so there is **no successful exact-source Rust compile or installed GUI test claim yet**.

Remaining: true figure/table object detection and extraction, line/column/cell structure, visual crop fidelity, verified caption-to-object binding, explicit native human confirm/reject storage and review history, accessibility/readback, blinded labeled scientific fixtures, and performance/portability acceptance across release platforms. F37 remains **PARTIAL**.
