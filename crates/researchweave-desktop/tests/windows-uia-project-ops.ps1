param([string]$Exe = "")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
if (!$Exe) { $Exe = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path 'target/debug/researchweave-desktop.exe' }
if (!(Test-Path $Exe)) { throw "Build desktop first" }
$root = Join-Path $env:TEMP ("rw-project-ops-" + [guid]::NewGuid().ToString("N"))
$hostRoot = Join-Path $env:TEMP ("rw-project-ops-host-" + [guid]::NewGuid().ToString("N"))
$old = $env:RESEARCHWEAVE_HOST_DATA_DIR
$env:RESEARCHWEAVE_HOST_DATA_DIR = $hostRoot
New-Item -ItemType Directory -Path $hostRoot -Force | Out-Null
$p=$null
function Find($w,$type,[string]$name) {
    $condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,$type)
    for($n=0;$n -lt 40;$n++) {
        foreach($item in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)) {
            if($item.Current.Name -eq $name) { return $item }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "UIA missing $name"
}
function Window($process) {
    Start-Sleep -Seconds 2
    $c=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty,$process.Id)
    $w=[System.Windows.Automation.AutomationElement]::RootElement.FindFirst([System.Windows.Automation.TreeScope]::Children,$c)
    if(!$w){throw "Native window missing"}
    return $w
}
function Invoke($w,[string]$name) {
    $button=Find $w ([System.Windows.Automation.ControlType]::Button) $name
    ([System.Windows.Automation.InvokePattern]$button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke()
}
function Edit($w,[string]$name,[string]$value) {
    $control=Find $w ([System.Windows.Automation.ControlType]::Edit) $name
    ([System.Windows.Automation.ValuePattern]$control.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue($value)
}
function Page($w,[string]$page,[string]$button) {
    $command=Find $w ([System.Windows.Automation.ControlType]::Edit) 'Command palette'
    ([System.Windows.Automation.ValuePattern]$command.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).SetValue($page)
    $command.SetFocus()
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    $null=Find $w ([System.Windows.Automation.ControlType]::Button) $button
}
function AllNames($w) {
    return @($w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object {$_.Current.Name})
}
function AssertNoSentinel($w,[string]$root,[string]$needle) {
    $names=(AllNames $w) -join ' '
    if($names.Contains($needle)){throw "Private sentinel leaked into accessible output"}
    foreach($name in @('ai-profiles.json','operation-audit.sqlite')) {
        $file=Join-Path $root $name
        if(Test-Path $file) {
            $bytes=[System.IO.File]::ReadAllBytes($file)
            $raw=[System.Text.Encoding]::UTF8.GetString($bytes)
            if($raw.Contains($needle)){throw "Private sentinel leaked into local host metadata"}
        }
    }
}
try {
    $p=Start-Process -FilePath $Exe -PassThru
    $w=Window $p
    Edit $w 'Project path' $root
    Edit $w 'Project title' 'SENTINEL_DIAGNOSTIC_PRIVATE_2197'
    Invoke $w 'Create project'
    Start-Sleep -Milliseconds 400
    Page $w 'Diagnostics' 'Run project diagnostics'
    Invoke $w 'Run project diagnostics'
    Start-Sleep -Milliseconds 200
    $names=AllNames $w
    if(-not ($names | Where-Object {$_ -like '*Structural checks only*' -and $_ -like '*Checks:*' })) {throw "Diagnostics did not show bounded structural checks"}
    $diagnosticSummary=($names | Where-Object {$_ -like 'Project diagnostics summary *'}) -join ' '
    if($diagnosticSummary.Contains('SENTINEL_DIAGNOSTIC_PRIVATE_2197')) { throw "Diagnostics leaked private title into bounded results" }
    Write-Output 'PASS: Diagnostics summary and checked/unavailable coverage through project.diagnostics'
    Page $w 'Activity' 'Load project activity'
    Edit $w 'Activity exact operation filter' 'project.create'
    Edit $w 'Activity offset' '0'
    Edit $w 'Activity limit' '10'
    Invoke $w 'Load project activity'
    Start-Sleep -Milliseconds 180
    $names=AllNames $w
    if(-not ($names | Where-Object {$_ -like '*actor_authenticated=false*' -and $_ -like '*Verified:*' })) { Write-Output ("DIAGNOSTIC activity: " + (($names | Where-Object {$_ -like '*activity*' -or $_ -like '*Verified*' -or $_ -like '*invalid*'}) -join ' | ')); throw "Activity provenance disclaimer/result missing"}
    Invoke $w 'Clear project activity view'
    if(-not ((AllNames $w) | Where-Object {$_ -like '*View cleared only*'})){throw 'Clear-view did not retain provenance disclaimer'}
    Write-Output 'PASS: bounded filtered activity and clear-view are payload-free'
    Page $w 'Providers' 'List stored provider profiles'
    Edit $w 'Provider ID' 'uia-provider'
    Edit $w 'Provider kind' 'open_ai_compatible'
    Edit $w 'Provider model' 'research-model'
    Edit $w 'Provider endpoint' 'https://api.example.org/v1'
    Edit $w 'Provider local flag' 'false'
    Edit $w 'Provider model' ''
    Invoke $w 'Preview configure provider profile'
    if(-not ((AllNames $w) | Where-Object {$_ -like '*Invalid or unavailable profile action*'})){throw 'Invalid provider model unexpectedly previewed'}
    Edit $w 'Provider model' 'research-model'
    Invoke $w 'Preview configure provider profile'
    Invoke $w 'Record approved provider profile change'
    Start-Sleep -Milliseconds 200
    Invoke $w 'List stored provider profiles'
    Start-Sleep -Milliseconds 200
    if(-not ((AllNames $w) | Where-Object {$_ -like '*uia-provider*' -and $_ -like '*health=not_checked*'})){throw 'Configured profile not listed as metadata'}
    $file=Join-Path $hostRoot 'ai-profiles.json'
    if(!(Test-Path $file)){throw 'Host profile store missing'}
    AssertNoSentinel $w $hostRoot 'SENTINEL_PRIVATE_PAYLOAD_2739'
    Stop-Process -Id $p.Id -Force
    $p.WaitForExit()
    $p=Start-Process -FilePath $Exe -PassThru
    $w=Window $p
    Edit $w 'Project path' $root
    Invoke $w 'Open project'
    Start-Sleep -Milliseconds 250
    Page $w 'Providers' 'List stored provider profiles'
    Invoke $w 'List stored provider profiles'
    if(-not ((AllNames $w) | Where-Object {$_ -like '*uia-provider*' -and $_ -like '*health=not_checked*'})){throw 'Profile missing after restart'}
    Edit $w 'Provider ID' 'uia-provider'
    Edit $w 'Provider kind' 'open_ai_compatible'
    Edit $w 'Provider model' 'research-model-2'
    Edit $w 'Provider endpoint' 'https://api.example.org/v1'
    Edit $w 'Provider local flag' 'false'
    Invoke $w 'Preview update provider profile'
    Invoke $w 'Record approved provider profile change'
    Invoke $w 'List stored provider profiles'
    if(-not ((AllNames $w) | Where-Object {$_ -like '*research-model-2*'})){throw 'Profile update not observed'}
    Edit $w 'Provider endpoint' 'https://invalid.example.org/?api_key=SENTINEL_PRIVATE_PAYLOAD_2739'
    Invoke $w 'Preview update provider profile'
    if(-not ((AllNames $w) | Where-Object {$_ -like '*Invalid or unavailable profile action*'})){throw 'Credential-bearing URL was not rejected before preview'}
    $raw=[System.IO.File]::ReadAllText($file)
    if($raw.Contains('SENTINEL_PRIVATE_PAYLOAD_2739')){throw 'Invalid endpoint stored private sentinel'}
    Edit $w 'Provider ID' 'uia-provider'
    Invoke $w 'Preview disconnect provider profile'
    Invoke $w 'Record approved provider profile change'
    Invoke $w 'List stored provider profiles'
    if(((AllNames $w) | Where-Object {$_ -like '*uia-provider*' -and $_ -like '*health=not_checked*'})){throw 'Disconnected provider still listed'}
    AssertNoSentinel $w $hostRoot 'SENTINEL_PRIVATE_PAYLOAD_2739'
    Write-Output 'PASS: Configure/approved record/restart/update/disconnect provider metadata, no secret disclosure'
} finally {
    if($p -and !$p.HasExited){Stop-Process -Id $p.Id -Force}
    foreach($dir in @($root,$hostRoot)) { if(Test-Path $dir){Remove-Item -LiteralPath $dir -Force -Recurse} }
    $env:RESEARCHWEAVE_HOST_DATA_DIR=$old
}
