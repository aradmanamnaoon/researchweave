param([string]$Fixture, [string]$Screenshot)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
if (-not $Fixture) { throw 'Specify deterministic PDF fixture path' }
$exe = (Resolve-Path 'target/debug/researchweave-desktop.exe').Path
$process = Start-Process -FilePath $exe -PassThru
try {
    Start-Sleep -Seconds 2
    $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$process.Id)
    $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,$condition)
    if (!$window) { throw 'Desktop UIA window absent' }
    function FindNamed([string]$name,[System.Windows.Automation.ControlType]$type) {
        $all = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
        foreach($entry in $all) { if ($entry.Current.Name -eq $name -and $entry.Current.ControlType -eq $type) { return $entry } }
        throw "No UIA $type element named $name"
    }
    $sources = FindNamed 'Sources activity' ([System.Windows.Automation.ControlType]::Button)
    ([System.Windows.Automation.InvokePattern]$sources.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
    Start-Sleep -Milliseconds 150
    $nav = FindNamed 'PDF Reader workspace screen' ([System.Windows.Automation.ControlType]::Button)
    ([System.Windows.Automation.InvokePattern]$nav.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
    Start-Sleep -Milliseconds 250
    $path = FindNamed 'PDF file path' ([System.Windows.Automation.ControlType]::Edit)
    ([System.Windows.Automation.ValuePattern]$path.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue((Resolve-Path $Fixture).Path)
    $search = FindNamed 'PDF search query' ([System.Windows.Automation.ControlType]::Edit)
    ([System.Windows.Automation.ValuePattern]$search.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue('PDFium')
    $open = FindNamed 'Open PDF' ([System.Windows.Automation.ControlType]::Button)
    ([System.Windows.Automation.InvokePattern]$open.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
    Start-Sleep -Seconds 3
    $all = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
    $statuses = @($all | ForEach-Object { $_.Current.Name } | Where-Object { $_ -match 'matches: 1' })
    if (-not $statuses.Count) {
        $names = @($all | ForEach-Object { $_.Current.Name } | Where-Object { $_ -match 'PDF|matches|error|Rendered|Rendering' })
        throw ('PDF UI did not expose matching rendered status. UIA: ' + ($names -join ' | '))
    }
    if (-not (Get-Process -Id $process.Id).Responding) { throw 'PDF page renderer froze UI' }
    Write-Output 'PASS: PDF Reader navigated; actual path entered; PDFium search produced one match; UI responsive'
    if ($Screenshot) {
        $rect=$window.Current.BoundingRectangle
        $bitmap=New-Object System.Drawing.Bitmap([int]$rect.Width,[int]$rect.Height)
        $graphics=[System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen([int]$rect.Left,[int]$rect.Top,0,0,$bitmap.Size)
        $graphics.Dispose()
        $bitmap.Save([IO.Path]::GetFullPath($Screenshot),[System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
    }
} finally { if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force } }
