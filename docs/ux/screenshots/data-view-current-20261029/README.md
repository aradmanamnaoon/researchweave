# PR16 current-source Data View private native acceptance

Run: 2026-10-29, private Linux/Xvfb/AT-SPI, real native executable. No visible Windows desktop.

- Slint source SHA-256: `05b4d6f9e3ad032ab2cce3de0ff155d030f2a0473264029b89e39e5bbac41d70`
- Rust main source SHA-256: `d5efcdbb248bdf8fef221439d627455616fc666b2e2dcfef0b7d2973f40a3383`
- Native Linux binary SHA-256: `b78c3ab05db9545a2c7e13b0016284a91a561ea48b67d746b7c39dbe1071bc60`
- Repository test script SHA-256: `2c9c71369bc6921b433b3ae12f9492fb4f6fbaad552605dcdb946d04f0aec4fa`
- Result: `scripts/ux/isolated-xvfb-dataset-grid.sh` exit code **0**.

At 1280×800 the native grid and full-page JSON inspector coexist in the first viewport. AT-SPI exposes all three fixture rows (A/1, A/3, B/5). The inspector has visible intersection [936, 648, 320, 162]; a real click and Ctrl+A/C yielded 1,072 UTF-8 bytes, with JSON SHA-256 `eb398d229bf48a3beba7cc8fe89ec89ababa27de515a51772cb8e5e55aee8f57`. Parsed values, offset=0, limit=25 and immutable revision matched the source dataset. A uniquely initialized clipboard sentinel was replaced, so the check cannot pass from a stale clipboard.

Files: [verified grid](01-grid.png), [inspector after copy](02-visible-inspector.png), [exact copied page JSON](page.json).

Scope: this is one three-row synthetic fixture, **not** a 54-row pagination test, complete UIA/Narrator acceptance, or final release signoff.
