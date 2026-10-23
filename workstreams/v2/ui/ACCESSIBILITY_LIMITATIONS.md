# Accessibility limitations and evidence

Automated evidence covers accessible names/descriptions, keyboard-focusable controls, text alternatives for charts, theme token contrast, high-contrast theme behavior, narrow layouts and 100/150/200% scale checks. The screenshot harness contains synthetic PROTOTYPE captures and alt descriptions; it is evidence of offscreen Qt rendering only.

Not observed and therefore **not claimed**:

- NVDA on Windows.
- VoiceOver on macOS.
- Orca on Linux.
- Native screen-reader live-region/error announcements.
- Complete native focus-order/focus-restoration behavior across every dialog/project switch.
- Real multi-monitor geometry and native 100/150/200% DPI behavior.
- Native Linux/macOS rendering.
- A full native keyboard-only journey. The Windows Qt offscreen long QTest sequence crashes, while command registration/routing and accessible names are deterministically tested.

The UI must retain textual/non-color state indicators and chart table/text alternatives during integration. Native QA is required before any accessibility conformance claim.
