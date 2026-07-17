<#
start.ps1 - Start the backend and frontend on Windows.

Usage:
    .\start.ps1
    .\start.ps1 -Mock
    .\start.ps1 -Wait
    .\start.ps1 -BackendPort 9000 -FrontendPort 5174

Default mode performs lightweight preflight checks, starts a detached worker, and
returns the caller terminal immediately. Use -Wait for foreground diagnostics.
Compatible with Windows PowerShell 5.1.
#>

[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173,
    [switch]$SkipInstall,
    [switch]$Mock,
    [switch]$Wait,
    [switch]$Worker
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot '.runtime'
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'

$BackendPidFile = Join-Path $RuntimeDir 'backend.pid'
$FrontendPidFile = Join-Path $RuntimeDir 'frontend.pid'
$BackendStartFile = Join-Path $RuntimeDir 'backend.start'
$FrontendStartFile = Join-Path $RuntimeDir 'frontend.start'
$BackendPortFile = Join-Path $RuntimeDir 'backend.port'
$FrontendPortFile = Join-Path $RuntimeDir 'frontend.port'
$StartupPidFile = Join-Path $RuntimeDir 'startup.pid'
$StartupStateFile = Join-Path $RuntimeDir 'startup.state'
$StartupMessageFile = Join-Path $RuntimeDir 'startup.message'

$StartupOutLog = Join-Path $RuntimeDir 'startup.out.log'
$StartupErrLog = Join-Path $RuntimeDir 'startup.err.log'
$BackendLog = Join-Path $RuntimeDir 'backend.out.log'
$BackendErr = Join-Path $RuntimeDir 'backend.err.log'
$FrontendLog = Join-Path $RuntimeDir 'frontend.out.log'
$FrontendErr = Join-Path $RuntimeDir 'frontend.err.log'

$WorkerInputFile = Join-Path $RuntimeDir 'worker.stdin'
$BackendInputFile = Join-Path $RuntimeDir 'backend.stdin'
$FrontendInputFile = Join-Path $RuntimeDir 'frontend.stdin'

if (-not (Test-Path -LiteralPath $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

function Set-StartupState {
    param(
        [ValidateSet('starting', 'running', 'failed')][string]$State,
        [string]$Message = ''
    )

    Set-Content -LiteralPath $StartupStateFile -Value $State -Encoding Ascii -NoNewline
    Set-Content -LiteralPath $StartupMessageFile -Value $Message -Encoding UTF8 -NoNewline
}

function Get-StartupState {
    if (-not (Test-Path -LiteralPath $StartupStateFile)) {
        return ''
    }
    return (Get-Content -LiteralPath $StartupStateFile -Raw).Trim()
}

function Get-StartupMessage {
    if (-not (Test-Path -LiteralPath $StartupMessageFile)) {
        return ''
    }
    return (Get-Content -LiteralPath $StartupMessageFile -Raw).Trim()
}

function Reset-DetachedInputFiles {
    foreach ($path in @($WorkerInputFile, $BackendInputFile, $FrontendInputFile)) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        Set-Content -LiteralPath $path -Value '' -Encoding Ascii -NoNewline
    }
}

function Ensure-DetachedInputFiles {
    foreach ($path in @($WorkerInputFile, $BackendInputFile, $FrontendInputFile)) {
        if (-not (Test-Path -LiteralPath $path)) {
            Set-Content -LiteralPath $path -Value '' -Encoding Ascii -NoNewline
        }
    }
}

function Get-TrackedProcess {
    param([string]$PidFile)

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $null
    }

    $value = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($value -notmatch '^\d+$') {
        return $null
    }

    return Get-Process -Id ([int]$value) -ErrorAction SilentlyContinue
}

function Get-PortOwner {
    param([int]$Port)

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
        return $null
    }

    $processId = [int]$listeners[0].OwningProcess
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue

    $processName = '<unknown>'
    if ($null -ne $process) {
        $processName = $process.ProcessName
    }

    $commandLine = '<unavailable>'
    if ($null -ne $cim) {
        $commandLine = [string]$cim.CommandLine
    }

    return [PSCustomObject]@{
        Pid = $processId
        Name = $processName
        CommandLine = $commandLine
    }
}

