# Windows F14 native keyboard reachability after expanded review form

## Exact observed failure

- Source: `5d32fa053e0a50829d2ec53c3ee88eef0aff4608`, hosted native candidate `41308671031`, Windows 2022 installed x64 UIA.
- Preserved original artifact: `target/qa/archived-5d32fa0-windows/windows-installed-uia.log` and `windows-installed-uia.png`.
- Confirmed passed through first-run creation, Unicode manuscript, saved protocol, immutable freeze and physical receipt, native PDF file picker, native PDFium document navigation and reference registration. The earlier narrow-sidebar `Project · r4` readback no longer fails.
- New failure at `windows-uia-smoke.ps1:1220`: `FocusByTab` exhausted a budget of 12 native Tab keystrokes seeking `Copyable reference duplicate candidate or decision details`. The reported final focused element was **`Record explicitly approved reference dedup decision`**, and the screenshot shows the expanded review form/panel immediately above the offscreen copyable receipt. This is a genuine **incomplete keyboard navigation proof**, not evidence that the reference scan wrote an event, that a candidate was fabricated, or that the native TextEdit is permanently inaccessible.

## Bounded source repair

The new F14 form has two reference-ID editors, candidate SHA editor, rationale editor and six separate decision controls between the scan and the read-only receipt. The original 12-tab budget is insufficient for the observed installed layout. The first scan receipt now allows **at most 28 actual native Tab stops**; other result receipts allow a bounded **16** stops after their real predecessor buttons. The same `FocusByTab` helper still obtains actual Windows UI Automation **FocusedElement** and requires exact `ControlType.Edit` and accessible name before reading the real `ValuePattern` content. No direct database read or offscreen `Named` lookup replaces native keyboard focus. All scan/preview/record/no-write/refusal assertions remain unchanged.

Local PowerShell 5.1 AST parsing, the project-revision Unicode contract and the previous preview pipeline contamination contract passed. **Full installed Windows UIA success is not yet proven** and an exact-source native run must pass the entire F14 scan, negative self-alias, positive keep-separate/history/reconsideration and persistence scenarios before any release gate may be called complete. If expanded tabs still fail, inspect the new exact screenshot/tab trace and fix real Slint focus/viewport semantics rather than bypassing UIA.
