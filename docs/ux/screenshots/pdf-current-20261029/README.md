# PR16 current-source PDF extracted-text native acceptance

Run: 2026-10-29, private Linux/Xvfb with pinned PDFium, same current-source native executable as the Data View receipt.

- Slint source SHA-256: `05b4d6f9e3ad032ab2cce3de0ff155d030f2a0473264029b89e39e5bbac41d70`
- Rust main source SHA-256: `d5efcdbb248bdf8fef221439d627455616fc666b2e2dcfef0b7d2973f40a3383`
- Binary SHA-256: `b78c3ab05db9545a2c7e13b0016284a91a561ea48b67d746b7c39dbe1071bc60`
- PDF fixture SHA-256: `c0f54e821f5ffcc06eb10ae4a165881251cd5cd5bb397d3fc101a33fe672fa52`
- Result: `scripts/ux/isolated-xvfb-pdf-extracted-text.sh` exit code **0**.

Verified exact page-1 text `First page unrelated text`, page-2 Find Next `Second page PDFium landmark`, real selectable Ctrl+A/C clipboard, read-only typing rejection, and clearing stale text when the PDF path changes. Screenshots: [page 1](01-page1.png), [page 2](02-page2.png), [stale text cleared](03-path-cleared.png).

Scope: this demonstrates read-only actual extraction, **not** persisted immutable PDF page records, glyph-level passage selection, or citation/AI provenance.
