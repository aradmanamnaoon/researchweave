param(
    [Parameter(Mandatory = $true)]
    [string]$Setup,
    [Parameter(Mandatory = $true)]
    [string]$Fixture,
    [string]$Query = "ResearchWeave",
    [switch]$RunUIA,
    [string]$Screenshot = ""
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$targetRoot = Join-Path $repo "target"
$installRoot = Join-Path $targetRoot "installed-smoke\ResearchWeave"
$setupPath = (Resolve-Path $Setup).Path
$fixturePath = (Resolve-Path $Fixture).Path
$stagedPdfium = Join-Path $targetRoot "native-package\windows-x64\pdfium.dll"
$stagedExe = Join-Path $targetRoot "native-package\windows-x64\researchweave-desktop.exe"
$releaseExe = Join-Path $targetRoot "release\researchweave-desktop.exe"

function Assert-InTarget([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($targetRoot).TrimEnd('\') + '\'
    if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to mutate path outside target: $full"
    }
}

function Remove-PriorInstall {
    if (-not (Test-Path -LiteralPath $installRoot)) { return }
    Assert-InTarget $installRoot
    $uninstaller = Join-Path $installRoot "unins000.exe"
    if (Test-Path -LiteralPath $uninstaller) {
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
            '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
        ) -Wait -PassThru -WindowStyle Hidden
        if ($uninstall.ExitCode -ne 0) {
            throw "Previous test uninstall failed with exit code $($uninstall.ExitCode)"
        }
    }
    if (Test-Path -LiteralPath $installRoot) {
        Remove-Item -LiteralPath $installRoot -Recurse -Force
    }
}

Assert-InTarget $installRoot
Remove-PriorInstall
try {
    $install = Start-Process -FilePath $setupPath -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=$installRoot"
    ) -Wait -PassThru -WindowStyle Hidden
    if ($install.ExitCode -ne 0) {
        throw "Installer failed with exit code $($install.ExitCode)"
    }

    $exe = Join-Path $installRoot "researchweave-desktop.exe"
    $pdfium = Join-Path $installRoot "pdfium.dll"
    $notice = Join-Path $installRoot "PDFIUM_RUNTIME_NOTICES.md"
    foreach ($file in @($exe, $pdfium, $notice, $stagedPdfium, $stagedExe, $releaseExe)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item -LiteralPath $file).Length -eq 0) {
            throw "Installed-candidate file missing: $file"
        }
    }

    $stagedExeHash = (Get-FileHash -LiteralPath $stagedExe -Algorithm SHA256).Hash
    $releaseExeHash = (Get-FileHash -LiteralPath $releaseExe -Algorithm SHA256).Hash
    if ($stagedExeHash -ne $releaseExeHash) {
        throw "Staged executable differs from current target/release Rust binary"
    }
    $installedExeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    if ($stagedExeHash -ne $installedExeHash) {
        throw "Installed executable differs from the staged Rust release binary"
    }

    & $exe '--smoke-project'
    if ($LASTEXITCODE -ne 0) { throw "Installed project smoke failed: $LASTEXITCODE" }
    & $exe '--smoke-pdf' $fixturePath $Query
    if ($LASTEXITCODE -ne 0) { throw "Installed PDF smoke failed: $LASTEXITCODE" }

    $stagedHash = (Get-FileHash -LiteralPath $stagedPdfium -Algorithm SHA256).Hash
    $installedHash = (Get-FileHash -LiteralPath $pdfium -Algorithm SHA256).Hash
    if ($stagedHash -ne $installedHash) {
        throw "Installed PDFium runtime differs from verified staged runtime"
    }

    if ($RunUIA) {
        $uia = Join-Path $repo "crates\researchweave-desktop\tests\windows-uia-smoke.ps1"
        $uiaArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $uia, '-Exe', $exe)
        if ($Screenshot) { $uiaArgs += @('-Screenshot', $Screenshot) }
        & powershell.exe @uiaArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Installed UIA smoke failed: $LASTEXITCODE"
        }
    }
}
finally {
    if (Test-Path -LiteralPath $installRoot) {
        $uninstaller = Join-Path $installRoot "unins000.exe"
        if (Test-Path -LiteralPath $uninstaller) {
            $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @(
                '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
            ) -Wait -PassThru -WindowStyle Hidden
            if ($uninstall.ExitCode -ne 0) {
                throw "Test uninstall failed with exit code $($uninstall.ExitCode)"
            }
        }
        if (Test-Path -LiteralPath $installRoot) {
            Assert-InTarget $installRoot
            Remove-Item -LiteralPath $installRoot -Recurse -Force
        }
    }
}
if (Test-Path -LiteralPath $installRoot) {
    throw "Installed-candidate cleanup incomplete: $installRoot"
}
Write-Output "PACKAGED_QA_OK pdfium_sha256=$installedHash exe_sha256=$installedExeHash"
