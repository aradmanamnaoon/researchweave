# Dependencies

Most local evidence operations use Python 3.12's standard library and SQLite FTS5.
The source package depends on the existing ResearchWeave src-layout installation.
Developer verification uses the shared virtual environment's `pytest`, `pytest-cov`,
`ruff` and `mypy`. No shared packaging or lockfile configuration was edited.

`cryptography` is an **optional runtime dependency** for password-protected
`.rwproj.enc` bundles. The implementation uses its vetted AES-256-GCM primitive
and `Scrypt` KDF; missing installations fail with a typed actionable error.
`pypdf` is an **optional runtime dependency** for live PDF text extraction;
its absence is reported without fabricated OCR. DOCX and EPUB extraction use
bounded, validated standard-library ZIP/XML parsing. There is no default OCR
provider. The final integrator should add documented optional extras for
`cryptography` and `pypdf` after appropriate license/version and vulnerability
review. Public catalog clients use a trusted, explicitly injected HTTPS transport;
no provider access or paid dependency is enabled automatically.
