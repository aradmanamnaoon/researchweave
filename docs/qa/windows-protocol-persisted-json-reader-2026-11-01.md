# Windows installed Protocol freeze JSON accessibility — 2026-11-01

**Observed candidate:** `1ab974ac3e8cb97ef4e0f0aab4dffed0b3bfd693`, [run 41281278706](https://github.com/aradmanamnaoon/researchweave/actions/runs/41281278706), Windows installed job `124775885300`.

The real Windows installer, PDFium native smoke, disposable project initialization, verification and user-data retention all passed. Installed UIA also created a project, exercised Persian multiline text, recorded a protocol and its immutable local baseline, and confirmed an actual physical Markdown receipt with SHA-256 and no overwrite. It then failed inside `Read-VisibleProtocolFreezeReceipt`:

```text
UIA_PROTOCOL_FREEZE_VIEWPORT_RECOVERY: native receipt-save focus, keyboard PageDown (no save invoked)
UIA_FAILURE: The actual persisted protocol freeze JSON was not exposed after bounded scrolling of the native Protocol ScrollView
```

The diagnostic screenshot SHA-256 is `F5E643E077A67DE093C1D6802737B3FD2DFAF1E11D0A7420F5C4AEEFF21C9DF4`. At approximately 886x600 (high scaling), the local freeze card starts near the bottom of the viewport, while its full JSON text is below the receipt-save row. Windows AccessKit does not expose this offscreen Text; Tab/PageDown from the Save button did not bring it into the live tree. The persisted freeze was **not** proven invalid; this was a native accessibility/readback failure.

## Corrective source

The Protocol native UI now provides a fixed-height, read-only, selectable `TextEdit` immediately following **Inspect frozen baseline**, bound directly to the same `root.protocol-freeze-status` value that the Rust trusted host populates from persisted `protocol.freeze_inspect` history. It is labeled `Read-only inspected protocol freeze JSON` and improves keyboard access and inspectability. The previous full Text receipt remains in the lower panel for existing Linux accessibility and scientific acceptance.

The Windows installed UIA script uses a bounded actual Tab traversal from the focused Inspect button to this native read-only editor, checks `ValuePattern.IsReadOnly`, retrieves actual `ValuePattern.Current.Value`, strictly parses JSON and still verifies exact protocol ID, `local_only=true`, `external_registration_verified=false` and a genuine boolean frozen state. The callers continue independently requiring the detailed before/after freeze version, event, and digest fields. No JSON is reconstructed from assertions, copied from test fixtures, or read directly from SQLite.

This change requires a fresh exact-source hosted installed Windows UIA pass; only local Slint compilation, PowerShell parsing, source tests and previous diagnostics can be claimed before then. Keep the release gate closed until the actual `UIA_PROTOCOL_FREEZE_JSON_READ` marker and all subsequent native workflow assertions pass.
