# Windows installed UIA — protocol preview false-negative root cause

## Independent evidence

- Candidate `c44289b2`, archived hosted native run `41290047655`, artifact
  `rust-windows-native-smoke-diagnostics/windows-installed-uia.log`:
  protocol create, Markdown export and actual persisted read-only freeze JSON
  inspect passed, then the script raised
  `Local protocol freeze did not provide a separate non-mutating preview`.
- The same artifact's `windows-installed-uia.png` screenshot visibly shows
  **LOCAL FREEZE PREVIEW ONLY** in the actual read-only native Protocol
  preview editor after clicking Preview. That is evidence the screen rendered
  the expected preview; it does *not* independently prove its receipt hash.

## Proven PowerShell 5.1 harness defect

`Read-VisibleProtocolFreezePreviewOutcome` retrieves a real UIA `ValuePattern`
from the read-only Slint TextEdit and returns its string content. Before this
fix it also emitted a `Write-Output` diagnostic into the *same success pipeline*.
The caller assigned the result to `$freezePreview`, so the variable became a
two-element `Object[]` (diagnostic + actual editor value), not a string.

PowerShell's `-notlike` operator with an array left operand returns all
**non-matching elements**; the diagnostic did not contain
`LOCAL FREEZE PREVIEW ONLY`, so the assertion raised a false failure even
though the second element matched. This is independent of UI accessibility
materialization. The new `Write-Host` sends the diagnostic to the host
without contaminating the returned data value.

Reproduced locally in Windows PowerShell 5.1 using a synthetic function:

```text
BROKEN_TYPE=Object[]
BROKEN_FALSE_FAILURE=True
FIXED_TYPE=String
FIXED_FALSE_FAILURE=False
PS5_PARSE_ERRORS=0
```

The installed real UIA `ValuePattern`, read-only enforcement, exact preview
text and duplicate-freeze negative checks remain intact and unmodified.
**Not a hosted native pass** until the replacement source's Windows UIA job
completes successfully.
