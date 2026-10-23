# Accessibility limitations and evidence

Automated evidence covers accessible names/descriptions, keyboard-focusable controls, textual chart alternatives, theme contrast, high-contrast mode, narrow layouts and 100/150/200% scale checks. An in-app screen-focus memory/restoration mechanism is present, but native OS focus ownership is intentionally not inferred from offscreen Qt.

Not observed and therefore **not claimed**:

- NVDA on Windows.
- VoiceOver on macOS.
- Orca on Linux.
- Native screen-reader live-region/error announcements.
- Complete native focus-order/focus-restoration behavior across dialogs/project switches.
- Real multi-monitor geometry and native 100/150/200% DPI behavior.
- Native Linux/macOS rendering.
- A full native keyboard-only journey. Deterministic command registration/routing and accessible naming are tested; native key delivery remains release QA.

The UI retains textual/non-color state indicators, text/table chart alternatives, screen/context help and readable recovery/error text. Native assistive-technology validation is required before any accessibility conformance claim.
