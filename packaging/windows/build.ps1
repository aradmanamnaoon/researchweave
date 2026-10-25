$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Repo

uv sync --locked --extra dev --extra formats --extra release
$VersionMatch = Select-String -Path "pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) { throw "Could not determine ResearchWeave version" }
$Version = $VersionMatch.Matches[0].Groups[1].Value
$env:RESEARCHWEAVE_VERSION = $Version

uv run pyinstaller --noconfirm --clean packaging/researchweave.spec
if (-not (Test-Path -LiteralPath "dist\ResearchWeave\ResearchWeave.exe")) {
    throw "Expected Windows executable was not produced"
}

$Zip = "dist\ResearchWeave-v$Version-windows-x64-portable.zip"
if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip }
Compress-Archive -Path "dist\ResearchWeave\*" -DestinationPath $Zip -CompressionLevel Optimal

$Iscc = $null
$Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($Command) {
    $Iscc = $Command.Source
}
if (-not $Iscc) {
    $Candidates = @(
        (Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate)) {
            $Iscc = $Candidate
            break
        }
    }
}
if (-not $Iscc) {
    throw "Inno Setup 6 (ISCC.exe) is required to build the Windows installer"
}

$SourceDir = (Resolve-Path "dist\ResearchWeave").Path
$OutputDir = (Resolve-Path "dist").Path
& $Iscc "/DAppVersion=$Version" "/DSourceDir=$SourceDir" "/DOutputDir=$OutputDir" "packaging\windows\ResearchWeave.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }

$Installer = "dist\ResearchWeave-v$Version-windows-x64-setup.exe"
if (-not (Test-Path -LiteralPath $Installer)) {
    throw "Expected Windows installer was not produced"
}

$ChecksumFile = "dist\SHA256SUMS-windows.txt"
$Artifacts = @($Installer, $Zip)
$Lines = foreach ($Artifact in $Artifacts) {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Artifact).Hash.ToLowerInvariant()
    "$Hash *$(Split-Path -Leaf $Artifact)"
}
$Lines | Set-Content -LiteralPath $ChecksumFile -Encoding ascii
$Lines
