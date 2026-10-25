$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VersionMatch = Select-String -Path (Join-Path $Repo "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) { throw "Could not determine ResearchWeave version" }
$Version = $VersionMatch.Matches[0].Groups[1].Value
$Zip = Join-Path $Repo "dist\ResearchWeave-v$Version-windows-x64-portable.zip"
if (-not (Test-Path -LiteralPath $Zip)) { throw "Build the Windows package first" }

$Scratch = Join-Path ([System.IO.Path]::GetTempPath()) ("researchweave-portable-" + [guid]::NewGuid())
$Package = Join-Path $Scratch "package"
$Profile = Join-Path $Scratch "profile"
$LocalAppData = Join-Path $Profile "LocalAppData"
New-Item -ItemType Directory -Path $Package,$LocalAppData -Force | Out-Null
$Sentinel = Join-Path $LocalAppData "researchweave-retention-sentinel.txt"
Set-Content -LiteralPath $Sentinel -Value "retain user data" -Encoding UTF8

try {
    Expand-Archive -LiteralPath $Zip -DestinationPath $Package
    $Exe = Join-Path $Package "ResearchWeave.exe"
    if (-not (Test-Path -LiteralPath $Exe)) { throw "Portable executable missing after extraction" }
    $previousLocalAppData = $env:LOCALAPPDATA
    $previousQt = $env:QT_QPA_PLATFORM
    try {
        $env:LOCALAPPDATA = $LocalAppData
        $env:QT_QPA_PLATFORM = "offscreen"
        $process = Start-Process -FilePath $Exe -PassThru
        Start-Sleep -Seconds 4
        if ($process.HasExited) { throw "Packaged app exited during startup smoke test" }
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
    finally {
        $env:LOCALAPPDATA = $previousLocalAppData
        $env:QT_QPA_PLATFORM = $previousQt
    }
    Remove-Item -LiteralPath $Package -Recurse -Force
    if (-not (Test-Path -LiteralPath $Sentinel)) {
        throw "Removing the portable package unexpectedly removed user-profile data"
    }
    Write-Output "portable_startup=pass"
    Write-Output "user_data_retention=pass"
    Write-Output "sentinel=$Sentinel"
}
finally {
    if (Test-Path -LiteralPath $Scratch) { Remove-Item -LiteralPath $Scratch -Recurse -Force }
}
