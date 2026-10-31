# ResearchWeave design system

Updated: 2026-10-31 on isolated mission branch. The Rust desktop shell uses Slint. Semantic token changes are implemented in source; new installed-GUI screenshots and multi-platform visual acceptance remain pending.

## Identity

ResearchWeave uses an original woven-evidence mark from assets/branding/researchweave-mark.svg and the platform application icon assets in assets/branding. The mark represents connected evidence and synthesis without generic brain/AI imagery. The Rust window, Windows installer/shortcut, Linux launcher/AppImage and macOS bundle packaging now reference the same brand family.

The six stable activity roots are Home, Sources, Analyze, Synthesize, Automate and Manage. They use original monochrome SVGs from assets/icons and a custom accessible ActivityNavButton rather than host-colored primary buttons.

## Semantic palette

| Role | Light direction | Dark direction | Purpose |
| --- | --- | --- | --- |
| Meridian Ink | #202B37 | #F5F7FA text | Main body text and scientific identity |
| Mineral Blue | #3B5B88 | #98BCD5 | Primary action and navigation selection |
| Archive Amethyst | #6957A6 | #B4A0E4 | Evidence and keyboard focus |
| Clay Copper | #9B6042 | #E4A880 | Discovery and scientific data role |
| Warm Paper | #F5F4EF | #111B26 canvas | Long-session writing and analysis canvas |
| Dark Navigation | #263245 | #172638 | Persistent rail with #C7D6E1 foreground |

Theme also defines surface, raised surface, muted text, divider, focus, success, warning, danger, reader canvas, tab strip and four scientific-data roles. High contrast overrides these roles with black/dark surfaces, white text/borders, yellow selection accent and cyan focus. Color is never sufficient by itself: selected activity also changes shape/border/indicator, and scientific charts require labels/data tables.

The Rust contrast test in crates/researchweave-desktop/src/display_contrast.rs audits primary text, accent, evidence, copper, and navigation rail foreground/background pairs against 4.5:1. Light primary-action text contrast is about 6.9:1 and dark accent on its normal surface about 7.3:1. This is a token audit, not a rendered WCAG certification.

## Layout and density

Spacing uses semantic Theme space tokens. Research surfaces use a persistent activity rail, optional contextual navigation, a workbench header/command center, an object strip, central task surface and optional inspector. At large text scale or narrow width, contextual sidebars/inspectors collapse completely and the command center remains the route to hidden destinations.

The activity rail uses stacked icon-over-label tiles so long names do not truncate. The selected activity uses Mineral Blue outline/indicator plus a surface change. Hover styling is now a semantic rail token and status text uses an accessible navigation foreground instead of a dark-on-dark surface token. Historical resize harness results predate this palette; they must be rerun.

## Typography and controls

Current typography is system-font based for cross-platform availability. Heading, metadata and body sizes scale with Theme.ui-scale; the preference range is 80–200 percent. Native text fields/editors are retained for platform semantics. Custom controls must provide accessible role/name/action, visible focus and keyboard activation.

The manuscript workspace now has a taller paper-colored central writing area (minimum 370px, preferred 560px) with margins. It still keeps save/inspect actions separate from export actions, and bounds operation receipts in a scrollable panel. The notebook text area is taller. This remains a plain-text editor; complete Word-like pages and rich formatting are future product work.

## Accessibility acceptance

New interactive components must provide a meaningful UIA/accessibility role and label, keyboard activation, visible focus, and non-color status cues. At minimum, affected screens are tested at ordinary size, minimum supported size and 200% application text scale. Screen-reader certification still requires real NVDA/VoiceOver/Orca evidence on the corresponding native platform.

## Current visual evidence

- docs/verification/rust-rewrite/activity-rail-redesign-v3.png: minimum-size light theme, all six activities visible and non-overlapping.
- docs/verification/rust-rewrite/activity-rail-200pct.png: 200% high-contrast rail and Preferences state.
- docs/verification/rust-rewrite/manuscript-docx-ui-v5.png: manuscript editor with visible versioning actions and four export formats after DOCX generation.

## Open design-system work

Some general-purpose Slint native buttons still inherit host accent styling and may disagree with Mineral Blue; this needs native GUI review. Pre-change screenshots and original branding artwork remain historical evidence and have not been regenerated for Meridian. Advanced workspace-specific shells (page-oriented rich editor, statistical data grid/results split, qualitative coding panes, reference three-column view, knowledge graph and source-grounded AI view) remain product work and must reuse these semantic tokens instead of copying competitor branding.
