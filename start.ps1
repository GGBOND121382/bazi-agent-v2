<#
start.ps1 - Start backend and frontend in the background.

Usage:
    .\start.ps1
    .\start.ps1 -Mock
    .\start.ps1 -Wait
    .\start.ps1 -BackendPort 9000 -FrontendPort 5174

By default, dependency checks, process startup, and health checks run in a hidden
background PowerShell process, so the current terminal returns immediately.
Use -Wait to run startup checks in the current terminal.
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
$BackendPidFile = Join-Path $RuntimeDir 'backend.pid'
$FrontendPidFile = Join-Path $RuntimeDir 'frontend.pid'
$BackendStartFile = Join-Path $RuntimeDir 'backend.start'
$FrontendStartFile = Join-Path $RuntimeDir 'frontend.start'
$BackendPortFile = Join-Path $RuntimeDir 'backend.port'
$FrontendPortFile = Join-Path $RuntimeDir 'frontend.port'
$StartupPidFile = Join-Path $RuntimeDir 'startup.pid'
$StartupOutLog = Join-Path $RuntimeDir 'startup.out.log'
$StartupErrLog = Join-Path $RuntimeDir 'startup.err.log'
$BackendLog = Join-Path $RuntimeDir 'backend.out.log'
$BackendErr = Join-Path $RuntimeDir 'backend.err.log'
$FrontendLog = Join-Path $RuntimeDir 'frontend.out.log'
$FrontendErr = Join-Path $RuntimeDir 'frontend.err.log'

if (-not (Test-Path -LiteralPath $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
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

    $checks = @(
        [PSCustomObject]@{ Name = 'backend'; Port = $BackendPort },
        [PSCustomObject]@{ Name = 'frontend'; Port = $FrontendPort }
    )

    foreach ($item in $checks) {
        $owner = Get-PortOwner -Port $item.Port
        if ($null -ne $owner) {
            $message = "{0} port {1} is already in use: PID={2}, process={3}`nCommand line: {4}`nRun .\stop.ps1 first or choose another port." -f $item.Name, $item.Port, $owner.Pid, $owner.Name, $owner.CommandLine
            throw $message
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

    Write-Host "TIMEOUT $Description was not ready within $TimeoutSeconds seconds: $Uri" -ForegroundColor Red
    return $false
}

function Find-PowerShellExecutable {
    $currentProcess = Get-Process -Id $PID -ErrorAction SilentlyContinue
    $hasCurrentPath = $false
    if ($null -ne $currentProcess) {
        $hasCurrentPath = -not [string]::IsNullOrWhiteSpace($currentProcess.Path)
    }
    if ($hasCurrentPath) {
        return $currentProcess.Path
    }

    $windowsPowerShell = Join-Path $PSHOME 'powershell.exe'
    if (Test-Path -LiteralPath $windowsPowerShell) {
        return $windowsPowerShell
    }

    $powerShellCore = Join-Path $PSHOME 'pwsh.exe'
    if (Test-Path -LiteralPath $powerShellCore) {
        return $powerShellCore
    }

    throw 'Unable to locate a PowerShell executable.'
}

function Start-DetachedWorker {
    $startupProcess = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $startupProcess) {
        throw "A startup worker is already running, PID=$($startupProcess.Id). Run .\status.ps1."
    }
    Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue

    $backendProcess = Get-TrackedProcess -PidFile $BackendPidFile
    $frontendProcess = Get-TrackedProcess -PidFile $FrontendPidFile
    if ($null -ne $backendProcess) {
        throw 'Backend is already running. Run .\stop.ps1 first.'
    }
    if ($null -ne $frontendProcess) {
        throw 'Frontend is already running. Run .\stop.ps1 first.'
    }

    Assert-PortsAvailable
    Remove-Item -LiteralPath $StartupOutLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StartupErrLog -Force -ErrorAction SilentlyContinue

    $powerShellExe = Find-PowerShellExecutable
    $quotedScriptPath = '"{0}"' -f $PSCommandPath
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $quotedScriptPath,
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

    $startup = Start-Process -FilePath $powerShellExe -ArgumentList $arguments -WorkingDirectory $ProjectRoot -RedirectStandardOutput $StartupOutLog -RedirectStandardError $StartupErrLog -WindowStyle Hidden -PassThru
    $startup.Id | Set-Content -LiteralPath $StartupPidFile -NoNewline

    Start-Sleep -Milliseconds 350
    if ($startup.HasExited) {
        $details = ''
        if (Test-Path -LiteralPath $StartupErrLog) {
            $details = @(Get-Content -LiteralPath $StartupErrLog -Tail 30 -ErrorAction SilentlyContinue) -join "`n"
        }
        throw "The background startup worker exited immediately.`n$details"
    }

    Write-Host "START Background startup submitted, PID=$($startup.Id). The current terminal is free." -ForegroundColor Green
    Write-Host 'STATUS .\status.ps1' -ForegroundColor Cyan
    Write-Host "LOG    Get-Content '$StartupOutLog' -Wait" -ForegroundColor Cyan
    Write-Host "ERROR  Get-Content '$StartupErrLog' -Wait" -ForegroundColor Cyan
}

function Resolve-Python312 {
    $pythonOutput = & py.exe -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.12 was not found through py.exe.'
    }

    $python = (@($pythonOutput) | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($python)) {
        throw 'Unable to resolve the Python 3.12 executable path.'
    }
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Python 3.12 executable does not exist: $python"
    }

    return $python
}

