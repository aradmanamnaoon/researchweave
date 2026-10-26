param(
    [string]$Exe = "",
    [string]$Screenshot = "",
    [switch]$VisualOnly
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ResearchWeaveCapture {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
}
'@

if (-not $Exe) {
    $Exe = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path 'target/debug/researchweave-desktop.exe'
}
if (-not (Test-Path $Exe)) {
    throw "Build desktop executable first: $Exe"
}

function Children(
    [System.Windows.Automation.AutomationElement]$Parent,
    [System.Windows.Automation.ControlType]$Type
) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        $Type
    )
    return $Parent.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Named(
    [System.Windows.Automation.AutomationElement]$Parent,
    [System.Windows.Automation.ControlType]$Type,
    [string]$Name
) {
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        foreach ($item in (Children $Parent $Type)) {
            if ($item.Current.Name -eq $Name) {
                return $item
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "UIA element missing: $Type '$Name'"
}

function WindowForProcess([System.Diagnostics.Process]$Process) {
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
            $Process.Id
        )
        $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
            [System.Windows.Automation.TreeScope]::Children,
            $condition
        )
        if ($window) {
            return $window
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'Native window missing from UIA tree'
}

function Navigate(
    [System.Windows.Automation.AutomationElement]$Window,
    [string]$Page
) {
    $command = Named $Window ([System.Windows.Automation.ControlType]::Edit) 'Command palette'
    ([System.Windows.Automation.ValuePattern]$command.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).SetValue($Page)
    $command.SetFocus()
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Milliseconds 150
}

function WaitForNameLike(
    [System.Windows.Automation.AutomationElement]$Window,
    [string]$Pattern,
    [int]$TimeoutMilliseconds = 3000
) {
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    do {
        $names = @($Window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        ) | ForEach-Object { $_.Current.Name })
        if ($names | Where-Object { $_ -like $Pattern }) {
            return
        }
        Start-Sleep -Milliseconds 50
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "UIA result missing: $Pattern"
}

function FocusAndReplace(
    [System.Windows.Automation.AutomationElement]$Element,
    [string]$AccessibleName,
    [string]$Value
) {
    $Element.SetFocus()
    $focused = $null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 25
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($focused -and $focused.Current.Name -eq $AccessibleName) {
            break
        }
    }
    if (-not $focused -or $focused.Current.Name -ne $AccessibleName) {
        throw "$AccessibleName did not receive focus before edit"
    }
    [System.Windows.Forms.SendKeys]::SendWait('^a')
    [System.Windows.Forms.SendKeys]::SendWait($Value)
}

function WaitForDirtyDraft(
    [string]$HostData,
    [ValidateSet('manuscript', 'notebook')]
    [string]$Surface,
    [string]$Expected
) {
    $draftRoot = Join-Path $HostData 'writing-drafts'
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if (Test-Path $draftRoot) {
            foreach ($file in @(Get-ChildItem $draftRoot -Filter '*.json' -File)) {
                $draft = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
                if (
                    ($Surface -eq 'manuscript' -and $draft.manuscript_dirty -and $draft.body -eq $Expected) -or
                    ($Surface -eq 'notebook' -and $draft.notebook_dirty -and $draft.notebook -eq $Expected)
                ) {
                    return $draft
                }
            }
        }
        Start-Sleep -Milliseconds 25
    }
    throw "$Surface edit was not durably journaled before the 800 ms autosave"
}

function OpenProject(
    [System.Windows.Automation.AutomationElement]$Window,
    [string]$ProjectPath
) {
    $path = Named $Window ([System.Windows.Automation.ControlType]::Edit) 'Project path'
    ([System.Windows.Automation.ValuePattern]$path.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).SetValue($ProjectPath)
    (Named $Window ([System.Windows.Automation.ControlType]::Button) 'Open project').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    Start-Sleep -Milliseconds 300
}

$projectPath = Join-Path $env:TEMP ('rw-writing-uia-' + [guid]::NewGuid().ToString('N'))
$hostData = Join-Path $env:TEMP ('rw-writing-uia-host-' + [guid]::NewGuid().ToString('N'))
$previousHostData = $env:RESEARCHWEAVE_HOST_DATA_DIR
$env:RESEARCHWEAVE_HOST_DATA_DIR = $hostData
New-Item -ItemType Directory -Path $hostData -Force | Out-Null
$process = $null

