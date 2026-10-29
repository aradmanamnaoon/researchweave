---
name: rw-work-object-breadcrumbs
description: Show current document ancestry and return route. Use for ResearchWeave Rust/Slint navigation audits and implementation review.
---

# Work object breadcrumbs

## Trigger and expected output

Use this skill when the goal is to **show current document ancestry and return route**. This is a scoped, repeatable ResearchWeave UX engineering skill, not an automatic permission to edit files. Produce a brief audit record with the affected workflow, source evidence, observed behavior, screenshots or assistive-technology logs if obtained, and a pass/fail/pending decision.

**Discipline-specific method (Navigation):** Trace the active project and object identity before and after the route. Check discoverability through visible navigation, command search, and keyboard-only access; avoid losing the work context on route changes.

## Repeatable application procedure

1. **Identify the actual interaction.** Read [main.slint:369-374](https://github.com/aradmanamnaoon/researchweave/blob/976656d9ea5ce753f9b170383bf5cb65eb9f263d/crates/researchweave-desktop/ui/main.slint#L369-L374) in the current worktree and trace its callbacks into Rust before modifying behavior. Keep project scope, immutable revision semantics, privacy, and scientific integrity intact.
2. **Exercise the distinguishing probe.** Navigate from PDF through evidence and back using a named source. Use a disposable local project and representative empty, populated, error, and keyboard-only states. Capture OS, scale, fixture, exact steps and observable output when testing is possible.
3. **Apply the correction.** Compare the observed outcome with the acceptance gate below. Fix the smallest common interaction/component cause, preserve focus and drafts, and verify the action against the typed Rust handler rather than relying on visual mock controls.
4. **Recheck and report.** Repeat the original probe after changes, inspect relevant neighboring states, run targeted tests and a native GUI check, and classify each remaining gap explicitly as unresolved. Attach source and test evidence to the final review.

## Review checklist

- [ ] Entry point and result context for this specific goal are discoverable from the intended task.
- [ ] The probe was exercised with real UI behavior, including a failure or boundary condition, and evidence is linked.
- [ ] No control claims a capability, effect, citation, or analysis output that the backend cannot deliver.
- [ ] Keyboard focus, accessible names, long text, mixed scripts, and offline/error states have been checked where applicable.
- [ ] The targeted acceptance gate is met with an observed result, or recorded as pending/failing.

**Acceptance gate:** Breadcrumb names document and path while preserving reading position.

## Task-specific evidence to capture

- **Fixture and setup:** Record the project revision, OS/platform and source/document/dataset setup necessary for this specific probe.
- **Reproduction script:** Navigate from PDF through evidence and back using a named source.
- **Expected observation:** Breadcrumb names document and path while preserving reading position.
- **Measured result:** Pending until the probe is run on the applicable actual implementation. Record a screenshot, structured output or assistive-technology log with its exact version; a code reference alone is insufficient.

## Baseline application record (static inspection only)

- **Snapshot:** origin/main 976656d, 2026-10-29; UI may evolve after this snapshot.
- **Evidence:** [main.slint:369-374](https://github.com/aradmanamnaoon/researchweave/blob/976656d9ea5ce753f9b170383bf5cb65eb9f263d/crates/researchweave-desktop/ui/main.slint#L369-L374).
- **Observation:** Object kind is inferred from page number only.
- **Next test or improvement:** Implement and exercise typed work object navigation.
- **Status:** Audited against the source and UX requirements. Runtime probe, user research, implementation completion, and packaged-platform pass are **unverified** in this skill record.

Read [UX acceptance criteria](../../UX_ACCEPTANCE_CRITERIA.md), [design system](../../DESIGN_SYSTEM.md), and [AGENTS.md](../../../../AGENTS.md) before applying. Complement with existing .agents/skills/desktop-accessibility or .agents/skills/research-beginner-experience for their specialties. Existing PyQt6-specific instructions must be adapted to the **Rust/Slint** implementation.
