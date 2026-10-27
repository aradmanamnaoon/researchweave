# ResearchWeave UI/UX audit

Snapshot: 2026-10-26. Evidence comes from the live Rust/Slint application on Windows through UI Automation plus real window screenshots. This is an incremental audit, not a declaration that every destination is visually complete.

| Surface / issue | Observed defect | Change | Evidence | Status |
| --- | --- | --- | --- | --- |
| Main activity rail | Native primary buttons inherited host accent, long Synthesize/Automate labels squeezed horizontally, and lower choices could crowd at large scale. | Added custom icon-over-label ActivityNavButton with Research Teal selected tile/indicator, keyboard/UIA action, focus border and scale-aware width/height. | activity-rail-redesign-v3.png; activity-rail-200pct.png; resize harness and broad UIA. | FIXED_WINDOWS |
| Narrow shell | Invisible contextual panel continued consuming layout width, pushing task content off screen. | Responsive state now collapses hidden panel widths to zero while keeping global keyboard-focus IDs structurally available. | Minimum screenshot and 800x600 UIA command-center path. | FIXED_WINDOWS |
| 200% scale | Rail/top metadata clipped and scale controls became unreachable in earlier render. | Context sidebar collapses at large scale, metadata hides when necessary, activity rail widens/uses stacked labels, Preferences remains scrollable. | activity-rail-200pct.png plus restart persistence assertion. | FIXED_WINDOWS |
| Manuscript export result | Raw DOCX base64 made the results text expand and visually compressed surrounding controls. | Desktop presentation removes nested data.base64 from visible JSON, reports encoded length instead, and bounds results in a scrollable panel. | manuscript-docx-ui-v5.png. | FIXED_WINDOWS |
| Manuscript actions | Export was Markdown-only and visually mixed with persistence actions. | Separate versioning action row from Markdown/DOCX/HTML/PDF export row. | manuscript-docx-ui-v5.png plus full UIA DOCX assertion. | FIXED_WINDOWS |
| Application identity | Rust shell/packaging lacked consistent icon treatment. | Window and native packaging now use the ResearchWeave brand assets; activity roots have original SVG icons. | Live screenshots; packaging files. | IMPLEMENTED_LOCAL |
| Statistics workspace | Descriptives-only UI hid the breadth of validated native analysis kernels; the first expanded stacked form also placed controls below Slint's clipped UIA viewport and the first accepted redesign still exposed dense raw JSON before key results. | Replaced the stacked form with an always-visible progressive-disclosure chooser over shared immutable dataset/revision context. Descriptives, frequency, Pearson, Welch t and HC3 OLS now render one focused form at a time; method-aware summaries surface key estimates, sample counts and immutable-revision provenance while retaining the full verified payload below. | `statistics-workbench-summary.png`; fresh full UIA executes all five methods; 26/26 desktop tests and medium/narrow/minimum resize suite pass. | FIXED_WINDOWS |

## Interaction/accessibility observations

The broad Windows UIA suite verifies named editable controls, Invoke semantics, Ctrl+K command access, Unicode text, six activity roots, compact navigation, async responsiveness, manuscript workflows, local AI/provider controls and persisted display preferences. The custom activity buttons expose button role, default accessibility action, accessible descriptions, TouchArea mouse activation and Enter/Space keyboard activation.

The resize suite now asserts each activity root is present, not off-screen and non-overlapping at requested 980x680, 820x640 and 760x560 outer sizes. Real Windows chrome/DPI produces slightly smaller client bounds; the acceptance criterion is reachable non-overlapping UI, not exact pixels.

## Open visual defects / unverified areas

- Native general-purpose buttons can still inherit the OS/Slint accent rather than Research Teal.
- The manuscript screen is still a structured plain-text editor, not a page-oriented rich-text Word-class editor.
- Statistics now has a populated-state screenshot audit and readable method-aware summary layer. Rich tables/plots/diagnostics for more advanced methods remain product work. Qualitative, references, AI, systematic-review and publishing workspaces still require dedicated populated-state screenshot audits as their richer shells land.
- Real NVDA, Windows forced-colors, macOS VoiceOver and Linux Orca passes remain open.
- Native macOS/Linux screenshots remain release-blocking for universal visual claims.
- Large tables, long PDFs, dialogs, context menus, loading/error/empty states and high-DPI OS scaling need dedicated screenshot matrices beyond the current application-level text scaling.
