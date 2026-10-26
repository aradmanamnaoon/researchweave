param([string]$Destination = "")
$ErrorActionPreference = 'Stop'
$url = 'https://github.com/firecrawl/pdfium-rs/releases/download/native-v7988/firecrawl-pdfium-win-x64.tgz'
$expected = '6f398552d8021a89078f64466557251a204999177287b876be49877eb8750d50'
if (-not $Destination) { $Destination = Join-Path $PSScriptRoot '../../target/pdfium/win-x64' }
$Destination = [IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force $Destination | Out-Null
$archive = Join-Path $Destination 'pdfium-win-x64.tgz'
Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actual -ne $expected) { Remove-Item -LiteralPath $archive -Force; throw "PDFium SHA256 mismatch: $actual" }
tar -xzf $archive -C $Destination
if (-not (Test-Path (Join-Path $Destination 'bin/pdfium.dll'))) {
    if (-not (Test-Path (Join-Path $Destination 'lib/pdfium.dll'))) { throw 'PDFium shared library missing from verified archive' }
}
Write-Output "PDFium native-v7988 win-x64 verified at $Destination"
