# Architectural boundaries

Implemented: `app/main.py` owns Qt launch and welcome window; `app/config.py` provides typed offline defaults; `app/logging.py` emits redacted keyed JSON events. Proposed future packages include `ui`, `core`, `agents`, `providers`, `research`, `statistics`, `integrations`, `storage`, `security`, `documents`, `export`. Add each when meaningful, not as placeholder code.

Scientific analysis should be independent of UI imports. Persistence must be versioned, providers opt-in, methods reproducible, and agent actions explicitly authorized.
