---
name: rw-selection-grounded-ask
description: Pass exact selected text with source and permission metadata. Use for ResearchWeave Rust/Slint contextual ai audits and implementation review.
---

# Selection grounded ask

## Trigger and expected output

Use this skill when the goal is to **pass exact selected text with source and permission metadata**. This is a scoped, repeatable ResearchWeave UX engineering skill, not an automatic permission to edit files. Produce a brief audit record with the affected workflow, source evidence, observed behavior, screenshots or assistive-technology logs if obtained, and a pass/fail/pending decision.

**Discipline-specific method (Contextual AI):** Identify the exact originating object, data scope, permitted effect class and approval requirements. Inspect source grounding, model/provider selection and explicit consent before any egress or state change; test denied and unavailable states.

## Repeatable application procedure

1. **Identify the actual interaction.** Read [main.slint:1040-1079](https://github.com/aradmanamnaoon/researchweave/blob/976656d9ea5ce753f9b170383bf5cb65eb9f263d/crates/researchweave-desktop/ui/main.slint#L1040-L1079) in the current worktree and trace its callbacks into Rust before modifying behavior. Keep project scope, immutable revision semantics, privacy, and scientific integrity intact.
2. **Exercise the distinguishing probe.** Select PDF excerpt and ask for plain language explanation. Use a disposable local project and representative empty, populated, error, and keyboard-only states. Capture OS, scale, fixture, exact steps and observable output when testing is possible.
3. **Apply the correction.** Compare the observed outcome with the acceptance gate below. Fix the smallest common interaction/component cause, preserve focus and drafts, and verify the action against the typed Rust handler rather than relying on visual mock controls.
4. **Recheck and report.** Repeat the original probe after changes, inspect relevant neighboring states, run targeted tests and a native GUI check, and classify each remaining gap explicitly as unresolved. Attach source and test evidence to the final review.

## Review checklist

- [ ] Entry point and result context for this specific goal are discoverable from the intended task.
- [ ] The probe was exercised with real UI behavior, including a failure or boundary condition, and evidence is linked.
- [ ] No control claims a capability, effect, citation, or analysis output that the backend cannot deliver.
- [ ] Keyboard focus, accessible names, long text, mixed scripts, and offline/error states have been checked where applicable.
- [ ] The targeted acceptance gate is met with an observed result, or recorded as pending/failing.

**Acceptance gate:** Request preview identifies selected scope and source location.

## Task-specific evidence to capture

- **Fixture and setup:** Record the project revision, OS/platform and source/document/dataset setup necessary for this specific probe.
- **Reproduction script:** Select PDF excerpt and ask for plain language explanation.
- **Expected observation:** Request preview identifies selected scope and source location.
- **Measured result:** Pending until the probe is run on the applicable actual implementation. Record a screenshot, structured output or assistive-technology log with its exact version; a code reference alone is insufficient.

## Baseline application record (static inspection only)

## 30 October 2026 native implementation and scoped GUI evidence

**Latest superseding scope (r6):** PDF Reader initial passage UI caused a strict 200%-scale narrow-window extracted-text visibility **FAIL**. The form was moved below the compact extracted-text control; exact-source Linux executable SHA-256 `a96e2a8db0760e02833049e6f4c38cee73a284bc7f7bc7958b41c597ffedae21` then **PASS** both the passage preview positive/mismatch/path-change private native GUI and the independent 900×620/200% original page1/page2/copy/Find Next/path-clear workflow. [Portable r6 evidence](../../screenshots/pdf-passage-r6/). This supersedes the earlier r5 snapshot only for the stated Linux scenarios; it does not certify built Windows/macOS packages or genuine persisted PDF citation/annotation anchors.

The Reader now offers **Selected PDF passage** with explicit instructions to select/copy from its read-only extracted text and paste exact text. Slint 1.18 does not expose the native TextEdit selection range to Rust; this is **not automatic highlighting capture**. `verified_pdf_passage` in `main.rs` matches only one exact bounded UTF-8 occurrence in the displayed page, and binds a host-held render job, page number, path and text digest. The preview identifies path, page, displayed-text byte range and SHA-256, labels the excerpt unverified, and cannot send data until an explicit local-model Run. Persisted annotations and archival citations are not implied.

The independent `scripts/ux/isolated-xvfb-pdf-passage-ai.sh` private Linux GUI workflow **PASS** real Ctrl+A/C from the read-only text widget, explicit paste/button, preview scope, rejection of nonmatching text, and path-change invalidation. Exact-source frozen executable SHA-256 `dfcd3204d4bcade67d92175567cee70b40c217d2b5fd025638072cbe74020d97`; source/screenshot receipts at [pdf-passage-r5](../../screenshots/pdf-passage-r5/). **Disposition: scoped Linux native GUI PASS for the stated acceptance gate; untested on installed Windows/macOS and assistive-technology speech.** This is not a signoff for the remaining 99 skills.

- **Snapshot:** origin/main 976656d, 2026-10-29; UI may evolve after this snapshot.
- **Evidence:** [main.slint:1040-1079](https://github.com/aradmanamnaoon/researchweave/blob/976656d9ea5ce753f9b170383bf5cb65eb9f263d/crates/researchweave-desktop/ui/main.slint#L1040-L1079).
- **Observation:** Rendered PDF is an Image with search highlight but no selectable passage.
- **Next test or improvement:** Test selection provenance and privacy before model call.
- **Status:** Audited against the source and UX requirements. Runtime probe, user research, implementation completion, and packaged-platform pass are **unverified** in this skill record.

Read [UX acceptance criteria](../../UX_ACCEPTANCE_CRITERIA.md), [design system](../../DESIGN_SYSTEM.md), and [AGENTS.md](../../../../AGENTS.md) before applying. Complement with existing .agents/skills/desktop-accessibility or .agents/skills/research-beginner-experience for their specialties. Existing PyQt6-specific instructions must be adapted to the **Rust/Slint** implementation.