function Assert-PortsAvailable {
    if ($BackendPort -eq $FrontendPort) {
        throw 'Backend and frontend ports must be different.'
    }

    foreach ($item in @(
        [PSCustomObject]@{ Name = 'backend'; Port = $BackendPort },
        [PSCustomObject]@{ Name = 'frontend'; Port = $FrontendPort }
    )) {
        $owner = Get-PortOwner -Port $item.Port
        if ($null -ne $owner) {
            $message = "{0} port {1} is already in use: PID={2}, process={3}`nCommand line: {4}`nRun .\stop.ps1 first or choose another port." -f $item.Name, $item.Port, $owner.Pid, $owner.Name, $owner.CommandLine
            throw $message
        }
    }
}

function Assert-NoTrackedProcesses {
    $startup = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $startup) {
        throw "A startup worker is already running, PID=$($startup.Id). Run .\status.ps1."
    }

    $backend = Get-TrackedProcess -PidFile $BackendPidFile
    if ($null -ne $backend) {
        throw "Backend is already running, PID=$($backend.Id). Run .\stop.ps1 first."
    }

    $frontend = Get-TrackedProcess -PidFile $FrontendPidFile
    if ($null -ne $frontend) {
        throw "Frontend is already running, PID=$($frontend.Id). Run .\stop.ps1 first."
    }
}

function Resolve-Python312 {
    $python = ''

    $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -ne $pyCommand) {
        $output = & $pyCommand.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $python = (@($output) | Select-Object -Last 1).Trim()
        }
    }

    if ([string]::IsNullOrWhiteSpace($python)) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($null -ne $pythonCommand) {
            $candidate = $pythonCommand.Source
            $version = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if (($LASTEXITCODE -eq 0) -and (($version | Select-Object -Last 1).Trim() -eq '3.12')) {
                $python = $candidate
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($python)) {
        throw 'Python 3.12 was not found. Install it or expose it through py.exe/python.exe.'
    }
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Python 3.12 executable does not exist: $python"
    }

    return $python
}

function Resolve-DeepSeekKey {
    if (-not [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
        return $env:DEEPSEEK_API_KEY.Trim()
    }

    $candidates = @(
        (Join-Path $ProjectRoot 'deepseek-apikey'),
        (Join-Path (Split-Path $ProjectRoot -Parent) 'deepseek-apikey')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $value = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $candidate)).Trim()
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                return $value
            }
        }
    }

    throw "DeepSeek key was not found. Set DEEPSEEK_API_KEY or create 'deepseek-apikey' in the project directory or its parent. Use -Mock for mock mode."
}

function Assert-ApplicationConfiguration {
    [void](Resolve-Python312)

    if (-not $Mock) {
        [void](Resolve-DeepSeekKey)
        $ragDb = Join-Path $ProjectRoot 'data\bazi_rag_dataset_v2_1\import\sqlite\bazi_rag.sqlite'
        if (-not (Test-Path -LiteralPath $ragDb)) {
            throw "RAG SQLite database does not exist: $ragDb. Use -Mock only for UI testing."
        }
    }
}

function Wait-HttpReady {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds,
        [string]$Description
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Milliseconds 300
    }

    throw "$Description was not ready within $TimeoutSeconds seconds: $Uri"
}

