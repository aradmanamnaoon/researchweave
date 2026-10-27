param(
    [string]$Exe = "",
    [int]$StartupIterations = 20,
    [int]$NavigationIterations = 100,
    [string]$ProjectPath = "",
    [int]$ProjectOpenIterations = 20,
    [string]$OutputJson = "docs/verification/rust-rewrite/performance-windows-release.json"
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

if (-not $Exe) {
    $Exe = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path 'target/release/researchweave-desktop.exe'
}
if (-not (Test-Path -LiteralPath $Exe)) { throw "Release desktop executable missing: $Exe" }
if ($StartupIterations -lt 5) { throw 'StartupIterations must be at least 5' }
if ($NavigationIterations -lt 20) { throw 'NavigationIterations must be at least 20' }
if ($ProjectPath -and $ProjectOpenIterations -lt 5) { throw 'ProjectOpenIterations must be at least 5' }

function Find-ProcessWindow([int]$ProcessId) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
        $ProcessId
    )
    return [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
        [System.Windows.Automation.TreeScope]::Children,
        $condition
    )
}

function Find-NamedDescendant(
    [System.Windows.Automation.AutomationElement]$Parent,
    [string]$Name
) {
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
    return $Parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
}

function Wait-ReadyWindow([System.Diagnostics.Process]$Process, [int]$TimeoutMs = 10000) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt $TimeoutMs) {
        if ($Process.HasExited) { throw "Desktop exited before becoming ready (exit $($Process.ExitCode))" }
        $window = Find-ProcessWindow $Process.Id
        if ($window) {
            $command = Find-NamedDescendant $window 'Command palette'
            if ($command) {
                return [pscustomobject]@{ Window = $window; Command = $command }
            }
        }
        Start-Sleep -Milliseconds 1
    }
    throw "Desktop did not expose the command palette within ${TimeoutMs}ms"
}

function Wait-NamedDescendant(
    [System.Windows.Automation.AutomationElement]$Parent,
    [string]$Name,
    [int]$TimeoutMs = 5000
) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt $TimeoutMs) {
        $item = Find-NamedDescendant $Parent $Name
        if ($item) { return $item }
        Start-Sleep -Milliseconds 1
    }
    throw "UIA element did not appear within ${TimeoutMs}ms: $Name"
}

function Percentile([double[]]$Values, [double]$P) {
    if ($Values.Count -eq 0) { return $null }
    $sorted = @($Values | Sort-Object)
    $index = [Math]::Max(0, [Math]::Min($sorted.Count - 1, [Math]::Ceiling($P * $sorted.Count) - 1))
    return [double]$sorted[$index]
}

function Distribution([double[]]$Values) {
    return [ordered]@{
        n = $Values.Count
        p50_ms = [Math]::Round((Percentile $Values 0.50), 3)
        p95_ms = [Math]::Round((Percentile $Values 0.95), 3)
        max_ms = [Math]::Round((($Values | Measure-Object -Maximum).Maximum), 3)
        min_ms = [Math]::Round((($Values | Measure-Object -Minimum).Minimum), 3)
    }
}

function Stop-Gracefully([System.Diagnostics.Process]$Process, [int]$TimeoutMs = 5000) {
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $requested = $Process.CloseMainWindow()
    if (-not $requested) {
        if (-not $Process.HasExited) { Stop-Process -Id $Process.Id -Force }
        return $null
    }
    while (-not $Process.HasExited -and $watch.ElapsedMilliseconds -lt $TimeoutMs) {
        Start-Sleep -Milliseconds 1
        $Process.Refresh()
    }
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        return $null
    }
    return [double]$watch.Elapsed.TotalMilliseconds
}

$resolvedExe = (Resolve-Path -LiteralPath $Exe).Path
$binaryHash = (Get-FileHash -LiteralPath $resolvedExe -Algorithm SHA256).Hash.ToLowerInvariant()
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$computer = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$rustc = (& rustc --version).Trim()

