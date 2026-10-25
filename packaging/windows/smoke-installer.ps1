$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VersionMatch = Select-String -Path (Join-Path $Repo "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) { throw "Could not determine ResearchWeave version" }
$Version = $VersionMatch.Matches[0].Groups[1].Value
$Installer = Join-Path $Repo "dist\ResearchWeave-v$Version-windows-x64-setup.exe"
if (-not (Test-Path -LiteralPath $Installer)) { throw "Build the Windows installer first" }

$VersionInfo = (Get-Item -LiteralPath $Installer).VersionInfo
if ($VersionInfo.ProductVersion -and -not $VersionInfo.ProductVersion.StartsWith($Version)) {
    throw "Installer metadata version '$($VersionInfo.ProductVersion)' does not match '$Version'"
}

$Scratch = Join-Path ([System.IO.Path]::GetTempPath()) ("researchweave-installer-" + [guid]::NewGuid())
$InstallDir = Join-Path $Scratch "install"
$Profile = Join-Path $Scratch "profile"
$LocalAppData = Join-Path $Profile "LocalAppData"
New-Item -ItemType Directory -Path $InstallDir,$LocalAppData -Force | Out-Null
$Sentinel = Join-Path $LocalAppData "researchweave-retention-sentinel.txt"
Set-Content -LiteralPath $Sentinel -Value "retain user data" -Encoding UTF8

try {
    $Install = Start-Process -FilePath $Installer -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/DIR=$InstallDir"
    ) -Wait -PassThru
    if ($Install.ExitCode -ne 0) { throw "Installer exited with code $($Install.ExitCode)" }

    $Exe = Join-Path $InstallDir "ResearchWeave.exe"
    if (-not (Test-Path -LiteralPath $Exe)) { throw "Installed ResearchWeave.exe is missing" }
    $Uninstaller = Join-Path $InstallDir "unins000.exe"
    if (-not (Test-Path -LiteralPath $Uninstaller)) { throw "Uninstaller was not created" }

    $previousLocalAppData = $env:LOCALAPPDATA
    $previousQt = $env:QT_QPA_PLATFORM
    try {
        $env:LOCALAPPDATA = $LocalAppData
        $env:QT_QPA_PLATFORM = "offscreen"
        $process = Start-Process -FilePath $Exe -PassThru
        Start-Sleep -Seconds 4
        if ($process.HasExited) { throw "Installed app exited during startup smoke test" }
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit()
    }
    finally {
        $env:LOCALAPPDATA = $previousLocalAppData
        $env:QT_QPA_PLATFORM = $previousQt
    }

    $Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    ) -Wait -PassThru
    if ($Uninstall.ExitCode -ne 0) { throw "Uninstaller exited with code $($Uninstall.ExitCode)" }
    if (Test-Path -LiteralPath $Exe) { throw "Application executable remains after uninstall" }
    if (-not (Test-Path -LiteralPath $Sentinel)) {
        throw "Uninstall unexpectedly removed user-profile data"
    }

    Write-Output "installer_install=pass"
    Write-Output "installer_startup=pass"
    Write-Output "installer_uninstall=pass"
    Write-Output "user_data_retention=pass"
}
finally {
    if (Test-Path -LiteralPath $Scratch) { Remove-Item -LiteralPath $Scratch -Recurse -Force }
}
