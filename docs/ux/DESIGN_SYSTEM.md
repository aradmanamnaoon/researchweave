# ResearchWeave Design System

Status: target system for UX-M1. Tokens/components may evolve through measured GUI QA, but semantic contracts should remain stable.

## Design goals

- Professional research workbench, not a marketing dashboard.
- Comfortable at beginner density; efficient at expert density.
- High information integrity: provenance/warnings/effects have consistent visual meaning.
- Native-feeling focus, keyboard and window behavior.
- Light, dark and high-contrast-compatible semantics.
- Unicode/RTL-safe components.

## Typography

Use platform UI fonts by default to avoid bundled-font/licensing/IME surprises. Use a distinct monospaced system font only for code, hashes, IDs and raw diagnostics.

| Role | Suggested size | Weight | Use |
|---|---:|---:|---|
| Window/workspace title | 22–24 | 650–700 | Active project/workspace |
| Document title | 18–20 | 600–650 | Source/dataset/analysis/manuscript section |
| Section | 15–16 | 600 | Inspector/panel groups |
| Body/control | 13–14 | 400 | Default UI text |
| Supporting | 12–13 | 400 | Metadata/helper text |
| Compact metadata | 11–12 | 450 | Revision/time/status labels |

Never encode scientific meaning using font style alone.

## Spacing and geometry

Base unit: 4 px logical units.

- `space-1` 4
- `space-2` 8
- `space-3` 12
- `space-4` 16
- `space-5` 20
- `space-6` 24
- `space-8` 32

Control target heights: compact 28–30, standard 34–36, touch-friendly 40+. Do not use tiny icon-only targets without accessible names/tooltips.

Corner radii are restrained: 4–6 for controls, 8 for panels/dialogs. Avoid card-within-card nesting as the default layout primitive; use spacing/dividers/panes.

## Color semantics

Exact values must be contrast-tested in Slint on target platforms. Initial light-theme direction:

- Canvas: `#F5F6F7`
- Surface: `#FFFFFF`
- Raised surface: `#FAFBFC`
- Ink: `#172033`
- Muted ink: `#586577`
- Divider: `#D7DDE5`
- Accent: `#256B72` (research teal; interactive/selected, not status-only)
- Accent subtle: `#E4F1F1`
- Focus: `#0B6EE6`
- Success: `#197447`
- Warning: `#9A6410`
- Danger: `#B4232B`
- Conflict: `#7A4AA5`

Dark theme uses semantic tokens rather than inverted literals. High-contrast mode may use platform/high-contrast colors instead of brand fidelity.

Minimum text contrast target: WCAG AA 4.5:1 for normal text, 3:1 for large text and essential nontext focus/boundary cues.

## Effect semantics

Core `Effect` classes must map to consistent labels/icons and must never rely on color alone:

- Read — eye/read label; no approval.
- Local write — edit/storage label; approval when core policy requires it.
- Code execution — terminal/code label.
- External network — network/cloud label and destination host when known.
- Sensitive export — shield/export label and explicit data scope.
- Irreversible — warning/octagon label plus confirmation/approval semantics from core.

The UI renders authority state; it does not invent weaker effect rules.

## Shared component contracts

### ActivityRail

- Six stable roots with icon + accessible name.
- Current state visible via color + shape/indicator.
- Arrow-key navigation within the rail; one Tab stop for the rail when possible.

### ContextSidebar

- Optional tree/list/filter for active activity.
- Search/filter remains in the same region.
- Virtualized lists must have a keyboard fallback if platform accessibility scrolling is unavailable.

### WorkTabs

- Typed object identity, close/reopen behavior, dirty/pending state when applicable.
- Ctrl+Tab recent-tab cycling; accessible tab names and position.
- Tabs do not imply unsaved mutation for immutable domain objects.

### Inspector

- Collapsible groups.
- Context-sensitive properties/options/provenance.
- Advanced groups collapsed by default when safe.
- All option changes state whether they are preview-only or will create a new revision/run.

### CommandCenter

- Search field + categorized result list.
- Keyboard Up/Down/Enter/Escape.
- Entries expose shortcut and disabled reason.
- Supports commands, views, resources, settings and help.
- Never directly executes an effect that core requires approval for; opens preview/approval flow first.

### ApprovalSheet

- Operation title and plain-language effect.
- Project/scope/destination.
- Preview summary and irreversible/sensitive consequences.
- Approve / Cancel with safe default focus.
- Optional details showing normalized arguments without leaking secrets.

### JobItem / JobTray

- Queued/running/succeeded/failed/cancelled.
- Progress if meaningful; indeterminate otherwise.
- Cancel only when backend supports safe cancellation.
- Link to resulting artifact/error details.
- Status changes announced politely to assistive technology; repeated progress ticks are not spammed.

### ScientificResult

- Title, method, dataset revision, timestamp/run identity.
- Assumptions/warnings before interpretation.
- Tables/plots plus accessible textual alternative.
- Reopen settings, copy/export, provenance.

### EmptyState

- States why the area is empty.
- One primary next action and at most a few secondary actions.
- No decorative metric cards with zero values.

### ErrorState

- Human-readable summary.
- Recovery action when possible.
- Copyable diagnostic ID/details.
- Provider/network errors use redacted categories; no raw credential-bearing messages.

## Focus and keyboard model

- Visible focus indicator at least 2 px equivalent and 3:1 against adjacent colors.
- F6/Shift+F6 cycles major workbench regions.
- Tab moves through actionable controls in logical order inside a region.
- Arrow keys navigate composite widgets (rail, tab list, menu, tree, toolbar) to reduce tab-stop explosion.
- Escape closes transient UI and restores prior focus.
- Command center exposes all important commands even if no dedicated shortcut exists.

## Themes, density and scale

- Themes: Light, Dark, System; High Contrast follows OS where feasible.
- Density: Comfortable and Compact; scientific table row density can be independently compact if needed.
- UI scale: follow OS scale and offer supported in-app zoom only if Slint/platform behavior remains accessible.
- Persist user appearance settings outside scientific project content.

## Motion

Motion communicates state, never decorates idle UI.

- Micro transition: 120–160 ms.
- Panel reveal: 160–200 ms.
- No long easing on frequently repeated analysis/selection interactions.
- Reduced-motion setting removes nonessential transitions and animated movement; progress can remain non-motion textual/visual state.

## RTL and multilingual behavior

- Store/render UTF-8 without lossy normalization.
- Text editors support explicit paragraph direction: Auto / LTR / RTL.
- Logical Start/End spacing/alignment should replace hard-coded Left/Right where component framework permits.
- Mixed-direction scientific strings, numbers, equations, DOIs and code remain stable.
- Chevron/back/forward icons mirror only where navigation direction is semantic.
- Tables keep numeric columns aligned according to data semantics rather than blindly mirroring every column.

## Charts and custom drawing

- Every chart has a meaningful title/description and table/text alternative.
- Color palettes are distinguishable without relying solely on hue.
- Keyboard focus reaches interactive marks/legend only when interaction adds value; otherwise expose an accessible summary/table instead of hundreds of focus targets.
- Exported plots carry enough metadata/provenance to identify source analysis where feasible.