try {
    $process = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 2
    $window = WindowForProcess $process

    $path = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Project path'
    $title = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Project title'
    ([System.Windows.Automation.ValuePattern]$path.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).SetValue($projectPath)
    ([System.Windows.Automation.ValuePattern]$title.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).SetValue('Writing recovery UIA')
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Create project').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    Start-Sleep -Milliseconds 500
    if (-not (Test-Path (Join-Path $projectPath 'data/project.sqlite'))) {
        throw 'Project creation did not persist the SQLite project'
    }

    Navigate $window 'Manuscript'
    foreach ($pair in @(
        @('Manuscript ID', 'uia-writing'),
        @('Manuscript section', 'Results'),
        @('Manuscript citations', ''),
        @('Manuscript section body', 'Initial persisted manuscript body.')
    )) {
        $edit = Named $window ([System.Windows.Automation.ControlType]::Edit) $pair[0]
        ([System.Windows.Automation.ValuePattern]$edit.GetCurrentPattern(
            [System.Windows.Automation.ValuePattern]::Pattern
        )).SetValue($pair[1])
    }
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Preview manuscript section').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window '*Manuscript section preview ready*'
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Record previewed manuscript section').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window '*Previewed evidence operation recorded and audited*'
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Inspect manuscript').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window '*Initial persisted manuscript body.*'
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Export manuscript DOCX').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window '*application/vnd.openxmlformats-officedocument.wordprocessingml.document*'
    Write-Output 'PASS: manuscript preview -> approved save -> inspect -> DOCX export'

    if ($Screenshot) {
        $bounds = $window.Current.BoundingRectangle
        $bitmap = New-Object System.Drawing.Bitmap([int]$bounds.Width, [int]$bounds.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $hdc = $graphics.GetHdc()
        $captured = [ResearchWeaveCapture]::PrintWindow(
            [IntPtr]$window.Current.NativeWindowHandle,
            $hdc,
            2
        )
        $graphics.ReleaseHdc($hdc)
        $graphics.Dispose()
        if (-not $captured) {
            $bitmap.Dispose()
            throw 'PrintWindow failed for manuscript screenshot'
        }
        $bitmap.Save($Screenshot, [System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
        Write-Output "Screenshot: $Screenshot"
    }
    if ($VisualOnly) {
        return
    }

    $debounced = 'Debounced manuscript autosave'
    $manuscriptBody = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Manuscript section body'
    ([System.Windows.Automation.ValuePattern]$manuscriptBody.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).SetValue($debounced)
    WaitForNameLike $window '*Manuscript autosaved to project revisions*' 3000
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Inspect manuscript').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window "*$debounced*"
    Write-Output 'PASS: manuscript edit debounces into persisted project revision'

    $recoveredManuscript = 'Abrupt manuscript recovery'
    $manuscriptBody = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Manuscript section body'
    FocusAndReplace $manuscriptBody 'Manuscript section body' $recoveredManuscript
    WaitForDirtyDraft $hostData 'manuscript' $recoveredManuscript | Out-Null
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()

    $process = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 2
    $window = WindowForProcess $process
    OpenProject $window $projectPath
    Navigate $window 'Manuscript'
    $restoredManuscript = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Manuscript section body'
    $restoredManuscriptValue = ([System.Windows.Automation.ValuePattern]$restoredManuscript.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).Current.Value
    if ($restoredManuscriptValue -ne $recoveredManuscript) {
        throw 'Abrupt-exit manuscript draft was not restored into the fresh process'
    }
    WaitForNameLike $window '*Recovered manuscript autosaved to project revisions*' 3000
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Inspect manuscript').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window "*$recoveredManuscript*"
    Write-Output 'PASS: abrupt manuscript exit restores and retries without a new edit'

    Navigate $window 'Notebook'
    $recoveredNotebook = 'Abrupt notebook recovery'
    $notebookBody = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Project notebook text'
    FocusAndReplace $notebookBody 'Project notebook text' $recoveredNotebook
    WaitForDirtyDraft $hostData 'notebook' $recoveredNotebook | Out-Null
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()

    $process = Start-Process -FilePath $Exe -PassThru
    Start-Sleep -Seconds 2
    $window = WindowForProcess $process
    OpenProject $window $projectPath
    Navigate $window 'Notebook'
    $restoredNotebook = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Project notebook text'
    $restoredNotebookValue = ([System.Windows.Automation.ValuePattern]$restoredNotebook.GetCurrentPattern(
        [System.Windows.Automation.ValuePattern]::Pattern
    )).Current.Value
    if ($restoredNotebookValue -ne $recoveredNotebook) {
        throw 'Abrupt-exit notebook draft was not restored into the fresh process'
    }
    WaitForNameLike $window '*Recovered notebook autosaved to project revisions*' 3000
    (Named $window ([System.Windows.Automation.ControlType]::Button) 'Export notebook Markdown').GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    ).Invoke()
    WaitForNameLike $window "*$recoveredNotebook*"
    Write-Output 'PASS: abrupt notebook exit restores and retries without a new edit'

    $draftRoot = Join-Path $hostData 'writing-drafts'
    $finalDraft = @(Get-ChildItem $draftRoot -Filter '*.json' -File | ForEach-Object {
        Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
    } | Where-Object {
        $_.body -eq $recoveredManuscript -and $_.notebook -eq $recoveredNotebook
    } | Select-Object -First 1)
    if (-not $finalDraft -or $finalDraft.manuscript_dirty -or $finalDraft.notebook_dirty) {
        throw 'Recovered writing journal did not clear dirty flags after revision persistence'
    }
    Write-Output 'PASS: recovered writing journal is clean after both durable retries'
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    if (Test-Path $projectPath) {
        Remove-Item -LiteralPath $projectPath -Recurse -Force
    }
    if (Test-Path $hostData) {
        Remove-Item -LiteralPath $hostData -Recurse -Force
    }
    $env:RESEARCHWEAVE_HOST_DATA_DIR = $previousHostData
}
