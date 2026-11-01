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

### Follow-up on `939f27c`

Exact-source candidate `41300357835` repeated the same UIA failure after PDFium and Protocol smoke. Its captured `windows-installed-uia.png` again shows the actual 886x567 References window, with the right object-tab strip and content horizontally clipped while the left activity sidebar and existing project title remain visible. Merely adding a compact Text conditional on `root.width < 1100px` at the far right did not solve the installed native accessibility/viewport failure. The original assertion has **not** been weakened.

The production revision label is therefore moved into the **always-present left activity sidebar**, immediately beneath the displayed project title, independent of root-width/layout thresholds. The failed conditional object-strip revision is removed. The actual project revision still comes from the existing trusted native `root.project-revision` property and has an exact accessible label `Project · r<revision>`. This is a distinct source change from `939f27c` and requires its own installed Windows native UIA positive evidence.

## Still required

Slint compilation and **installed Windows UIA rerun on the exact changed source** must prove the label is actually in the accessibility tree and the remainder of the native F14/F03/F05/Protocol suite passes. A source-only text change does **not** clear the release gate.
