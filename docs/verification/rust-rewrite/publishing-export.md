# §40.68 — native manuscript artifact export

`writing.manuscript_export` accepts a persisted `manuscript_id` and optional
`format` equal to `markdown` (default), `html`, `docx`, or `pdf`.
Unsupported formats fail closed. The command is read-only: no journal account,
identifier, ethics approval, or submission is created or asserted.

Each receipt supplies `mime_type`, `byte_length`, a SHA-256 digest over the
actual artifact bytes, `base64`, `submission_performed=false`,
`scientific_claims_verified=false`, and each persisted section's revision
and content digest. Existing `text` remains the original Markdown export
for compatibility. DOCX is an OPC ZIP package containing actual WordprocessingML;
HTML escapes untrusted source text; PDF is a valid minimal one-page PDF with
cross-reference offsets and a standard font.

## Fidelity and required review

- HTML and DOCX preserve section titles and basic paragraph boundaries, with
  citation markers left literal rather than inventing bibliography mappings.
- The dependency-free PDF renderer supports up to 45 physical lines and 110
  characters per line; it substitutes ASCII `?` for characters outside its
  basic font encoding. Use DOCX/HTML for Unicode or longer manuscripts; no
  claim of typesetting or Unicode fidelity is made.
- Exports contain the underlying research text; the authorized project host
  must enforce local access and any sensitive-export policy before delivering
  the receipt to an external process.
- Bibliography verification, journal-specific editorial checks, signed human
  review and actual submission are separate workflows. This export does not
  implement submission or assert readiness.

The Rust exporter adds no new Cargo dependencies or external side effects.
