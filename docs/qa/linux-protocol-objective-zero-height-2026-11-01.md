# Protocol objective became zero-height in native Linux GUI

**Status: source repair, pending exact-source hosted native acceptance.**

Private Linux Xvfb/AT-SPI replay exercised the installed-style desktop
against a disposable synthetic project. The same actual UI successfully
recorded a protocol, stored and inspected its immutable local freeze,
exported a physical Markdown receipt, verified its SHA-256, refused an
overwriting Save and refused a duplicate freeze. The subsequent valid
post-baseline amendment could not edit the Protocol objective.

An audited screenshot, `protocol-amendment-objective-reveal-diagnostic.png`,
showed title, design, author and amendment rationale inputs but **no visible
objective editor**. The objective's *real accessible component* returned
`x=373, y=305, width=883, height=0`. More than twenty bounded wheel-up
actions revealed the top of the form but did not create a usable editor.

Production root cause: the `protocol-objective := TextEdit` in
`crates/researchweave-desktop/ui/main.slint` had no minimum height inside
the increasingly long Protocol ScrollView. The field collapsed during the
real native layout; this was not merely an AT-SPI queryText limitation.
The fix specifies an explicit multiline minimum, preferred and maximum
height (96/112/176 px), allowing the outer page to scroll.

The private QA still refuses an offscreen or zero-height edit; it records a
real screenshot and accessibility-tree checkpoint immediately before trying
the objective, then attempts a revision-bound amendment via native controls
and checks immutable baseline provenance. This is an important negative
test: a visible label or an accessibility node alone is not a functional
editor.

**Not yet established:** the newly compiled field's actual height, successful
post-freeze amendment through the new layout, and all-platform installed
acceptance. Local recompilation was interrupted when the Windows C: drive
approached zero free space. A targeted removal of the disposable Rust
incremental compilation cache recovered 2.3+ GiB; other user files and
projects were not removed. Continue with hosted exact-source checks, never
invent a native screenshot or a passing amendment.
