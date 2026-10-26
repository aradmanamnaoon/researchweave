param([string]$Cargo = "cargo")
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
Push-Location $repo
try {
    # Use cmd's stream merge to prevent native stderr diagnostic lines from
    # becoming PowerShell terminating errors. This check should be run after
    # Slint source changes (incremental no-op builds have limited coverage).
    $output = & cmd.exe /d /c "$Cargo build -p researchweave-desktop --locked 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "Desktop build failed: $($output -join [Environment]::NewLine)" }
    if (($output -join [Environment]::NewLine) -match "(?i)binding loop|layoutinfo-h.+loop") {
        throw "Slint responsive binding-loop warning: $($output -join [Environment]::NewLine)"
    }
    Write-Output "PASS: desktop build output has no Slint binding-loop warnings"
} finally {
    Pop-Location
}
