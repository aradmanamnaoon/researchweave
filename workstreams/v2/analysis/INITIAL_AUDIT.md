# ResearchWeave V2 Analysis — baseline audit

- Base checkout: `D:\coding\codex\researchweave` (`main` at `af5c862d780d65c62a8c083fbfb64bd08a420092`).
- Worker checkout: `D:\coding\codex\researchweave-v2-analysis` (`rebuild/v2-analysis`, created from the base SHA).
- Original base has an untracked `prompts/` directory. No writes to that checkout.
- Historical branches: `feature/rw-ai`, `feature/rw-analysis`, `feature/rw-evidence`, `feature/rw-ui` (retained).
- Existing base source has app bootstrap and no V2 scientific-analysis implementation.
- Exclusive production ownership: `src/researchweave/analysis/**`; tests `tests/v2/analysis/**` and worker handoff `workstreams/v2/analysis/**`.
- Source layout target (relative): `src/researchweave/analysis/`; final destination only after integration: `D:\coding\codex\researchweave\src\researchweave\analysis\`.
- Initial runtime discovery: `python` invokes Windows Store alias; a working Python 3.12.9 interpreter exists in base `.venv`; an isolated worktree `.venv` was created with `uv`.
- Raw research inputs and existing unrelated files are outside owned paths and will remain unchanged.
