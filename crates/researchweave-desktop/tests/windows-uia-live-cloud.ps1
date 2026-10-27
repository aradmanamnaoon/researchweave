param(
    [Parameter(Mandatory = $true)] [string]$Exe,
    [Parameter(Mandatory = $true)] [string]$ProfileId,
    [Parameter(Mandatory = $true)] [string]$Endpoint,
    [Parameter(Mandatory = $true)] [string]$Bucket,
    [Parameter(Mandatory = $true)] [string]$RunToken,
    [string]$Screenshot = ""
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Named([System.Windows.Automation.AutomationElement]$Parent, [System.Windows.Automation.ControlType]$Type, [string]$Name) {
    $condition = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $Type)),
        (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Name))
    )
    $element = $Parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    if (-not $element) { throw "Missing UI element: $Name" }
    return $element
}

function WindowFor([System.Diagnostics.Process]$Process, [string]$Failure) {
    for ($attempt = 0; $attempt -lt 160; $attempt++) {
        $Process.Refresh()
        if ($Process.HasExited) { throw 'Application exited before UIA was ready' }
        if ($Process.MainWindowHandle -ne 0) {
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
            if ($window) { return $window }
        }
        Start-Sleep -Milliseconds 100
    }
    throw $Failure
}

function Set-Value([System.Windows.Automation.AutomationElement]$Window, [string]$Name, [string]$Value) {
    $element = Named $Window ([System.Windows.Automation.ControlType]::Edit) $Name
    ([System.Windows.Automation.ValuePattern]$element.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue($Value)
}

function Invoke-Button([System.Windows.Automation.AutomationElement]$Window, [string]$Name) {
    $button = Named $Window ([System.Windows.Automation.ControlType]::Button) $Name
    ([System.Windows.Automation.InvokePattern]$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
}
function Focus-CloudControl(
    [System.Windows.Automation.AutomationElement]$Window,
    [System.Windows.Automation.ControlType]$Type,
    [string]$Name,
    [ValidateSet('Forward', 'Backward')] [string]$Direction = 'Forward',
    [int]$MaxTabs = 35
) {
    # Only the visible part of Slint's Cloud Sync ScrollView is exposed through
    # UIA. Tab moves and scrolls the actual focus; resolve a fresh node each time.
    $key = if ($Direction -eq 'Backward') { '+{TAB}' } else { '{TAB}' }
    for ($attempt = 0; $attempt -le $MaxTabs; $attempt++) {
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($focused) {
            try {
                if ($focused.Current.ProcessId -ne $Window.Current.ProcessId) {
                    throw 'Cloud Sync keyboard focus left the ResearchWeave window'
                }
                if ($focused.Current.ControlType -eq $Type -and
                    $focused.Current.Name -eq $Name) {
                    return $focused
                }
            } catch [System.Windows.Automation.ElementNotAvailableException] {
                # UI nodes can be rebuilt when a control enters the viewport.
            }
        }
        if ($attempt -eq $MaxTabs) { break }
        [System.Windows.Forms.SendKeys]::SendWait($key)
        Start-Sleep -Milliseconds 100
    }
    throw "Cloud Sync control did not receive keyboard focus: $Name ($Direction)"
}
function Set-CloudValue(
    [System.Windows.Automation.AutomationElement]$Window,
    [string]$Name,
    [string]$Value,
    [string]$Direction = 'Forward'
) {
    $edit = Focus-CloudControl $Window ([System.Windows.Automation.ControlType]::Edit) $Name $Direction
    ([System.Windows.Automation.ValuePattern]$edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue($Value)
}
function Invoke-CloudButton(
    [System.Windows.Automation.AutomationElement]$Window,
    [string]$Name,
    [string]$Direction = 'Forward'
) {
    $button = Focus-CloudControl $Window ([System.Windows.Automation.ControlType]::Button) $Name $Direction
    ([System.Windows.Automation.InvokePattern]$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
}

function Wait-ForNameLike([System.Windows.Automation.AutomationElement]$Window, [string]$Pattern, [int]$TimeoutMs = 30000) {
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    do {
        $names = @($Window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        ) | ForEach-Object { $_.Current.Name })
        $match = $names | Where-Object { $_ -like $Pattern } | Select-Object -First 1
        if ($match) { return $match }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for accessible text like: $Pattern"
}

function Read-JsonRetry([string]$Path, [int]$Attempts = 160) {
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        if (Test-Path -LiteralPath $Path) {
            try { return (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json) }
            catch { }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Timed out waiting for valid JSON: $Path"
}

function Capture-WindowScreenshot([System.Windows.Automation.AutomationElement]$Window, [string]$Path) {
    if (-not $Path) { return }
    $rect = $Window.Current.BoundingRectangle
    if ($rect.Width -le 0 -or $rect.Height -le 0) { throw 'Cannot capture zero-size live-cloud window' }
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $bmp = New-Object System.Drawing.Bitmap([int]$rect.Width, [int]$rect.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $graphics.CopyFromScreen([int]$rect.Left, [int]$rect.Top, 0, 0, $bmp.Size)
        $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bmp.Dispose()
    }
}

if ($RunToken -notmatch '^[A-Za-z0-9._-]{1,96}$') { throw 'Run token is invalid' }
if ($ProfileId -notmatch '^[A-Za-z0-9._-]{1,96}$') { throw 'Profile ID is invalid' }
$endpointUri = [Uri]$Endpoint
if ($endpointUri.Scheme -ne 'https' -or -not $endpointUri.Host.EndsWith('.liara.site', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Live GUI endpoint must be an HTTPS Liara hostname'
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$exePath = (Resolve-Path $Exe).Path
$hostData = Join-Path $repo "target/live-s3/gui-host-$RunToken"
$restorePath = Join-Path $repo "target/live-s3/gui-restored-$RunToken.rwproj"
if (Test-Path -LiteralPath $hostData) { Remove-Item -LiteralPath $hostData -Recurse -Force }
if (Test-Path -LiteralPath $restorePath) { Remove-Item -LiteralPath $restorePath -Force }
New-Item -ItemType Directory -Path $hostData -Force | Out-Null
$priorHostData = $env:RESEARCHWEAVE_HOST_DATA_DIR
$env:RESEARCHWEAVE_HOST_DATA_DIR = $hostData
$p = $null

try {
    $p = Start-Process -FilePath $exePath -PassThru
    $window = WindowFor $p 'Live cloud GUI window did not appear'
    Set-Value $window 'Project title' "Live Liara GUI $RunToken"
    Invoke-Button $window 'Create default project'
    Wait-ForNameLike $window '*Project created in managed local storage*' 10000 | Out-Null

    $command = Named $window ([System.Windows.Automation.ControlType]::Edit) 'Command palette'
    ([System.Windows.Automation.ValuePattern]$command.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue('Cloud Sync')
    $command.SetFocus()
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Start-Sleep -Milliseconds 200

    (Named $window ([System.Windows.Automation.ControlType]::Edit) 'Cloud provider kind').SetFocus()
    Set-CloudValue $window 'Cloud provider kind' 'liara'
    Set-CloudValue $window 'Cloud profile ID' $ProfileId
    Set-CloudValue $window 'Cloud S3 endpoint' $Endpoint
    Set-CloudValue $window 'Cloud S3 bucket' $Bucket
    Set-CloudValue $window 'Cloud S3 region' 'us-east-1'
    Set-CloudValue $window 'Cloud S3 prefix' "researchweave/live-acceptance-$RunToken"
    Set-CloudValue $window 'Cloud S3 path style' 'true'
    Invoke-CloudButton $window 'Save cloud profile'
    Wait-ForNameLike $window '*Cloud profile saved locally*' 10000 | Out-Null

    # The protected workflow seeded this profile's provider credential into the
    # Windows Credential Manager before launching the app. The GUI never receives
    # the provider credential as a command-line argument or environment value.
    $passphrase = "rw-live-gui-$RunToken-32-byte-minimum-passphrase"
    Set-CloudValue $window 'Cloud project encryption passphrase' $passphrase
    Invoke-CloudButton $window 'Save cloud encryption key securely'
    Wait-ForNameLike $window '*Project sync encryption key saved securely*' 10000 | Out-Null
    Set-CloudValue $window 'Cloud sync device name' 'github-windows-uia'
    Set-CloudValue $window 'Cloud restore archive destination' $restorePath
    Invoke-CloudButton $window 'Enable automatic cloud sync'
    $statePath = Join-Path $hostData 'cloud-auto-sync.json'
    $autoSyncEnabled = $false
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        $state = Read-JsonRetry $statePath
        if ($state.enabled -eq $true -and $state.profile_id -eq $ProfileId) {
            $autoSyncEnabled = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $autoSyncEnabled) { throw 'Automatic cloud sync was not enabled for the test profile' }

    Invoke-CloudButton $window 'Test cloud connection and conditional writes' 'Backward'
    Wait-ForNameLike $window '*Cloud operation completed*' | Out-Null
    Write-Output 'LIVE_S3_GUI_STAGE_OK stage=connection'

    Invoke-CloudButton $window 'Push encrypted cloud sync now'
    $revision1 = $null
    for ($attempt = 0; $attempt -lt 300; $attempt++) {
        $state1 = Read-JsonRetry $statePath
        $revision1 = [string]$state1.expected_remote_revision
        if ($revision1 -match '^[A-Za-z0-9._-]{1,128}$') { break }
        Start-Sleep -Milliseconds 100
    }
    if ($revision1 -notmatch '^[A-Za-z0-9._-]{1,128}$') { throw 'First GUI push did not persist a valid remote revision' }
    Write-Output 'LIVE_S3_GUI_STAGE_OK stage=encrypted_push'

    Set-CloudValue $window 'Cloud expected remote revision' $revision1 'Backward'
    Invoke-CloudButton $window 'Push encrypted cloud sync now'
    Wait-ForNameLike $window '*Cloud operation completed*' | Out-Null
    $revision2 = $null
    for ($attempt = 0; $attempt -lt 160; $attempt++) {
        $state2 = Read-JsonRetry $statePath
        $revision2 = [string]$state2.expected_remote_revision
        if ($revision2 -and $revision2 -ne $revision1) { break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $revision2 -or $revision2 -eq $revision1) { throw 'Second GUI push did not advance the remote revision' }

    Set-CloudValue $window 'Cloud expected remote revision' $revision1 'Backward'
    Invoke-CloudButton $window 'Push encrypted cloud sync now'
    Wait-ForNameLike $window '*Cloud conflict preserved; no remote winner was chosen*' | Out-Null
    Write-Output 'LIVE_S3_GUI_STAGE_OK stage=conflict_preservation'

    Invoke-CloudButton $window 'View cloud sync history'
    Wait-ForNameLike $window '*Cloud operation completed*' | Out-Null
    Write-Output 'LIVE_S3_GUI_STAGE_OK stage=history'

    Invoke-CloudButton $window 'Pull latest cloud revision as copy'
    for ($attempt = 0; $attempt -lt 300; $attempt++) {
        if ((Test-Path -LiteralPath $restorePath -PathType Leaf) -and (Get-Item -LiteralPath $restorePath).Length -gt 0) { break }
        Start-Sleep -Milliseconds 100
    }
    if (-not (Test-Path -LiteralPath $restorePath -PathType Leaf) -or (Get-Item -LiteralPath $restorePath).Length -le 0) {
        throw 'Live GUI pull did not create a non-empty archive copy'
    }
    Write-Output 'LIVE_S3_GUI_STAGE_OK stage=encrypted_pull'
    Capture-WindowScreenshot $window $Screenshot

    Invoke-CloudButton $window 'Disable automatic cloud sync'
    if ((Read-JsonRetry $statePath).enabled -ne $false) {
        throw 'Automatic cloud sync remained enabled after cleanup'
    }
    Invoke-CloudButton $window 'Forget cloud encryption key' 'Backward'
    Invoke-CloudButton $window 'Disconnect cloud profile' 'Backward'
    Write-Output 'LIVE_S3_GUI_STAGE_OK stage=local_cleanup'
    Write-Output "LIVE_S3_GUI_ACCEPTANCE_OK provider=liara endpoint_host=$($endpointUri.Host)"
}
finally {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    if (Test-Path -LiteralPath $hostData) { Remove-Item -LiteralPath $hostData -Recurse -Force }
    if (Test-Path -LiteralPath $restorePath) { Remove-Item -LiteralPath $restorePath -Force }
    if ($null -eq $priorHostData) { Remove-Item Env:RESEARCHWEAVE_HOST_DATA_DIR -ErrorAction SilentlyContinue }
    else { $env:RESEARCHWEAVE_HOST_DATA_DIR = $priorHostData }
}
