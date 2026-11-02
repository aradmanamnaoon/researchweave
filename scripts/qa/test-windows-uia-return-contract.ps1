# PowerShell 5.1 static QA: the UIA reader returns exactly one value.
# Does not open any window or interact with an installed application.
$ErrorActionPreference = 'Stop'
$scriptPath = (Resolve-Path (Join-Path $PSScriptRoot '../../crates/researchweave-desktop/tests/windows-uia-smoke.ps1')).Path
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath, [ref]$tokens, [ref]$errors
)
if ($errors.Count -ne 0) {
    throw ('UIA script has PowerShell syntax errors: ' + ($errors | Out-String))
}
$readers = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Read-VisibleProtocolFreezePreviewOutcome'
}, $true))
if ($readers.Count -ne 1) {
    throw 'Expected exactly one protocol preview UIA reader'
}
$commands = @($readers[0].Body.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst]
}, $true))
if (@($commands | Where-Object { $_.GetCommandName() -eq 'Write-Output' }).Count -ne 0) {
    throw 'UIA preview reader must not write diagnostics into returned preview data'
}
if (@($commands | Where-Object { $_.GetCommandName() -eq 'Write-Host' }).Count -lt 1) {
    throw 'UIA preview reader diagnostic is unexpectedly missing'
}
$details = @(
    $readers[0].Body.Extent.Text
)
foreach ($required in @('ValuePattern', 'IsReadOnly', 'Current.Value', 'return $value')) {
    if ($details[0] -notlike "*$required*") {
        throw "UIA preview reader is missing required native assertion: $required"
    }
}
function BrokenPipeline {
    Write-Output 'UIA_NATIVE_PROTOCOL_FREEZE_OUTCOME_READ_CHARS=200'
    return 'LOCAL FREEZE PREVIEW ONLY'
}
function CorrectPipeline {
    Write-Host 'UIA_NATIVE_PROTOCOL_FREEZE_OUTCOME_READ_CHARS=200'
    return 'LOCAL FREEZE PREVIEW ONLY'
}
$broken = BrokenPipeline
$correct = CorrectPipeline
if ($broken.GetType() -ne [object[]] -or
    -not [bool]($broken -notlike '*LOCAL FREEZE PREVIEW ONLY*')) {
    throw 'Negative control did not reproduce the PowerShell array false failure'
}
if ($correct.GetType() -ne [string] -or
    [bool]($correct -notlike '*LOCAL FREEZE PREVIEW ONLY*')) {
    throw 'Correct pipeline did not preserve the actual preview-only value'
}
Write-Output 'UIA_PROTOCOL_PREVIEW_PIPELINE_CONTRACT_OK'