function Start-Backend {
    param([string]$Python)

    $backendDir = Join-Path $ProjectRoot 'backend'
    Set-Location $backendDir

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

    $keyFile = Join-Path (Split-Path $ProjectRoot -Parent) 'deepseek-apikey'
    $previousKey = $env:DEEPSEEK_API_KEY
    $hadPreviousKey = Test-Path Env:DEEPSEEK_API_KEY

    if (-not $Mock) {
        if (-not (Test-Path -LiteralPath $keyFile)) {
            throw 'DeepSeek key file was not found. Use -Mock for mock mode.'
        }
        $resolvedKeyFile = Resolve-Path -LiteralPath $keyFile
        $env:DEEPSEEK_API_KEY = [IO.File]::ReadAllText($resolvedKeyFile).Trim()
        if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
            throw 'DeepSeek key file is empty.'
        }

        $ragDb = Join-Path $ProjectRoot 'data\bazi_rag_dataset_v2_1\import\sqlite\bazi_rag.sqlite'
        if (-not (Test-Path -LiteralPath $ragDb)) {
            throw "RAG SQLite database does not exist: $ragDb"
        }
    }

    Write-Host "START backend uvicorn (port $BackendPort)..." -ForegroundColor Green
    try {
        $quotedBackendDir = '"{0}"' -f $backendDir
        $arguments = @(
            '-m', 'uvicorn', 'app.main:app',
            '--app-dir', $quotedBackendDir,
            '--host', '127.0.0.1',
            '--port', [string]$BackendPort,
            '--log-level', 'info'
        )
        $process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $backendDir -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErr -WindowStyle Hidden -PassThru
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
    $frontendDir = Join-Path $ProjectRoot 'frontend'
    Set-Location $frontendDir

    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (($null -eq $nodeCommand) -or ($null -eq $npmCommand)) {
        throw 'Node.js or npm was not found.'
    }

    $viteScript = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path -LiteralPath $viteScript)) {
        if ($SkipInstall) {
            throw 'Frontend dependencies are missing and -SkipInstall was specified.'
        }
        Write-Host 'SETUP Installing frontend dependencies...' -ForegroundColor Cyan
        & npm.cmd install --prefer-offline --no-audit --no-fund --no-progress
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

    Write-Host "START frontend Vite (port $FrontendPort)..." -ForegroundColor Green
    try {
        $quotedViteScript = '"{0}"' -f $viteScript
        $arguments = @(
            $quotedViteScript,
            '--host', '127.0.0.1',
            '--port', [string]$FrontendPort
        )
        $process = Start-Process -FilePath $nodeCommand.Source -ArgumentList $arguments -WorkingDirectory $frontendDir -RedirectStandardOutput $FrontendLog -RedirectStandardError $FrontendErr -WindowStyle Hidden -PassThru
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

function Invoke-StartWorker {
    Set-Location $ProjectRoot

    $backendProcess = Get-TrackedProcess -PidFile $BackendPidFile
    $frontendProcess = Get-TrackedProcess -PidFile $FrontendPidFile
    if ($null -ne $backendProcess) {
        throw 'Backend is already running. Run .\stop.ps1 first.'
    }
    if ($null -ne $frontendProcess) {
        throw 'Frontend is already running. Run .\stop.ps1 first.'
    }

    Assert-PortsAvailable
    $BackendPort | Set-Content -LiteralPath $BackendPortFile -NoNewline
    $FrontendPort | Set-Content -LiteralPath $FrontendPortFile -NoNewline

    $python = Resolve-Python312
    $backend = Start-Backend -Python $python
    $frontend = Start-Frontend

    Write-Host 'HEALTH Waiting for backend...' -ForegroundColor Cyan
    $backendReady = Wait-HttpReady -Uri "http://127.0.0.1:$BackendPort/api/v1/health" -TimeoutSeconds 20 -Description 'backend'
    if (-not $backendReady) {
        throw "Backend did not become ready. Logs: $BackendLog / $BackendErr"
    }

    Write-Host 'HEALTH Waiting for frontend and API proxy...' -ForegroundColor Cyan
    $frontendReady = Wait-HttpReady -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 20 -Description 'frontend page'
    $proxyReady = Wait-HttpReady -Uri "http://127.0.0.1:$FrontendPort/api/v1/health" -TimeoutSeconds 10 -Description 'frontend API proxy'
    if ((-not $frontendReady) -or (-not $proxyReady)) {
        throw "Frontend or API proxy did not become ready. Logs: $FrontendLog / $FrontendErr"
    }

    Write-Host "OK    backend http://127.0.0.1:$BackendPort (pid $($backend.Id))" -ForegroundColor Green
    Write-Host "OK    frontend http://127.0.0.1:$FrontendPort (pid $($frontend.Id))" -ForegroundColor Green
    Write-Host 'STOP  .\stop.ps1' -ForegroundColor Cyan
}

if ((-not $Worker) -and (-not $Wait)) {
    try {
        Start-DetachedWorker
        exit 0
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

$exitCode = 0
try {
    Invoke-StartWorker
} catch {
    $exitCode = 1
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    try {
        & (Join-Path $ProjectRoot 'stop.ps1') -Force -BackendPort $BackendPort -FrontendPort $FrontendPort
    } catch {
    }
} finally {
    if ($Worker) {
        Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
    }
    Set-Location $ProjectRoot
}

exit $exitCode
