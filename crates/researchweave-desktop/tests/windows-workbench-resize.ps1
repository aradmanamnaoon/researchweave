param(
    [string]$Exe = "",
    [string]$Screenshot = ""
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ResearchWeaveWindow {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool MoveWindow(
        IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint
    );
}
'@

if (-not $Exe) {
    $Exe = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path 'target/debug/researchweave-desktop.exe'
}
if (-not (Test-Path -LiteralPath $Exe)) { throw "Build desktop executable first: $Exe" }

function Elements(
    [System.Windows.Automation.AutomationElement]$parent,
    [System.Windows.Automation.ControlType]$type
) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty, $type
    )
    return $parent.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Has-Named(
    [System.Windows.Automation.AutomationElement]$parent,
    [System.Windows.Automation.ControlType]$type,
    [string]$name
) {
    foreach ($item in (Elements $parent $type)) {
        if ($item.Current.Name -eq $name) { return $true }
    }
    return $false
}

$process = Start-Process -FilePath $Exe -PassThru
try {
    Start-Sleep -Seconds 2
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $process.Id
    )
    $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
        [System.Windows.Automation.TreeScope]::Children, $condition
    )
    if (-not $window) { throw 'Native window missing from UIA tree' }
    $handle = [IntPtr]$window.Current.NativeWindowHandle
    if ($handle -eq [IntPtr]::Zero) { throw 'Native window handle unavailable' }

    $sizes = @(
        @{ Name='medium'; Width=980; Height=680 },
        @{ Name='narrow'; Width=820; Height=640 },
        @{ Name='minimum'; Width=760; Height=560 }
    )
    foreach ($size in $sizes) {
        if (-not [ResearchWeaveWindow]::MoveWindow(
            $handle, 50, 50, $size.Width, $size.Height, $true
        )) {
            throw "MoveWindow failed at $($size.Name)"
        }
        Start-Sleep -Milliseconds 250
        $bounds = $window.Current.BoundingRectangle
        # Window chrome/DPI scaling can differ from the requested outer size.
        # What matters is that the window actually becomes smaller and the core
        # controls stay in the accessibility tree.
        if ($bounds.Width -gt 1100 -or $bounds.Height -gt 800) {
            throw "Window did not resize at $($size.Name): $([int]$bounds.Width)x$([int]$bounds.Height)"
        }
        foreach ($edit in @('Command palette','Project path','Project title','Research note')) {
            if (-not (Has-Named $window ([System.Windows.Automation.ControlType]::Edit) $edit)) {
                throw "$edit unreachable at $($size.Name) size"
            }
        }
        $activityElements = @()
        $activityButtons = Elements $window ([System.Windows.Automation.ControlType]::Button)
        foreach ($activity in @(
            'Home activity','Sources activity','Analyze activity',
            'Synthesize activity','Automate activity','Manage activity'
        )) {
            $element = $null
            foreach ($candidate in $activityButtons) {
                if ($candidate.Current.Name -eq $activity) { $element = $candidate; break }
            }
            if (-not $element) {
                throw "$activity unreachable at $($size.Name) size"
            }
            if ($element.Current.IsOffscreen) {
                throw "$activity is off-screen at $($size.Name) size"
            }
            $activityElements += $element
        }
        $orderedActivities = @($activityElements | Sort-Object { $_.Current.BoundingRectangle.Top })
        for ($index = 0; $index -lt ($orderedActivities.Count - 1); $index++) {
            $currentBounds = $orderedActivities[$index].Current.BoundingRectangle
            $nextBounds = $orderedActivities[$index + 1].Current.BoundingRectangle
            if ($currentBounds.Bottom -gt ($nextBounds.Top + 1)) {
                throw "Activity controls overlap at $($size.Name) size"
            }
        }
        Write-Output "PASS: $($size.Name) resize keeps core workbench controls reachable ($([int]$bounds.Width)x$([int]$bounds.Height))"
    }

    if ($Screenshot) {
        $bounds = $window.Current.BoundingRectangle
        $bitmap = New-Object System.Drawing.Bitmap([int]$bounds.Width, [int]$bounds.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen(
            [int]$bounds.Left, [int]$bounds.Top, 0, 0, $bitmap.Size
        )
        $graphics.Dispose()
        $bitmap.Save($Screenshot, [System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
        Write-Output "Screenshot: $Screenshot"
    }
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
}
