# Historical Python tracked secret-scan review

This file is retained as legacy Python-release evidence. `detect-secrets` was run after the historical Python integration and its tracked-file candidates were reviewed manually.
No live credential or private research datum was identified in the flagged tracked files.

A final pre-release scan across all tracked files plus intended untracked public candidates reported
**338 findings in 27 files**. Every finding falls into the reviewed categories below (synthetic
security fixtures, hashes/manifests/scanner output, or the PDF-ingest validation alphabet). No new
AI provider/runtime/conversation source file introduced a secret candidate.

| Candidate group | Files / examples | Review result |
|---|---|---|
| Safe-character alphabet | `src/researchweave/ai/pdf_ingest.py` | Scanner flags the long alphanumeric allow-list used to validate document IDs. It is code, not secret material. |
| Redaction/security fixtures | `tests/integration/test_int_064_sync.py`, `tests/unit/test_logging.py`, AI/evidence security tests | Deliberately fake values such as the literal `correct horse battery staple`, intentionally wrong passwords, synthetic API keys, basic-auth URLs and recovery tokens exercise rejection/redaction behavior. They are test fixtures only. |
| Base64 fixture content | evidence tests | Encoded deterministic BibTeX/test payloads; decodes to synthetic publication metadata, not credentials. |
| Synthetic journey passphrases | Historical `workstreams/v2/ai/run_journeys.py` (available in Git history/recovery ref) | Explicitly labeled synthetic recovery passphrases used to exercise encrypted-sync conflict flows. |
| SHA-256 / manifest values | workstream traces, screenshot and asset manifests, generated secret-scan JSON | Content hashes expected to have high entropy; no authentication use. The full scan also flags hashes embedded in the focused scan output itself; those are scanner metadata, not credentials. |

The machine-readable full scanner output remains in `SECRETS_SCAN.json`; the focused source/test scan is
in `SECRETS_REVIEW_FOCUSED.json`. Any future candidate outside these documented fixture/hash categories
must be reviewed before release.
