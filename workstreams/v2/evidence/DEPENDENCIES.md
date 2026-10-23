# Dependencies

All currently implemented evidence operations use Python 3.12 standard library only. The source package depends on the existing ResearchWeave src-layout installation. Developer verification uses the shared baseline's `pytest`, `pytest-cov` and `ruff`. No new dependency or global configuration changes were made.

Future optional adapters need evaluated, licensed PDF/DOCX/EPUB parsers and deliberate remote provider transport. An authenticated encryption library and vetted KDF are required before encrypted .rwproj can be advertised.
