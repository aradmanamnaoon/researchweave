# Initial audit — 2026-10-23

- Canonical repository: `D:\coding\codex\researchweave`, branch `main`.
- Recorded common base: `af5c862d780d65c62a8c083fbfb64bd08a420092`.
- Evidence worktree: `D:\coding\codex\researchweave-v2-evidence`; branch `rebuild/v2-evidence`.
- Base status: `main` had untracked `prompts/`; preserved intact.
- Historical branches: `feature/rw-ai`, `feature/rw-analysis`, `feature/rw-evidence`, `feature/rw-ui`; their worktree registrations are currently prunable. Nothing deleted, reset, stashed or merged.
- Production ownership: `src/researchweave/evidence/**`; tests `tests/v2/evidence/**`; documentation `workstreams/v2/evidence/**`, `docs/v2/evidence/**`.
- Current repo baseline: Python 3.12, PyQt6 root app, hatchling src layout; old `src/researchweave/research` and `src/researchweave/storage` contain placeholders. New worker code stays isolated.
- Applicable project-local skills reviewed: local-first-storage, citation-and-bibliography-verification, systematic-review-engineering, research-project-portability, scientific-test-engineering, scientific-research-workflows.
