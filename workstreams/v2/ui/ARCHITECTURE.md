# UI architecture

The Qt shell delegates actions to UIFacade. The facade exposes 24 typed, namespaced local commands with structured errors and previews. ProjectStore persists versioned JSON atomically with optimistic revision checks. PreferenceStore validates color, density and scale. ResearchTableModel virtualizes table rows. JobManager is a bounded Qt thread pool with cancellation and generation checks. The prototype runs without accounts or network connections.

In production the integrator must inject evidence/analysis/AI facades and provide host-bound approval, durable project database, provenance and professional document rendering. Scientific inference and source verification are outside this worker's demo domain.

The latest implementation includes editable method templates (research_guides.py), local search over research objects (search.py), and integrity-checked ZIP snapshots (snapshots.py). Archives contain only manifest.json and project.json, with schema/hash validation and size/compression restrictions; no arbitrary file extraction occurs. Backup creation/restoration requires a host-injected approval callback. Restoring creates a distinct project UUID and retains the original.