function Start-Backend {
    param([string]$Python)

    Set-Location $BackendDir
    & $Python -c "import fastapi, uvicorn, app" 2>$null
    $dependenciesReady = ($LASTEXITCODE -eq 0)
    if ((-not $dependenciesReady) -and $SkipInstall) {
        throw 'Backend dependencies are missing and -SkipInstall was specified.'
    }
    if (-not $dependenciesReady) {
        Write-Host 'SETUP Installing backend dependencies...' -ForegroundColor Cyan
        & $Python -m pip install -e '.[dev]'
        if ($LASTEXITCODE -ne 0) {
            throw 'Backend dependency installation failed.'
        }
    }

    $previousKey = $env:DEEPSEEK_API_KEY
    $hadPreviousKey = Test-Path Env:DEEPSEEK_API_KEY
    if (-not $Mock) {
        $env:DEEPSEEK_API_KEY = Resolve-DeepSeekKey
    }

    try {
        $quotedBackendDir = '"{0}"' -f $BackendDir
        $arguments = @(
            '-m', 'uvicorn', 'app.main:app',
            '--app-dir', $quotedBackendDir,
            '--host', '127.0.0.1',
            '--port', [string]$BackendPort,
            '--log-level', 'info'
        )
        $process = Start-Process `
            -FilePath $Python `
            -ArgumentList $arguments `
            -WorkingDirectory $BackendDir `
            -RedirectStandardInput $BackendInputFile `
            -RedirectStandardOutput $BackendLog `
            -RedirectStandardError $BackendErr `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        if ($hadPreviousKey) {
            $env:DEEPSEEK_API_KEY = $previousKey
        } else {
            Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
        }
    }

    $process.Id | Set-Content -LiteralPath $BackendPidFile -NoNewline
    $process.StartTime.ToUniversalTime().Ticks | Set-Content -LiteralPath $BackendStartFile -NoNewline
    return $process
}

function Start-Frontend {
    Set-Location $FrontendDir

    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (($null -eq $nodeCommand) -or ($null -eq $npmCommand)) {
        throw 'Node.js or npm was not found.'
    }

    $viteScript = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path -LiteralPath $viteScript)) {
        if ($SkipInstall) {
            throw 'Frontend dependencies are missing and -SkipInstall was specified.'
        }
        Write-Host 'SETUP Installing frontend dependencies...' -ForegroundColor Cyan
        & $npmCommand.Source install --prefer-offline --no-audit --no-fund --no-progress
        if ($LASTEXITCODE -ne 0) {
            throw 'Frontend dependency installation failed.'
        }
    }

    $previousMock = $env:VITE_USE_MOCKS
    $hadPreviousMock = Test-Path Env:VITE_USE_MOCKS
    $previousTarget = $env:VITE_API_TARGET
    $hadPreviousTarget = Test-Path Env:VITE_API_TARGET

    if ($Mock) {
        $env:VITE_USE_MOCKS = 'true'
    } else {
        Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue
    }
    $env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"

    try {
        $quotedViteScript = '"{0}"' -f $viteScript
        $arguments = @(
            $quotedViteScript,
            '--host', '127.0.0.1',
            '--port', [string]$FrontendPort
        )
        $process = Start-Process `
            -FilePath $nodeCommand.Source `
            -ArgumentList $arguments `
            -WorkingDirectory $FrontendDir `
            -RedirectStandardInput $FrontendInputFile `
            -RedirectStandardOutput $FrontendLog `
            -RedirectStandardError $FrontendErr `
            -WindowStyle Hidden `
            -PassThru
    } finally {
        if ($hadPreviousMock) {
            $env:VITE_USE_MOCKS = $previousMock
        } else {
            Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue
        }
        if ($hadPreviousTarget) {
            $env:VITE_API_TARGET = $previousTarget
        } else {
            Remove-Item Env:VITE_API_TARGET -ErrorAction SilentlyContinue
        }
    }

    $process.Id | Set-Content -LiteralPath $FrontendPidFile -NoNewline
    $process.StartTime.ToUniversalTime().Ticks | Set-Content -LiteralPath $FrontendStartFile -NoNewline
    return $process
}

function Stop-StartedServices {
    foreach ($pidFile in @($FrontendPidFile, $BackendPidFile)) {
        if (-not (Test-Path -LiteralPath $pidFile)) {
            continue
        }
        $value = (Get-Content -LiteralPath $pidFile -Raw).Trim()
        if ($value -match '^\d+$') {
            & taskkill.exe /F /T /PID ([int]$value) 2>&1 | Out-Null
        }
    }

    Remove-Item -LiteralPath $BackendPidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $FrontendPidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BackendStartFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $FrontendStartFile -Force -ErrorAction SilentlyContinue
}

function Invoke-StartupWorker {
    $exitCode = 0
    Set-StartupState -State 'starting' -Message 'Startup checks are running.'

    try {
        Ensure-DetachedInputFiles
        Assert-NoTrackedProcesses
        Assert-PortsAvailable
        Assert-ApplicationConfiguration

        $BackendPort | Set-Content -LiteralPath $BackendPortFile -NoNewline
        $FrontendPort | Set-Content -LiteralPath $FrontendPortFile -NoNewline

        $python = Resolve-Python312
        Write-Host "START backend on http://127.0.0.1:$BackendPort" -ForegroundColor Green
        $backend = Start-Backend -Python $python
        Write-Host "START frontend on http://127.0.0.1:$FrontendPort" -ForegroundColor Green
        $frontend = Start-Frontend

        [void](Wait-HttpReady -Uri "http://127.0.0.1:$BackendPort/api/v1/health" -TimeoutSeconds 25 -Description 'Backend')
        [void](Wait-HttpReady -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 25 -Description 'Frontend')
        [void](Wait-HttpReady -Uri "http://127.0.0.1:$FrontendPort/api/v1/health" -TimeoutSeconds 10 -Description 'Frontend API proxy')

        $message = "Backend PID=$($backend.Id); frontend PID=$($frontend.Id)."
        Set-StartupState -State 'running' -Message $message
        Write-Host "OK $message" -ForegroundColor Green
    } catch {
        $exitCode = 1
        $message = $_.Exception.Message
        Set-StartupState -State 'failed' -Message $message
        Write-Host "ERROR: $message" -ForegroundColor Red
        Stop-StartedServices
    } finally {
        if ($Worker) {
            Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
        }
        Set-Location $ProjectRoot
    }

    return $exitCode
}

function Find-PowerShellExecutable {
    $current = Get-Process -Id $PID -ErrorAction SilentlyContinue
    if ($null -ne $current) {
        if (-not [string]::IsNullOrWhiteSpace($current.Path)) {
            return $current.Path
        }
    }

    foreach ($candidate in @(
        (Join-Path $PSHOME 'powershell.exe'),
        (Join-Path $PSHOME 'pwsh.exe')
    )) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw 'Unable to locate a PowerShell executable.'
}

function Start-DetachedWorker {
    Assert-NoTrackedProcesses
    Assert-PortsAvailable
    Assert-ApplicationConfiguration

    Reset-DetachedInputFiles
    Remove-Item -LiteralPath $StartupOutLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StartupErrLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StartupStateFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StartupMessageFile -Force -ErrorAction SilentlyContinue
    Set-StartupState -State 'starting' -Message 'Detached startup worker has been submitted.'

    $powerShellExe = Find-PowerShellExecutable
    $arguments = @(
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-Worker',
        '-BackendPort', [string]$BackendPort,
        '-FrontendPort', [string]$FrontendPort
    )
    if ($SkipInstall) {
        $arguments += '-SkipInstall'
    }
    if ($Mock) {
        $arguments += '-Mock'
    }

    $startup = Start-Process `
        -FilePath $powerShellExe `
        -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardInput $WorkerInputFile `
        -RedirectStandardOutput $StartupOutLog `
        -RedirectStandardError $StartupErrLog `
        -WindowStyle Hidden `
        -PassThru

    $startup.Id | Set-Content -LiteralPath $StartupPidFile -NoNewline

    $deadline = (Get-Date).AddSeconds(3)
    while ((Get-Date) -lt $deadline) {
        $state = Get-StartupState
        if ($state -eq 'running') {
            Write-Host "OK    $(Get-StartupMessage)" -ForegroundColor Green
            Write-Host "OPEN  http://127.0.0.1:$FrontendPort" -ForegroundColor Cyan
            return
        }
        if ($state -eq 'failed') {
            throw (Get-StartupMessage)
        }
        if ($startup.HasExited) {
            $message = Get-StartupMessage
            if ([string]::IsNullOrWhiteSpace($message)) {
                $message = 'The detached startup worker exited before reporting a state.'
            }
            throw $message
        }
        Start-Sleep -Milliseconds 150
    }

    Write-Host "START Background startup submitted, PID=$($startup.Id)." -ForegroundColor Green
    Write-Host 'STATUS .\status.ps1' -ForegroundColor Cyan
    Write-Host "LOG    Get-Content '$StartupOutLog' -Wait" -ForegroundColor Cyan
}

if ($Worker) {
    $code = Invoke-StartupWorker
    exit $code
}

if ($Wait) {
    try {
        Assert-NoTrackedProcesses
        Assert-PortsAvailable
        Assert-ApplicationConfiguration
        Reset-DetachedInputFiles
        Remove-Item -LiteralPath $StartupOutLog -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $StartupErrLog -Force -ErrorAction SilentlyContinue
        $code = Invoke-StartupWorker
        exit $code
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

try {
    Start-DetachedWorker
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
