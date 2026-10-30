# Statistics method navigation at 200% / 900×620

**30 October 2026 · private real native Linux UI receipt; synthetic local project.**

The [dedicated reproduction harness](../../../../scripts/ux/isolated-xvfb-statistics-narrow-200.sh)
uses actual Slint Preferences actions to persist 200% text scale, resizes the
application to 900×620, enters Statistics through the command palette, and
scrolls using native pointer events until the method selectors materialize.
It inspects the actual AT-SPI accessible controls and rejects controls with a
zero rectangle or rectangles outside the visible window.

The final patched executable **PASS** all three method selector groups:
Descriptives/Frequency/Correlation, Welch t, and Linear model. In the earlier
unpatched screenshot the Correlation control extended beyond the right edge.
The final bounded sizing keeps it within the viewport; the long dataset
section heading wraps. The method controls are reached by scrolling rather
than falsely being described as visible when the page first opens.

Evidence: [initial viewport](statistics-200-narrow.png),
[scrolled method controls](statistics-200-narrow-after-scroll.png),
[native rectangles and scroll attempts](accessibility.json),
[window dimensions](geometry.txt), [source fingerprints](source-hashes.txt).

Exact current-source fingerprints: Linux executable SHA-256
`58201b8455f07838b2a87cbbf4d96d2a85c1c7eea5191e99830d98d9d078c626`;
Rust host `37953f0d4d813545d294e6f0862237c4b938087019c6b68729eae6081b69cc36`;
Slint `5b258d8e5ea4545426c302df40a200b5085ae43e6a3437477f801ca17217ef08`.
Original disposable receipt:
`/home/saba/researchweave-gui-audits/stats-final-narrow-20261030-r1/`.

This test covers Linux native layout and AT-SPI accessibility only. It does
not establish Windows UIA, macOS VoiceOver, actual screen reader speech, or
that every form action has been run at 200% scale. It does not authorize a
new public release.
