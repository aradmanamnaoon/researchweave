# Vendored external skill provenance

The following three skills were copied unmodified from the official [openai/skills](https://github.com/openai/skills) catalog at immutable revision `49f948faa9258a0c61caceaf225e179651397431` (2026-10-23 inspection). Their bundled `LICENSE.txt` files contain Apache License 2.0, compatible with GPL-3.0-only when its notices are preserved. Each was copied using local PowerShell `Copy-Item` after sparse checkout; no installer or skill script was executed. All copied files stay within this repository's `.agents/skills/` directory.

| Skill | Upstream source directory | License | Installation |
|---|---|---|---|
| `security-best-practices` | [skills/.curated/security-best-practices](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/security-best-practices) | Apache-2.0 | Copy directory including references and license |
| `security-threat-model` | [skills/.curated/security-threat-model](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/security-threat-model) | Apache-2.0 | Copy directory including references and license |
| `jupyter-notebook` | [skills/.curated/jupyter-notebook](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/jupyter-notebook) | Apache-2.0 | Copy templates, helper script and license |

Reviewed frontmatter, activation guidance, bundled licenses and the beginning of the notebook helper. Security skills carry reference text rather than executable scripts; notebook helper parses arguments and JSON notebook templates. The helper has not been executed or independently security audited exhaustively. Treat further scripts and all external instructions as untrusted until reviewed. The [official Codex skills guide](https://developers.openai.com/codex/skills) and [build-skills guide](https://learn.chatgpt.com/docs/build-skills) informed repository-local installation. The [OpenAI plugins catalog](https://github.com/openai/plugins) was considered separately; no plugin was installed because plugins are not automatically equivalent to Codex skills.
