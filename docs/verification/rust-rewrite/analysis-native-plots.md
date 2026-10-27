# Native plot rendering — §40.58–40.61

Read capability: `plot.render`. Required arguments: `dataset_id`,
`revision`, `x`, `y`. Optional: `kind` = `scatter` or `line`
(default scatter), `format` = `svg` or `png` (default SVG), `width` and
`height` (240–1600 pixels, default 720×480).

The renderer reads an immutable dataset revision through `DatasetStore::load`
and returns either deterministic SVG markup or a real native PNG raster, plus
descriptive `alt_text` and a machine-readable `data_table` retaining complete
numeric coordinate pairs in original order. Both formats include the dataset
ID, revision, original source hash, numeric axis bounds and included/excluded
observation counts. PNG uses a bounded RGB raster (white background, axes and
the same scatter/line geometry as the SVG), encodes with the Rust `png` crate,
and returns MIME type, byte count, base64 payload and SHA-256. Missing pairs are
excluded. Non-numeric or non-finite coordinates, degenerate axes,
descending/duplicate x values for line plots, unsupported options and more than
5000 complete pairs fail closed. Raster allocation is also bounded before
compression.

The SVG has a title, image role and accessible label; it contains no private
paths or local filesystem links. PNG deliberately does not rasterize textual
labels; accessibility text and the exact data table are returned alongside the
image instead. Rendering writes no files and requires no Python, R, or external
renderer. SVG, PNG, alt text and table derive from the same validated numeric
rows. Output is deterministic for identical immutable input and arguments,
including after service restart.

## Limitations

- Dataset storage is globally accessible within this analysis crate; project
  ownership authorization remains an upstream responsibility.
- Only numeric scatter and ascending-x line plots are implemented. There are no
  date axes, legends, confidence bands, ticks, plot themes or GUI controls yet.
- The PNG intentionally embeds no text glyphs; screen-reader text and the data
  table remain separate response fields. This avoids platform-font drift while
  keeping PNG bytes deterministic.
- SVG coordinates are rounded to three decimal places for deterministic output;
  the accompanying machine-readable table preserves numeric data values.

Regression test: `plots::tests::svg_table_escape_unicode_revision_restart_and_fail_closed`
also checks deterministic PNG bytes across restart, PNG signature and IHDR
dimensions, SHA-256 and data-table parity. Current analysis suite: **22/22**
passed with strict warnings-denied Clippy.
