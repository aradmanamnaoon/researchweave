# Strict Windows PowerShell 5.1/7 title-page native-preview parser regression.
# Extracts the actual UIA function, without launching or mocking a GUI pass.
$ErrorActionPreference = 'Stop'
$scriptPath = (Resolve-Path (Join-Path $PSScriptRoot '../../crates/researchweave-desktop/tests/windows-uia-smoke.ps1')).Path
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ('Windows UIA syntax error: ' + ($errors | Out-String)) }
$functions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Parse-NativeTitlePagePreview'
}, $true))
if ($functions.Count -ne 1) { throw 'Expected exactly one title-page preview parser' }
$source = $functions[0].Extent.Text
if ($source -match '[^\x00-\x7f]') {
    throw 'Title-page parser must not depend on UTF-8 source literals decoded as ANSI'
}
. ([scriptblock]::Create($source))
$dot = ([char]0x00B7).ToString()
$mojibakeDot = ([char]0x00C2).ToString() + $dot
$hash = 'a' * 64
$body = "Cortical memory networks`nAlex Doe | Lab One`nBea Nguyen | Lab Two"
$notice = 'Nothing has been saved or submitted'
foreach ($separator in @($dot, $mojibakeDot)) {
    foreach ($newline in @("`n", "`r`n")) {
        $candidate = 'UNSAVED TITLE PAGE ' + $separator + ' SHA-256 ' + $hash +
            $newline + $notice + $newline + $newline + ($body -replace "`n", $newline)
        $parsed = Parse-NativeTitlePagePreview $candidate
        if ($null -eq $parsed -or -not $parsed.Success -or
            $parsed.Groups[1].Value -cne $hash -or
            $parsed.Groups[2].Value -cne $notice -or
            -not $parsed.Groups[3].Value.Contains('Lab Two')) {
            throw 'Valid native F04 title-page receipt was refused or misparsed'
        }
    }
}
foreach ($candidate in @(
    ('UNSAVED TITLE PAGE - SHA-256 ' + $hash + "`n$notice`n`n$body"),
    ('UNSAVED TITLE PAGE ' + $dot + ' SHA-256 ' + ('b' * 63) + "`n$notice`n`n$body"),
    ('SAVED TITLE PAGE ' + $dot + ' SHA-256 ' + $hash + "`n$notice`n`n$body"),
    ('UNSAVED TITLE PAGE ' + $dot + ' SHA-256 ' + $hash + "`n$notice"),
    ('UNSAVED TITLE PAGE ' + $dot + ' SHA-256 ' + $hash + "`n`n$body")
)) {
    if ($null -ne (Parse-NativeTitlePagePreview $candidate)) {
        throw 'Malformed or misattributed native F04 title-page receipt was accepted'
    }
}
# The caller must still read the actual UIA ValuePattern and validate SHA-256
# from the body, its exact author/contact fields, and unchanged project revision.
$full = [System.IO.File]::ReadAllText($scriptPath)
foreach ($required in @(
    '$titlePagePreviewControl.GetCurrentPattern(',
    'Parse-NativeTitlePagePreview $titlePagePreviewText',
    '$actualDraftHash -ne $previewMatch.Groups[1].Value',
    '(Get-VisibleProjectRevision $window) -ne $titlePageRevisionBefore',
    'F04 title page preview lost an author'
)) {
    if (-not $full.Contains($required)) {
        throw "F04 native/UIA content, digest or zero-write invariant missing: $required"
    }
}
Write-Output 'WINDOWS_UIA_F04_TITLE_PAGE_EXACT_RECEIPT_PARSER_CONTRACT_OK'