$previousHostData = $env:RESEARCHWEAVE_HOST_DATA_DIR
$benchmarkRoot = Join-Path $env:TEMP ('rw-perf-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $benchmarkRoot -Force | Out-Null

$firstLaunchMs = $null
$startup = New-Object System.Collections.Generic.List[double]
$shutdown = New-Object System.Collections.Generic.List[double]
$navigation = New-Object System.Collections.Generic.List[double]
$projectOpen = New-Object System.Collections.Generic.List[double]
$failures = New-Object System.Collections.Generic.List[string]
$projectMetadata = $null

$resolvedProjectPath = $null
if ($ProjectPath) {
    $resolvedProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
    $projectDatabase = Join-Path $resolvedProjectPath 'data/project.sqlite'
    if (-not (Test-Path -LiteralPath $projectDatabase)) {
        throw "Project fixture is missing data/project.sqlite: $resolvedProjectPath"
    }
    $projectBytes = (Get-ChildItem -LiteralPath $resolvedProjectPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
    $projectMetadata = [ordered]@{
        path = $resolvedProjectPath
        project_sqlite_sha256 = (Get-FileHash -LiteralPath $projectDatabase -Algorithm SHA256).Hash.ToLowerInvariant()
        file_count = @(Get-ChildItem -LiteralPath $resolvedProjectPath -Recurse -File).Count
        total_bytes = [uint64]$projectBytes
    }
}

try {
    # First launch is reported separately. It is not labeled a true OS-cold result
    # because this harness does not flush Windows filesystem/standby caches.
    $firstHost = Join-Path $benchmarkRoot 'first-launch'
    New-Item -ItemType Directory -Path $firstHost -Force | Out-Null
    $env:RESEARCHWEAVE_HOST_DATA_DIR = $firstHost
    $firstWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $firstProcess = Start-Process -FilePath $resolvedExe -PassThru
    $null = Wait-ReadyWindow $firstProcess
    $firstWatch.Stop()
    $firstLaunchMs = [double]$firstWatch.Elapsed.TotalMilliseconds
    $firstShutdown = Stop-Gracefully $firstProcess
    if ($null -ne $firstShutdown) { $shutdown.Add($firstShutdown) }

    for ($i = 0; $i -lt $StartupIterations; $i++) {
        $startupHost = Join-Path $benchmarkRoot ("startup-{0:D3}" -f $i)
        New-Item -ItemType Directory -Path $startupHost -Force | Out-Null
        $env:RESEARCHWEAVE_HOST_DATA_DIR = $startupHost
        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        $process = Start-Process -FilePath $resolvedExe -PassThru
        try {
            $null = Wait-ReadyWindow $process
            $watch.Stop()
            $startup.Add([double]$watch.Elapsed.TotalMilliseconds)
            $shutdownMs = Stop-Gracefully $process
            if ($null -eq $shutdownMs) {
                $failures.Add("startup iteration $i did not exit gracefully")
            } else {
                $shutdown.Add($shutdownMs)
            }
        } finally {
            if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        }
    }

    # Navigation is measured in one warmed release process. Timing includes UIA
    # SetValue + Enter dispatch and ends when the new work-area accessibility node appears.
    $navHost = Join-Path $benchmarkRoot 'navigation'
    New-Item -ItemType Directory -Path $navHost -Force | Out-Null
    $env:RESEARCHWEAVE_HOST_DATA_DIR = $navHost
    $navProcess = Start-Process -FilePath $resolvedExe -PassThru
    try {
        $ready = Wait-ReadyWindow $navProcess
        $window = $ready.Window
        $routes = @(
            @{ Query='Statistics'; Expected='Statistics work area' },
            @{ Query='Manuscript'; Expected='Manuscript work area' },
            @{ Query='Library'; Expected='Library work area' },
            @{ Query='Preferences'; Expected='Preferences work area' },
            @{ Query='About'; Expected='About work area' }
        )
        for ($i = 0; $i -lt $NavigationIterations; $i++) {
            $route = $routes[$i % $routes.Count]
            $command = Wait-NamedDescendant $window 'Command palette'
            $valuePattern = [System.Windows.Automation.ValuePattern]$command.GetCurrentPattern(
                [System.Windows.Automation.ValuePattern]::Pattern
            )
            $watch = [System.Diagnostics.Stopwatch]::StartNew()
            $valuePattern.SetValue($route.Query)
            $command.SetFocus()
            [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
            $null = Wait-NamedDescendant $window $route.Expected
            $watch.Stop()
            $navigation.Add([double]$watch.Elapsed.TotalMilliseconds)
        }
        $navShutdown = Stop-Gracefully $navProcess
        if ($null -ne $navShutdown) { $shutdown.Add($navShutdown) }
    } finally {
        if (-not $navProcess.HasExited) { Stop-Process -Id $navProcess.Id -Force }
    }

    if ($resolvedProjectPath) {
        $openHost = Join-Path $benchmarkRoot 'project-open'
        New-Item -ItemType Directory -Path $openHost -Force | Out-Null
        $env:RESEARCHWEAVE_HOST_DATA_DIR = $openHost
        $openProcess = Start-Process -FilePath $resolvedExe -PassThru
        try {
            $ready = Wait-ReadyWindow $openProcess
            $window = $ready.Window
            for ($i = 0; $i -lt $ProjectOpenIterations; $i++) {
                $command = Wait-NamedDescendant $window 'Command palette'
                $valuePattern = [System.Windows.Automation.ValuePattern]$command.GetCurrentPattern(
                    [System.Windows.Automation.ValuePattern]::Pattern
                )
                $valuePattern.SetValue('Welcome')
                $command.SetFocus()
                [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
                $null = Wait-NamedDescendant $window 'Welcome work area'

                $pathEdit = Wait-NamedDescendant $window 'Project path'
                $pathPattern = [System.Windows.Automation.ValuePattern]$pathEdit.GetCurrentPattern(
                    [System.Windows.Automation.ValuePattern]::Pattern
                )
                $pathPattern.SetValue($resolvedProjectPath)
                $openButton = Wait-NamedDescendant $window 'Open project'
                $invoke = [System.Windows.Automation.InvokePattern]$openButton.GetCurrentPattern(
                    [System.Windows.Automation.InvokePattern]::Pattern
                )
                $watch = [System.Diagnostics.Stopwatch]::StartNew()
                $invoke.Invoke()
                $null = Wait-NamedDescendant $window 'Dashboard work area'
                $watch.Stop()
                $projectOpen.Add([double]$watch.Elapsed.TotalMilliseconds)
            }
            $openShutdown = Stop-Gracefully $openProcess
            if ($null -ne $openShutdown) { $shutdown.Add($openShutdown) }
        } finally {
            if (-not $openProcess.HasExited) { Stop-Process -Id $openProcess.Id -Force }
        }
    }
} finally {
    $env:RESEARCHWEAVE_HOST_DATA_DIR = $previousHostData
    if (Test-Path -LiteralPath $benchmarkRoot) {
        Remove-Item -LiteralPath $benchmarkRoot -Recurse -Force
    }
}

$result = [ordered]@{
    schema = 1
    measured_at_utc = [DateTime]::UtcNow.ToString('o')
    platform = [ordered]@{
        os = $os.Caption
        version = $os.Version
        build = $os.BuildNumber
        cpu = $cpu.Name
        physical_cores = $cpu.NumberOfCores
        logical_processors = $cpu.NumberOfLogicalProcessors
        ram_bytes = [uint64]$computer.TotalPhysicalMemory
    }
    binary = [ordered]@{
        path = $resolvedExe
        sha256 = $binaryHash
        profile = 'release'
        rustc = $rustc
    }
    protocol = [ordered]@{
        startup_ready_signal = 'top-level native window + Command palette accessibility node'
        first_launch_cache_state = 'unknown; filesystem/standby cache not flushed'
        warm_startup_iterations = $StartupIterations
        navigation_iterations = $NavigationIterations
        project_open_iterations = if ($resolvedProjectPath) { $ProjectOpenIterations } else { 0 }
        navigation_routes = @('Statistics','Manuscript','Library','Preferences','About')
        navigation_measurement = 'UIA SetValue + Enter -> target work-area accessibility node'
        project_open_measurement = 'Open project Invoke -> Dashboard work-area accessibility node; same populated local fixture reopened repeatedly'
        host_state = 'new isolated RESEARCHWEAVE_HOST_DATA_DIR for each startup; one isolated host for navigation'
    }
    project_fixture = $projectMetadata
    first_launch_ms = [Math]::Round($firstLaunchMs, 3)
    warm_startup = Distribution $startup.ToArray()
    warm_startup_samples_ms = @($startup | ForEach-Object { [Math]::Round($_, 3) })
    navigation = Distribution $navigation.ToArray()
    navigation_samples_ms = @($navigation | ForEach-Object { [Math]::Round($_, 3) })
    project_open = if ($projectOpen.Count -gt 0) { Distribution $projectOpen.ToArray() } else { $null }
    project_open_samples_ms = @($projectOpen | ForEach-Object { [Math]::Round($_, 3) })
    graceful_shutdown = Distribution $shutdown.ToArray()
    graceful_shutdown_samples_ms = @($shutdown | ForEach-Object { [Math]::Round($_, 3) })
    failures = @($failures)
}

$outputPath = if ([IO.Path]::IsPathRooted($OutputJson)) {
    $OutputJson
} else {
    Join-Path (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path $OutputJson
}
$outputDirectory = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outputPath -Encoding UTF8
$result | ConvertTo-Json -Depth 8
