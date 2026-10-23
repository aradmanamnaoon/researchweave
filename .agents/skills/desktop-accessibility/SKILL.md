---
name: desktop-accessibility
description: Audit and remediate keyboard navigation, screen reader semantics, readable typography, contrast, focus, and assistive technology behavior in PyQt6 desktop research applications. Use for accessibility reviews and new accessible UI components, not for generic visual redesign.
---

# Desktop accessibility

## Activation, goals, and evidence

Use when a new interactive desktop surface ships, accessibility is requested, or users cannot navigate with a keyboard, screen reader, magnifier, or higher contrast/font scaling. Desktop guidance must be adapted from WCAG 2.2 principles rather than assuming every browser-specific criterion maps directly to Qt. Start with target platforms, supported assistive technologies, user flows, existing accessibility defects, and a reproducible test environment. Deliver a prioritized defect list with severity, reproduction steps, code changes, and verified keyboard and assistive technology results. Do not report a pass based solely on static code inspection.

## Walk a real task as a keyboard user

Pick representative flows: open project; add a PDF; search references; edit extraction fields; run a statistical analysis; inspect a warning; save and export. With the mouse disconnected, verify Tab and Shift+Tab order, Space and Enter semantics, Escape and dialog dismissal, focus restoration after dialogs, and access to every action normally exposed on hover. Use native control conventions: arrow keys in lists/trees, F2 where appropriate to edit, Ctrl+F for search, and recognizable menu accelerators. Document shortcuts and avoid hijacking common OS/editor commands.

Every QDialog needs deliberate initial focus, a descriptive accessible title, and a predictable return-focus target on close. Dynamic panels must not silently move focus as asynchronous results arrive. If a background import adds a result table, keep current typing uninterrupted and offer a status notification and an explicit route to inspect results. On destructive confirmations, focus the safe option initially. Provide a clear way to exit nested widgets or command palettes without keyboard traps.

## Expose meaning to assistive technology

Set accessibleName for unlabeled icon buttons and controls, accessibleDescription for complex controls whose purpose or valid range is unclear, and label buddies for corresponding QLabels and widgets. Avoid duplicate or misleading names such as five 'Open' buttons without context. Use standard Qt widgets and QAccessible support where possible before creating custom painted controls. For custom delegates, define accessible equivalents and make states such as selected, expanded, busy, read-only, invalid, and checked available through relevant APIs. Ensure tables announce header labels and logical indices; represent units in column descriptions.

Use readable error language coupled to the field and a persistent summary for forms with multiple failures. Screen-reader users must be able to find validation messages after submission and understand how to correct them. Status changes cannot rely solely on a brief toast that disappears before it can be read; put job results in a navigable status/history area. Test an actual screen reader such as NVDA on Windows, VoiceOver on macOS, or Orca on Linux for supported platforms; document exact versions where practical.

## Contrast, text, motion, and cognition

Measure text contrast against its actual background, including selection and disabled-looking states: aim at least 4.5:1 for ordinary text and 3:1 for large text, with controls and focus indicators sufficiently distinguishable. Check high-contrast OS themes, 200% zoom or equivalent application scale, and user font preferences. No essential text may clip or overlap when labels wrap. Preserve scientifically meaningful special characters such as ±, μ, subscripts, minus signs, and superscripts in reading order and accessible descriptions.

Do not convey p-values or statistical significance only by red/green heatmaps. Provide numeric labels, axis descriptors, uncertainty, units, source citations, and textual interpretations; make charts keyboard-discoverable through companion data tables where practical. Reduce or disable decorative motion when an OS preference requests it, and never use flashing status to attract attention. Use short procedural instructions, clear language, and recoverable operations for beginners; advanced controls should remain findable through accessible search and documentation.

## Engineering workflow and common traps

Inspect widget hierarchy, focusPolicy, setTabOrder, QShortcut/QAction bindings, QAccessible exposure, size policies, and popup lifecycles. Prefer one semantically correct component implementation over patching dozens of individual screens. Test both an empty widget and a populated, error, loading, or disabled state. Automated checks can identify unlabelled controls and detect certain contrast violations; they cannot establish screen-reader usability or meaningful tab order.

Avoid turning every static label into a focus stop; overlong tab sequences harm navigation. Avoid redundant narration for every table cell when headers already explain the data. Avoid focus hijacking by timers, progress callbacks, or validation updates. Do not remove a visible focus ring because mouse screenshots look cleaner. Allow assistive technology to read a long citation or research title without truncation being the only available representation.

## Acceptance gates, references, and boundaries

Record a keyboard-only pass for each critical journey and one real screen-reader pass on every supported desktop OS that can be exercised; explicitly flag untested combinations. Check full keyboard reachability, visible focus, non-color status, announced validation, no clipped text at scaled fonts, meaningful chart alternatives, and recovery from errors. Back changes with targeted Qt widget tests and issue-linked manual scripts. Follow [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/), [WAI Accessible Rich Internet Applications Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) for interaction concepts only, [QAccessible](https://doc.qt.io/qt-6/qaccessible.html), [Qt Accessibility](https://doc.qt.io/qt-6/accessible.html), and platform assistive technology guidance. Protect private research context when screenshots or screen-reader logs are shared; use synthetic data by default. Never claim legal compliance merely because basic checks passed, and do not replace native OS accessibility interfaces with an untested custom layer.
