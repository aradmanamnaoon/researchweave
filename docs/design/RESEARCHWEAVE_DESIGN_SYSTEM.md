# ResearchWeave design system

Snapshot: 2026-10-26. The Rust desktop shell uses Slint. This document describes the current implemented visual primitives and the acceptance rules for future work; it is not a claim that every legacy screen has already been redesigned.

## Identity

ResearchWeave uses an original woven-evidence mark from assets/branding/researchweave-mark.svg and the platform application icon assets in assets/branding. The mark represents connected evidence and synthesis without generic brain/AI imagery. The Rust window, Windows installer/shortcut, Linux launcher/AppImage and macOS bundle packaging now reference the same brand family.

The six stable activity roots are Home, Sources, Analyze, Synthesize, Automate and Manage. They use original monochrome SVGs from assets/icons and a custom accessible ActivityNavButton rather than host-colored primary buttons.

## Semantic palette

| Role | Light direction | Dark direction | Purpose |
| --- | --- | --- | --- |
| Deep Ink | #172438 | #F4F6F8 text on #172438 surfaces | Main identity, text, navigation rail |
| Research Teal | #147A75 | #55C7BD | Primary ResearchWeave accent and selection |
| Evidence Violet | #7564B5 | #A997E8 | Evidence/conflict/focus secondary semantic |
| Discovery Copper | #9A5B3A | #E0A17B | Discovery/warning-adjacent secondary semantic |
| Soft Paper | #F6F5F1 | #101923 canvas | Long-session reading canvas |

Theme also defines surface, raised surface, muted text, divider, focus, success, warning, danger, reader canvas, tab strip and four scientific-data roles. High contrast overrides these roles with black/dark surfaces, white text/borders, yellow selection accent and cyan focus. Color is never sufficient by itself: selected activity also changes shape/border/indicator, and scientific charts require labels/data tables.

The Rust contrast test in crates/researchweave-desktop/src/display_contrast.rs evaluates key text/accent combinations against a 4.5:1 threshold. It is a token audit, not legal WCAG certification.

## Layout and density

Spacing uses semantic Theme space tokens. Research surfaces use a persistent activity rail, optional contextual navigation, a workbench header/command center, an object strip, central task surface and optional inspector. At large text scale or narrow width, contextual sidebars/inspectors collapse completely and the command center remains the route to hidden destinations.

The activity rail uses stacked icon-over-label tiles so long names such as Synthesize and Automate do not truncate. The selected activity uses Research Teal outline/indicator plus a surface change. The resize harness asserts all six activity buttons are on-screen and their UIA rectangles do not overlap at medium, narrow and minimum Windows sizes.

## Typography and controls

Current typography is system-font based for cross-platform availability. Heading, metadata and body sizes scale with Theme.ui-scale; the preference range is 80–200 percent. Native text fields/editors are retained for platform semantics. Custom controls must provide accessible role/name/action, visible focus and keyboard activation.

The manuscript workspace gives the editor a stable minimum reading height, keeps save/inspect actions separate from export actions, and bounds operation receipts in a scrollable panel. Artifact payload bytes are not dumped into the visible UI.

## Accessibility acceptance

New interactive components must provide a meaningful UIA/accessibility role and label, keyboard activation, visible focus, and non-color status cues. At minimum, affected screens are tested at ordinary size, minimum supported size and 200% application text scale. Screen-reader certification still requires real NVDA/VoiceOver/Orca evidence on the corresponding native platform.

## Current visual evidence

- docs/verification/rust-rewrite/activity-rail-redesign-v3.png: minimum-size light theme, all six activities visible and non-overlapping.
- docs/verification/rust-rewrite/activity-rail-200pct.png: 200% high-contrast rail and Preferences state.
- docs/verification/rust-rewrite/manuscript-docx-ui-v5.png: manuscript editor with visible versioning actions and four export formats after DOCX generation.

## Open design-system work

Some general-purpose Slint native buttons still inherit host accent styling rather than ResearchWeave Teal; they remain semantically correct but visually less unified. Advanced workspace-specific shells (page-oriented rich editor, statistical data grid/results split, qualitative coding panes, reference three-column view, knowledge graph and source-grounded AI view) remain product work and must reuse these semantic tokens instead of copying competitor branding.
