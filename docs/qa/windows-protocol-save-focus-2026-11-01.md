# Windows installed Protocol freeze JSON viewport recovery

## Observed failure

The exact-source [native release candidate 41277449988](https://github.com/aradmanamnaoon/researchweave/actions/runs/41277449988), commit `e9d59d10c1ef3034c16bb1b6872f912fe65fd9b8`, passed Windows native build, installer creation, PDFium smoke, installed CLI workflows and user-data-retention checks, but **failed installed Windows UI Automation** in `Read-VisibleProtocolFreezeReceipt`.

The archived `rust-windows-native-smoke-diagnostics/windows-installed-uia.log` reports a bounded Tab trace beginning at **Inspect local protocol freeze receipt** and continuing through **Prepare local protocol baseline receipt Markdown** and **Save verified local baseline receipt without overwrite**, without ever exposing the offscreen **Local protocol baseline receipt destination path** Edit. The previous test required focusing that Edit; Tab proceeded into the outer navigation and the assertion failed. This is directly observed native accessibility behavior, not a claimed protocol-freeze data error.

## Fail-closed correction

The `Read-VisibleProtocolFreezeReceipt` fallback now uses the real immediately following **Save verified local baseline receipt without overwrite** *button* as a bounded keyboard focus target (at most five native Tab transitions) instead of seeking the lazily inaccessible path Edit. It **never invokes Save**. From that verified focus anchor it issues bounded native PageDown to locate the exact `Protocol local freeze status ` accessibility Text containing the JSON returned by the persisted protocol audit, and validates identity, local-only state, boolean `frozen`, frozen version, immutable snapshot/event hashes, no duplicate freeze and no overwrite as before.

The structural JSON parser, field checks and negative assertions were not weakened. If the button cannot be focused, the actual native JSON does not appear, its structure is invalid or the protocol audit is inconsistent, UIA still fails. The next exact-source installed Windows candidate must prove this fix against an actual packaged executable; PowerShell AST parsing and source checks are not equivalent to installed GUI acceptance.
