$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Repo
uv sync --locked --extra dev --extra formats --extra release
uv run pyinstaller --noconfirm --clean packaging/researchweave.spec
if (-not (Test-Path -LiteralPath "dist\ResearchWeave\ResearchWeave.exe")) {
    throw "Expected Windows executable was not produced"
}
$Zip = "dist\ResearchWeave-windows-x86_64.zip"
if (Test-Path -LiteralPath $Zip) { Remove-Item -LiteralPath $Zip }
Compress-Archive -Path "dist\ResearchWeave\*" -DestinationPath $Zip -CompressionLevel Optimal
Get-FileHash -Algorithm SHA256 -LiteralPath $Zip
