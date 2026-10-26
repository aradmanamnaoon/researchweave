# PDFium runtime distribution — ResearchWeave

The Rust desktop's PDF rendering proof uses `firecrawl-pdfium = 0.1.0`
(MIT OR Apache-2.0), which dynamically loads the separate native PDFium
library. The native binary is **not** committed into the repository.

## Pinned Windows development asset

- Source: `https://github.com/firecrawl/pdfium-rs/releases/tag/native-v7988`
- PDFium version: `153.0.7988.0` (`chromium/7988`)
- Asset: `firecrawl-pdfium-win-x64.tgz` (3,764,191 bytes)
- SHA-256: `6f398552d8021a89078f64466557251a204999177287b876be49877eb8750d50`
- Fetch: `powershell -ExecutionPolicy Bypass -File packaging/rust/fetch-pdfium-win-x64.ps1`
- Output (not tracked): `target/pdfium/win-x64`

The archive SHA-256 was confirmed both by downloading the native-v7988 asset
and by reading the release API's asset `digest` field. Earlier search-indexed
display metadata contained a conflicting hash; do not use that value.

## Redistributing native runtimes

Retain the exact native archive's `LICENSE`, `licenses/`,
`PROVENANCE.json`, `VERSION`, and third-party notices alongside the runtime
in packaged releases. Carry firecrawl-pdfium's MIT/Apache-2.0 license notices
in the distribution notices bundle as well. The presence of permissive
notices does not remove obligations for bundled third-party PDFium
dependencies or patent/security review.

Cross-platform plan: separately pin + SHA-256 verify the same `native-v7988`
release's `firecrawl-pdfium-mac-arm64.tgz`,
`firecrawl-pdfium-mac-x64.tgz`, `firecrawl-pdfium-linux-x64.tgz`,
and any further supported architectures. Bundle native platform libraries
adjacent to the executable or in an application-owned runtime directory.
Do not silently fall back to system PDFium in production.

## Remaining integration tasks

Native raster pixels and per-character PDF page-space geometry allow a
Slint `Image` plus overlay rectangles. For production, calibrate glyph
index mapping against PDFium's generated whitespace, ligatures and UCS-2
limitations; split highlights across lines rather than using one aggregate
bounding box. Test rotated/cropped pages, zoom/high-DPI coordinate
transforms, encrypted/corrupt PDFs, keyboard selection, screen-reader
companion text, annotation persistence and archive integrity.
