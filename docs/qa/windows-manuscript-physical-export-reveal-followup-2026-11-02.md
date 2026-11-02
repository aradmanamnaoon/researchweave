# Windows installed manuscript physical-export field: second native regression

Exact candidate `250708ddada3a0a6a5357fb7305a6fcd5910c144`,
[native run 41395135031](https://github.com/aradmanamnaoon/researchweave/actions/runs/41395135031),
Windows job `125117933604`, archived diagnostic artifact
`rust-windows-native-smoke-diagnostics`:

- Installed EXE/NSIS CLI, real PDF viewer and page pixel/source-SHA checks,
  reference/review/PRISMA, dataset import, statistics, physical analysis
  report and immutable manuscript Markdown preparation all passed.
- `windows-installed-uia.log` reports the real `Manuscript export destination
  path` Edit at bounds `511,757,713,32`, while the intersection of the actual
  manuscript work area, window and monitor ends at `y=728`.
- The previous UIA ScrollPattern/right-edge wheel attempt did not reveal
  the field, so the strict Windows automation refused to write the export
  destination or claim a physical Markdown save.

The native UIA reveal helper now also attempts the actual Edit's
`ScrollItemPattern.ScrollIntoView` if supported, tries a finite wheel scroll
inside both the outer Slint ScrollView padding gutter and content area (rather
than the formerly ineffective extreme-right edge), and only then tries a
finite native PageDown sequence. Every branch must still find the exact
`Edit` accessibility name, non-offscreen state, at least 100×18 visible pixels
inside the real manuscript work-area/window/monitor intersection, and actual
keyboard focus before `ValuePattern.SetValue`.

The existing physical file creation, source content, SHA-256 receipt, consumed
approval and non-overwrite refusal assertions are unchanged. A source-level
Python contract protects these checks. Passing a parser or source contract
does **not** prove this actually scrolls on the installed Windows app.

**Status:** pending a fresh, exact-source Windows installed UIA run; fail
closed if the field remains inaccessible. No stable release or download
announcement is authorized by this document.
