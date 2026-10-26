param([string]$Exe = "", [string]$Screenshot = "")
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class DisplayFocus { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd); [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags); }'
if (-not $Exe) { $Exe = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path 'target/debug/researchweave-desktop.exe' }
if (-not (Test-Path $Exe)) { throw "Desktop executable missing: $Exe" }
$hostData = Join-Path $env:TEMP ('rw-display-' + [guid]::NewGuid().ToString('N'))
$original = $env:RESEARCHWEAVE_HOST_DATA_DIR
$env:RESEARCHWEAVE_HOST_DATA_DIR = $hostData
New-Item -ItemType Directory -Path $hostData -Force | Out-Null
$p = $null
function Named($window, $type, [string]$name) {
    $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $type)
    for ($i=0; $i -lt 30; $i++) {
        $items = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
        foreach ($item in $items) { if ($item.Current.Name -eq $name) { return $item } }
        Start-Sleep -Milliseconds 100
    }
    $all = @($window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name })
    throw "Missing accessible $name. Available: $($all -join ', ')"
}
function WindowFor($process) {
    $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $process.Id)
    for ($i=0; $i -lt 30; $i++) {
        $found = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
        if ($found) { return $found }
        Start-Sleep -Milliseconds 100
    }
    throw 'Desktop window missing'
}
function OpenPreferences($window) {
    $command = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Command palette'
    ([System.Windows.Automation.ValuePattern]$command.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue('Preferences')
    $command.SetFocus()
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    $null = Named $window ([System.Windows.Automation.ControlType]::Button) 'Toggle dark theme'
}
function AssertState($window, [string]$file) {
    if (-not (Test-Path $file)) { throw 'Preferences JSON missing' }
    $value = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
    if (-not $value.dark_mode -or -not $value.high_contrast -or -not $value.compact_density -or $value.ui_scale -ne 200) { throw "Incorrect persisted preferences: $(Get-Content -LiteralPath $file -Raw)" }
    foreach ($name in @('Dark theme: on','High contrast: on')) {
        $null = Named $window ([System.Windows.Automation.ControlType]::Text) $name
    }
    # At 200%, preferences intentionally scroll vertically. Offscreen labels
    # are not guaranteed to exist in Slint's current UIA tree until revealed.
    $foundScale = $false
    $foundDensity = $false
    for ($step=0; $step -lt 12; $step++) {
        $labels = @($window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name })
        if ($labels -contains 'Interface text scale: 200%') { $foundScale = $true; break }
        if ($labels -contains 'Compact density: on') { $foundDensity = $true }
        (Named $window ([System.Windows.Automation.ControlType]::Button) 'Compact density: on').SetFocus()
        [System.Windows.Forms.SendKeys]::SendWait('{PGDN}')
        Start-Sleep -Milliseconds 100
    }
    if (-not $foundDensity) {
        $labels = @($window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name })
        if ($labels -contains 'Compact density: on') { $foundDensity = $true }
    }
    if (-not $foundDensity) { throw 'Compact-density state is not exposed through UIA after scrolling the preferences viewport' }
    if (-not $foundScale) { throw '200% scale label is not accessible after scrolling the preferences viewport' }
}
try {
    $file = Join-Path $hostData 'display-preferences.json'
    $p = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 2
    $window = WindowFor $p
    OpenPreferences $window
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Toggle dark theme').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Toggle high contrast').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Compact density: off').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $null = Named $window ([System.Windows.Automation.ControlType]::Button) 'Compact density: on'
    for ($attempt=0; $attempt -lt 24; $attempt++) {
        $current = 100
        if (Test-Path $file) {
            try { $current = (Get-Content -LiteralPath $file -Raw | ConvertFrom-Json).ui_scale }
            catch { Start-Sleep -Milliseconds 90; continue }
        }
        if ($current -eq 200) { break }
        if ($current -gt 200) { throw "Scale overshot 200%: $current" }
        (Named $window ([System.Windows.Automation.ControlType]::Button) 'Increase interface scale').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        Start-Sleep -Milliseconds 75
    }
    AssertState $window $file
    Write-Output 'PASS: accessible controls set dark/high-contrast/compact-density/200% and persist JSON'
    if ($Screenshot) {
        # UIA targets the isolated PID, not a potentially overlapping broad-harness window.
        (Named $window ([System.Windows.Automation.ControlType]::Button) 'Toggle dark theme').SetFocus()
        $nativeWindow = [IntPtr]$p.MainWindowHandle
        $null = [DisplayFocus]::SetWindowPos($nativeWindow,[IntPtr](-1),0,0,0,0,0x43)
        $null = [DisplayFocus]::SetForegroundWindow($nativeWindow)
        $null = Named $window ([System.Windows.Automation.ControlType]::Text) 'Display preferences'
        $captured = $false
        for ($frame=0; $frame -lt 10; $frame++) {
            Start-Sleep -Milliseconds 300
            $rect = $window.Current.BoundingRectangle
            if ($rect.Width -lt 500 -or $rect.Height -lt 350) { continue }
            $bmp = New-Object System.Drawing.Bitmap([int]$rect.Width,[int]$rect.Height)
            $graphics = [System.Drawing.Graphics]::FromImage($bmp)
            $graphics.CopyFromScreen([int]$rect.Left,[int]$rect.Top,0,0,$bmp.Size)
            $graphics.Dispose()
            $differentPixels = 0
            foreach ($y in @(40,100,200,350,500)) {
                foreach ($x in @(20,100,250,500,800)) {
                    if ($x -lt $bmp.Width -and $y -lt $bmp.Height) {
                        $pixel = $bmp.GetPixel($x,$y)
                        if ($pixel.R -gt 30 -or $pixel.G -gt 30 -or $pixel.B -gt 30) { $differentPixels++ }
                    }
                }
            }
            if ($differentPixels -ge 4) {
                $bmp.Save($Screenshot,[System.Drawing.Imaging.ImageFormat]::Png)
                $captured = $true
                $bmp.Dispose()
                break
            }
            $bmp.Dispose()
        }
        $null = [DisplayFocus]::SetWindowPos($nativeWindow,[IntPtr](-2),0,0,0,0,0x43)
        if (-not $captured) { Write-Output 'LIMIT: focused Preferences screenshot was not reliably rendered; no black-frame evidence saved' }
        else { Write-Output "Screenshot: $Screenshot" }
    }
    Stop-Process -Id $p.Id -Force
    $p.WaitForExit()
    $p = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 2
    $window = WindowFor $p
    OpenPreferences $window
    AssertState $window $file
    Write-Output 'PASS: fresh process restored dark/high-contrast/compact-density/200% accessible state and JSON'
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Toggle dark theme').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Milliseconds 120
    $contrastOnly = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
    if ($contrastOnly.dark_mode -or -not $contrastOnly.high_contrast -or -not $contrastOnly.compact_density -or $contrastOnly.ui_scale -ne 200) {
        throw 'High contrast was not preserved when dark theme was turned off'
    }
    $null = Named $window ([System.Windows.Automation.ControlType]::Text) 'Dark theme: off'
    $null = Named $window ([System.Windows.Automation.ControlType]::Text) 'High contrast: on'
    $null = Named $window ([System.Windows.Automation.ControlType]::Button) 'Compact density: on'
    Write-Output 'PASS: high contrast and compact density remain enabled independently of dark theme'
} finally {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    if (Test-Path $hostData) { Remove-Item -LiteralPath $hostData -Recurse -Force }
    $env:RESEARCHWEAVE_HOST_DATA_DIR = $original
}
