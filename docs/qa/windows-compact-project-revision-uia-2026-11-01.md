# Windows installed native UIA: missing compact project revision

## Evidence

- Source `05ab920af5269114435b9c0193e565cbd410fccb`, native run `41297206361`, installed Windows job `124824087155` **failed**.
- Downloaded `rust-windows-native-smoke-diagnostics` into `target/qa/archived-05ab920-windows`.
- `windows-installed-uia.log` passed first-run, native folder dialogs, Unicode edits, question preview/record, Protocol one-time immutable baseline and physical Markdown digest, Windows PDF picker, PDFium reader navigation, and the actual native Protocol JSON frozen/unfrozen UIA inspection.
- Next error at `windows-uia-smoke.ps1:320`: `Project revision was not exposed by the native workbench header`.
- Real `windows-installed-uia.png` is **886 x 567**. It shows the References workspace and a successfully approved reference registration, but no header project revision. `Get-VisibleProjectRevision` requires a native Text control whose name ends in ` · r<N>`.

## Cause and correction

The existing full project header Text in `crates/researchweave-desktop/ui/main.slint` is deliberately visible only when `root.width >= 1100px` (and theme scale <=150%). An 886 px installed UI cannot expose that hidden control. This is a **responsive presentation/accessibility omission**, not evidence of a wrong project SQLite revision.

The compact object-tab strip now independently renders `Project · r<revision>` when a project is open at width under 1100 px, using the real same project-revision property and a native accessible Text label. The wide title+revision display remains unchanged, and the compact indicator is placed in the previously open right side of the object strip rather than crowding the command bar. The strict UIA assertion remains unchanged: it must read the native visible revision and agree with durable project state.

## Still required

Slint compilation and **installed Windows UIA rerun on the exact changed source** must prove the label is actually in the accessibility tree and the remainder of the native F14/F03/F05/Protocol suite passes. A source-only text change does **not** clear the release gate.
