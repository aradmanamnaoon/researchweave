# PowerShell 5.1/7 static and executable function extraction; no installed GUI.
$ErrorActionPreference = 'Stop'
$scriptPath = (Resolve-Path (Join-Path $PSScriptRoot '../../crates/researchweave-desktop/tests/windows-uia-smoke.ps1')).Path
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw ('Windows UIA syntax error: ' + ($errors | Out-String)) }
$functions = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Parse-NativeProjectRevision'
}, $true))
if ($functions.Count -ne 1) { throw 'Expected exactly one bounded project revision parser' }
$functionSource = $functions[0].Extent.Text
if ($functionSource -match '[^\x00-\x7f]' -and $functionSource -notmatch 'U\+00B7') {
    throw 'Revision parser changed to a non-ASCII literal vulnerable to PowerShell 5.1 UTF-8 no-BOM decoding'
}
. ([scriptblock]::Create($functionSource))
$middleDot = [char]0x00B7
$legacyMojibake = ([char]0x00C2).ToString() + $middleDot
$positive = @(
    "Project $middleDot r4",
    "Project $legacyMojibake r4",
    'Project - r0',
    'Project - r123456'
)
foreach ($candidate in $positive) {
    $value = Parse-NativeProjectRevision $candidate
    if ($null -eq $value -or $value -lt 0) { throw "Valid native revision refused: $candidate" }
}
foreach ($candidate in @(
    'Other - r4', 'Project revision 4', 'Project - r4 and r5',
    'Project - r-1', 'Project - r4.0', 'Project xyz1234 r4'
)) {
    if ($null -ne (Parse-NativeProjectRevision $candidate)) {
        throw "Non-project revision label accepted: $candidate"
    }
}
$revisionReader = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-VisibleProjectRevision'
}, $true))
if ($revisionReader.Count -ne 1) { throw 'Expected exactly one installed native revision inspector' }
$readerSource = $revisionReader[0].Extent.Text
foreach ($required in @('Parse-NativeProjectRevision', 'BoundingRectangle', 'Children $Window', 'ControlType', 'Write-Host')) {
    if (-not $readerSource.Contains($required)) {
        throw "Revision inspector lost live visibility/source invariant: $required"
    }
}
$readerCommands = @($revisionReader[0].Body.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst]
}, $true))
if (@($readerCommands | Where-Object { $_.GetCommandName() -eq 'Write-Output' }).Count -gt 0) {
    throw 'Project revision inspector must not contaminate its scalar result with pipeline diagnostics'
}
Write-Output 'WINDOWS_UIA_PROJECT_REVISION_NATIVE_LABEL_PARSER_CONTRACT_OK'
