# ResearchWeave's 100 project UX skills

This directory contains **100 individually named ResearchWeave UX audit and implementation instruction packages** in `<slug>/SKILL.md`. They cover navigation, onboarding, visual design, interactions, accessibility, source workflows, data analysis, writing, contextual AI, and reliability. They are specific to the Rust/Slint app and its existing scientific and privacy contracts.

Start with [the 100-skill application matrix](../100_SKILLS_APPLICATION_MATRIX.md). Choose a skill by task or select every skill under a category for a full work area audit. Read that `SKILL.md`, inspect its referenced current Rust/Slint files, perform its specific probe on the actual GUI, then record evidence and accept or reject the result. The package supplies a goal, specialist method, repeatable procedure, tailored probe, pass criterion, and baseline source observation. For cross-cutting expertise also consult the existing repository `.agents/skills`, especially `desktop-accessibility` and `research-beginner-experience`.

Also inspected existing external skill packages under `/skills/anatomyweave/`: `screen-reader-testing`, `interaction-design`, `onboarding`, `visual-design-foundations`, and `wcag-audit-patterns`. Their focus, keyboard testing, purpose-driven feedback, first-success tasks, and color/spacing review concepts inform this catalog. Many examples in those external packages use browser ARIA/CSS or growth funnels, so use **native Slint and OS accessibility APIs** for implementation and measure scientific-task success for onboarding. The repository-local packages are separately authored for those desktop constraints.

## Provenance and status

The packages were authored in this UX worktree on 2026-10-29 using code inspection of baseline `origin/main` commit `976656d`. Their observations are **static audit records**. No skill claims that an unrun GUI test passed or that a missing feature has already been implemented. The skills are **repository-local authored instruction files**, not automatically loaded or installed in the agent's managed skill registry.

These files are deliberately under `docs/ux/skills/`, the assigned work area; this workstream does not modify `.agents/skills`, system installations, application source, or release assets. If the project later wants automatic agent discovery, an authorized integration can register or copy the selected packages into the relevant supported skill directory after checking its discovery rules. Avoid duplicating conflicting legacy PyQt6 rules in the Rust workflow.

## Reproduce and validate

Edit `catalog.psv` when a skill's scope, acceptance gate, or baseline finding changes. It contains 100 records with nine fields: ID, category, slug, goal, unique audit probe, acceptance gate, source evidence range, baseline observation, and follow-up. Use `|` only as the separator.

From the repository root on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File docs/ux/skills/build_catalog.ps1
```

The script validates the count, unique IDs, unique slugs, and source-range bounds, then regenerates the 100 skill packages and matrix deterministically. After new UI work, verify whether the pinned baseline references still describe the current code. Preserve historic audit evidence while adding new source refs, native screenshots, tests, and a per-skill acceptance decision. A feature graduates from `Pending` only with observed behavior and reproducible evidence.
