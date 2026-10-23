# Dependencies

Most modules use Python 3.12 standard library only. Deterministic tests require pytest from the existing dev extra. Authenticated snapshot encryption and OS keyring adapters optionally require the version ranges in `requirements-optional.txt`, observed and tested locally as `cryptography==47.0.0` and `keyring==25.7.0`. Those two packages were installed into the isolated worker `.venv`; no root pyproject/lock or global Python environment was changed. Integration should add versioned project extras, regenerate the lock and run dependency auditing. Encryption fails closed with `DEPENDENCY_MISSING` if optional cryptography is absent. The crypto tests skip if `cryptography` has not been installed.

