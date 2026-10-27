# ResearchWeave UX Vision

## Product idea

ResearchWeave should feel like a **research workbench**, not a collection of tools and not an AI dashboard. The interface should keep the object of research in the center—source, protocol, dataset, analysis, review record, note, or manuscript—while surrounding it with just the context and actions needed for the current task.

The distinctive experience is **traceable flow**: users can move from question to evidence to analysis to writing without losing provenance, and advanced users can inspect every revision, assumption, approval and reproducibility detail without forcing that complexity on beginners.

## Design principles

### 1. Research objects, not screens

Users open and work on objects. A source can be read beside its notes. A dataset can be analyzed beside its variable inspector. An analysis result can reopen its exact configuration. A manuscript claim can link back to evidence.

### 2. Progressive disclosure without feature hiding

Default views expose the safe/common path. Advanced parameters, raw metadata, diagnostics, provenance and expert controls remain one action away. No required feature may become unreachable merely to simplify the UI.

### 3. Context travels with the user

Selection, open documents, filters, scroll position, active dataset revision and relevant inspectors should survive reasonable navigation. Moving to another activity should not erase the user's research context.

### 4. Reproducibility is visible

Every scientific operation should make its important inputs and resulting revision/artifact inspectable. Analyses show dataset revision, parameters, exclusions, assumptions and warnings. Local writes show resulting revision. Exports expose what is included and how it was produced.

### 5. AI proposes; the host authorizes

AI is contextual and assistive. It may explain, draft, summarize and propose exact commands. It never silently crosses the existing effect/approval boundaries. Side effects show destination, scope and consequences before approval.

### 6. Local-first status is understandable

Users should always be able to tell whether work is local, whether a cloud connection is configured, whether safe conditional writes have been verified, whether sync is current/conflicted, and whether an operation can transmit data.

### 7. Keyboard and pointer are peers

Every primary action must be reachable through keyboard navigation and the command palette. Mouse/pointer interaction should remain direct and discoverable. Focus movement follows stable workbench regions.

### 8. Accessibility is architecture

Focus order, pane landmarks, accessible names, high contrast, scaling, reduced motion, screen-reader summaries and nonvisual chart/result alternatives are part of component contracts, not post-release patches.

### 9. Multilingual by construction

All text controls are Unicode-safe. Text editors/readers support explicit LTR/RTL paragraph direction and sensible auto-detection. Layout uses logical start/end semantics where possible; directional icons mirror only when meaning requires it.

## Target workbench

The desktop window has five conceptual regions. Not all must be visible simultaneously.

1. **Activity rail** — six stable roots: Home, Sources, Analyze, Synthesize, Automate, Manage.
2. **Context sidebar** — navigation/filter/tree for the active activity, such as library collections, datasets, review stages, manuscript sections or settings categories.
3. **Work area** — tabbed research objects and workflow editors. Supports one primary document and later optional split view.
4. **Inspector** — contextual metadata, provenance, variables, analysis options, evidence links, approvals, or properties. Collapsible and keyboard-focusable.
5. **Bottom/status tray** — jobs, notifications, problems, diagnostics and sync state; normally compact and expandable on demand.

This is intentionally closer to a professional workbench than to a dashboard-with-cards pattern.

## Beginner experience

- Start Center explains local-first storage in one sentence and offers New Project, Open Project, Import Existing, and recent projects.
- New Project uses a guided, short flow with intelligent defaults. Advanced storage/privacy options are expandable.
- Project Home shows a small number of next actions based on current state rather than all features.
- Analysis workflows begin with intent-oriented choices and show advanced assumptions/options progressively.
- Contextual help explains the current control/task without sending the user to a separate documentation screen.
- Empty states teach the next meaningful action and never display dead decorative cards.

## Expert experience

- Global command center searches commands, settings, open/recent resources and destinations.
- Keyboard focus commands move among rail, sidebar, work area, inspector and bottom tray.
- Open resources persist in tabs; recent-resource switching is fast.
- Inspectors expose revision IDs, hashes, exclusions, assumptions, scripts/receipts and raw metadata when requested.
- Power users can change density, pane visibility, layout and shortcuts.
- Long-running jobs remain nonmodal, cancellable where backend semantics support cancellation, and reconnect to their resulting artifacts.

## Signature workflows

### Source-to-evidence

Library list -> open source -> reader in work area -> annotations/evidence in inspector -> create note/anchor -> note contains source backlink and verification state -> optional manuscript/review reuse.

### Data-to-result

Dataset tab -> variable/data modes -> choose analysis -> options inspector -> preview assumptions/exclusions -> run -> result tab appears linked to dataset revision -> result can reopen settings and export accessible tables/plots.

### Review-to-PRISMA

Review workspace -> stage queues -> blinded screening -> conflict/adjudication -> retrieval -> full-text eligibility -> extraction -> live PRISMA accounting. PRISMA is derived from persisted events and flags unresolved accounting instead of allowing cosmetic manual reconciliation.

### Contextual AI

Assistant drawer sees only the context the user explicitly supplies/permits. It returns text plus inert action proposals. Proposed write/network actions render as reviewable commands with exact effect labels and approval scope.

## Visual identity direction

ResearchWeave should be calm, dense when needed, and editorial rather than flashy. Use a neutral ink-and-paper base, a restrained research accent, strong typographic hierarchy, fine dividers, and high-quality data/document surfaces. Avoid oversized marketing cards, excessive gradients, decorative glass effects, and chat-centric composition.

The visual language should communicate three semantic concepts consistently:

- **Working context** — selected/open/current.
- **Research state** — draft/verified/warning/conflict/reproducible.
- **Effect boundary** — read/local write/network/sensitive/irreversible.

## Inspiration, not imitation

- VS Code/RStudio: command discoverability and stable workbench regions.
- jamovi/JASP: analysis parameters kept adjacent to results and approachable defaults.
- Zotero: source reading, annotations, notes and citations remain connected.

ResearchWeave differs by making scientific provenance, immutable revisions, approvals and offline/cloud boundaries first-class parts of the interaction model.
