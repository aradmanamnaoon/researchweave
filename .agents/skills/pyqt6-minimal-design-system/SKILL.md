---
name: pyqt6-minimal-design-system
description: Design or implement a coherent, restrained PyQt6 research desktop visual system with reusable spacing, typography, tokens, widgets, and interaction states. Trigger on visual consistency, desktop layout, and theming; do not substitute for architecture or accessibility audits.
---

# PyQt6 minimal design system

## When to apply

Activate for research desktop UI visual design, theming, toolbar density, document reading surfaces, dialogs, panels, tables, and control consistency. The objective is a calm interface that accommodates dense scientific work while remaining approachable for first-time researchers. Request screenshots or live UI observations, target OS, expected font scaling, representative content sizes, and current palette. Deliver a documented token set, a few reusable primitives, and a visible before/after workflow. Treat branding references as constraints, never as justification for illegible or decorative controls.

## Build a token vocabulary

1. Inventory repeated colors, spacing, radii, border styles, typography, icon treatments, and component heights. Choose semantic roles instead of arbitrary CSS-like hex choices: window background, raised surface, reading surface, interactive surface, primary text, muted text, accent, separator, focus, warning, error, selection, disabled.
2. Define a spacing scale such as 4, 8, 12, 16, 24, 32 logical pixels and use it consistently in QLayout margins, spacing, item delegates, and forms. Use a compact density profile for datasets and a comfortable profile for reading; don't hardwire one density into every screen.
3. Establish typography roles for window title, section title, body, metadata, button, monospace numeric data, and long-form reading. Prefer QFont family fallbacks available on all target systems and use point or scalable units where appropriate. For tables, align comparable numbers right and use locale-aware or explicitly scientific formatting based on task context.
4. Implement theme palettes through QPalette and small scoped QSS rules. Keep widget object names stable if style targeting is needed; avoid global selectors that unexpectedly restyle dialogs or third-party components. Test both light and dark variants if the application supports both, accounting for native dialog behavior.
5. Expose selected state, hover, keyboard focus, pending, error, empty, readonly, and destructive affordances in component specifications. Color alone cannot encode provenance confidence, job failure, or required fields. Use text, icons, and accessible names together.

## Compose meaningful research surfaces

Anchor the application in a navigable work area with a project/workspace switcher, clear current research context, persistent task status, and discoverable search or command access. Organize complex authoring screens around a readable center canvas with collapsible context panels. Apply progressive disclosure: expose core reading and writing actions, with advanced reproducibility controls in clearly named settings or expandable inspectors.

Tables need more than a visual row color. Specify header hierarchy, sorting cues, resizable columns, row actions on selection/focus, frozen identity column where justified, empty and loading states, and export affordance. For long citations and DOI values, support copy and inspect without forcing horizontal window growth. Never truncate a scientific unit or a minus sign silently. Use status badges sparingly and make semantic distinctions in plain language.

Forms must label expected units, optionality, defaults, validation location, and consequences of execution. Keep error text adjacent to the field and reserve space to avoid severe layout jumps. Standardize major dialog patterns: destructive confirmation with object name and scope; import preview with count, file types and exclusions; analysis setup with explicit variables and missing-data decisions; export with format and reproducibility manifest options.

## Implement with PyQt6 patterns

Centralize token constants in a dedicated theme module; translate semantic tokens into QPalette, QFont, QIcon, QSizePolicy, and QSS deliberately. Create reusable constructors or subclassed composites for section headers, inline alerts, empty states, status rows, labeled controls, and icon buttons. Keep component APIs based on meaning, such as kind='danger', rather than passing raw hex strings. Use SVG icons with the necessary rights and predictable stroke size; ensure icons are legible on high DPI monitors and can inherit or explicitly take theme color.

Use QSplitter for resizeable research panes and persist user adjustments. Set sensible stretch factors and minimum sizes; verify there are no fixed widths that make an ordinary 1366-pixel laptop unusable. Preserve keyboard operation and Qt native behaviors where they matter. Prefer clear labels over mystery icons for rare or consequential actions; show keyboard shortcuts consistently.

## Detect failures before shipping

Check the application with zero data, five items, and ten thousand rows; narrow and wide windows; 100%, 150%, and 200% scaling; very long article titles, multilingual text, and missing fonts. Open menus and modal dialogs under both themes. Verify selection and keyboard focus remain distinct. A beautiful empty screenshot is not sufficient: test a filled data grid, an exception, a progress state, and a workflow with unsaved changes.

Do not overuse frosted glass, gradients, animation, icons, or custom title bars when they interfere with platform semantics. Avoid low-opacity gray on gray; enforce measured contrast and visible focus in partnership with the desktop-accessibility skill. Never rely on CSS pseudo-elements unsupported by Qt style sheets or blindly paste browser CSS into QSS.

## Acceptance evidence and references

Report actual changed primitives, screenshots at representative densities, scaling tests, and any known native-platform differences. Gate success on consistent spacing and typography, no clipped text, recognizable hierarchy, keyboard-visible focus, accessible touch/mouse target sizes, and preserved behavior under system font changes. Use [Qt Style Sheets](https://doc.qt.io/qt-6/stylesheet-reference.html), [QPalette](https://doc.qt.io/qt-6/qpalette.html), [QStyle](https://doc.qt.io/qt-6/qstyle.html), [QFont](https://doc.qt.io/qt-6/qfont.html), and [Qt High DPI](https://doc.qt.io/qt-6/highdpi.html) as implementation references; consult [WCAG 2.2](https://www.w3.org/TR/WCAG22/) for text and focus targets. Do not change scientific data, calculation defaults, or export meaning as part of a cosmetic pass. Treat user-supplied icons, fonts, and illustrations as licensed assets that need provenance and cannot be silently re-distributed.
