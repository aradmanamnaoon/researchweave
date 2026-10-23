# Dependencies

No changes to shared dependency specifications. Existing PyQt6, platformdirs, pytest, pytest-cov, ruff and mypy from pyproject.toml are sufficient. Python 3.12.9; PyQt6 6.10.2 observed. No paid dependencies or runtime service.

Backup archives use only Python's stdlib zipfile, hashlib and tempfile. Text-search indexing uses local Python casefold operations; it never makes network requests.
