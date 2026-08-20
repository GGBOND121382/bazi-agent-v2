<#
stop.ps1 - Stop backend, frontend, and background startup worker.

Usage:
    .\stop.ps1
    .\stop.ps1 -Force
    .\stop.ps1 -BackendPort 9000 -FrontendPort 5174

Compatible with Windows PowerShell 5.1. If PID files are missing, the script
checks listening ports and process command lines. Unknown processes are not killed.
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [ValidateRange(0, 65535)][int]$BackendPort = 0,
    [ValidateRange(0, 65535)][int]$FrontendPort = 0
)

$ErrorActionPreference = 'SilentlyContinue'
$ProjectRoot = $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot '.runtime'
$BackendPidFile = Join-Path $RuntimeDir 'backend.pid'
$FrontendPidFile = Join-Path $RuntimeDir 'frontend.pid'
$BackendStartFile = Join-Path $RuntimeDir 'backend.start'
$FrontendStartFile = Join-Path $RuntimeDir 'frontend.start'
$BackendPortFile = Join-Path $RuntimeDir 'backend.port'
$FrontendPortFile = Join-Path $RuntimeDir 'frontend.port'
$StartupPidFile = Join-Path $RuntimeDir 'startup.pid'

function Resolve-ServicePort {
    param(
        [int]$ExplicitPort,
        [string]$PortFile,
        [int]$DefaultPort
    )

    if ($ExplicitPort -gt 0) {
        return $ExplicitPort
    }

    if (Test-Path -LiteralPath $PortFile) {
        $value = (Get-Content -LiteralPath $PortFile -Raw).Trim()
        if ($value -match '^\d+$') {
            $parsed = [int]$value
            if (($parsed -ge 1) -and ($parsed -le 65535)) {
                return $parsed
            }
        }
    }

    return $DefaultPort
}

function Remove-TrackingFiles {
    param(
        [string]$PidFile,
        [string]$StartFile
    )

    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StartFile -Force -ErrorAction SilentlyContinue
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)

    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $cim) {
        return ''
    }
    return [string]$cim.CommandLine
}

function Test-ExpectedCommand {
    param(
        [ValidateSet('startup', 'backend', 'frontend')][string]$Kind,
        [string]$CommandLine
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return $false
    }

    if ($Kind -eq 'startup') {
        $hasScript = $CommandLine.IndexOf('start.ps1', [StringComparison]::OrdinalIgnoreCase) -ge 0
        $hasWorker = $CommandLine.IndexOf('-Worker', [StringComparison]::OrdinalIgnoreCase) -ge 0
        return ($hasScript -and $hasWorker)
    }

    if ($Kind -eq 'backend') {
        $hasUvicorn = $CommandLine.IndexOf('uvicorn', [StringComparison]::OrdinalIgnoreCase) -ge 0
        $hasApp = $CommandLine.IndexOf('app.main:app', [StringComparison]::OrdinalIgnoreCase) -ge 0
        return ($hasUvicorn -and $hasApp)
    }

    $hasVite = $CommandLine.IndexOf('vite', [StringComparison]::OrdinalIgnoreCase) -ge 0
    $hasProjectRoot = $CommandLine.IndexOf($ProjectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $viteScript = Join-Path $ProjectRoot 'frontend\node_modules\vite\bin\vite.js'
    $hasViteScript = $CommandLine.IndexOf($viteScript, [StringComparison]::OrdinalIgnoreCase) -ge 0
    return ($hasVite -and ($hasProjectRoot -or $hasViteScript))
}

function Stop-ProcessTree {
    param(
        [int]$ProcessId,
        [string]$Name,
        [switch]$ForceStop
    )

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "SKIP  $Name PID $ProcessId no longer exists" -ForegroundColor DarkGray
        return
    }

    Write-Host "STOP  $Name pid=$ProcessId" -ForegroundColor Yellow

    if ($ForceStop) {
        & taskkill.exe /F /T /PID $ProcessId 2>&1 | Out-Null
        Write-Host "KILL  $Name force-stopped" -ForegroundColor Red
        return
    }

    Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
        if ($null -eq (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            Write-Host "OK    $Name stopped" -ForegroundColor Green
            return
        }
    }

    Write-Host "WARN  $Name did not exit in 3 seconds; killing process tree" -ForegroundColor Yellow
    & taskkill.exe /F /T /PID $ProcessId 2>&1 | Out-Null
}

function Stop-StartupWorker {
    if (-not (Test-Path -LiteralPath $StartupPidFile)) {
        return
    }

    $value = (Get-Content -LiteralPath $StartupPidFile -Raw).Trim()
    if ($value -notmatch '^\d+$') {
        Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $processId = [int]$value
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $commandLine = Get-ProcessCommandLine -ProcessId $processId
    if (-not (Test-ExpectedCommand -Kind 'startup' -CommandLine $commandLine)) {
        Write-Host "REFUSE startup PID $processId is not recognized" -ForegroundColor Red
        Write-Host "       $commandLine" -ForegroundColor DarkYellow
        Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    Stop-ProcessTree -ProcessId $processId -Name 'startup worker' -ForceStop
    Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
}

function Stop-TrackedService {
    param(
        [ValidateSet('backend', 'frontend')][string]$Kind,
        [string]$Name,
        [string]$PidFile,
        [string]$StartFile,
        [switch]$ForceStop
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "INFO  $Name has no PID file; checking its port" -ForegroundColor DarkGray
        return
    }

    $value = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($value -notmatch '^\d+$') {
        Write-Host "WARN  $Name PID file is invalid; checking its port" -ForegroundColor Yellow
        Remove-TrackingFiles -PidFile $PidFile -StartFile $StartFile
        return
    }

    $processId = [int]$value
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "INFO  $Name PID $processId no longer exists" -ForegroundColor DarkGray
        Remove-TrackingFiles -PidFile $PidFile -StartFile $StartFile
        return
    }

    $startMatches = $true
    if (Test-Path -LiteralPath $StartFile) {
        $expectedStart = (Get-Content -LiteralPath $StartFile -Raw).Trim()
        $actualStart = $process.StartTime.ToUniversalTime().Ticks.ToString()
        $startMatches = ($expectedStart -eq $actualStart)
    }

    $commandLine = Get-ProcessCommandLine -ProcessId $processId
    $commandMatches = Test-ExpectedCommand -Kind $Kind -CommandLine $commandLine
    if ((-not $startMatches) -or (-not $commandMatches)) {
        Write-Host "WARN  $Name PID $processId identity mismatch; checking its port" -ForegroundColor Yellow
        Write-Host "      $commandLine" -ForegroundColor DarkYellow
        Remove-TrackingFiles -PidFile $PidFile -StartFile $StartFile
        return
    }

    Stop-ProcessTree -ProcessId $processId -Name $Name -ForceStop:$ForceStop
    Remove-TrackingFiles -PidFile $PidFile -StartFile $StartFile
}

function Stop-ServiceByPort {
    param(
        [ValidateSet('backend', 'frontend')][string]$Kind,
        [string]$Name,
        [int]$Port,
        [switch]$ForceStop
    )

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
        Write-Host "DOWN  $Name port $Port is not listening" -ForegroundColor DarkGray
        return
    }

    $processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($processIdValue in $processIds) {
        $processId = [int]$processIdValue
        $commandLine = Get-ProcessCommandLine -ProcessId $processId
        if (-not (Test-ExpectedCommand -Kind $Kind -CommandLine $commandLine)) {
            Write-Host "REFUSE $Name port $Port PID $processId is not recognized" -ForegroundColor Red
            Write-Host "       $commandLine" -ForegroundColor DarkYellow
            continue
        }

        Write-Host "FOUND orphan $Name port=$Port pid=$processId" -ForegroundColor Yellow
        Stop-ProcessTree -ProcessId $processId -Name $Name -ForceStop:$ForceStop
    }
}

$ResolvedBackendPort = Resolve-ServicePort -ExplicitPort $BackendPort -PortFile $BackendPortFile -DefaultPort 8000
$ResolvedFrontendPort = Resolve-ServicePort -ExplicitPort $FrontendPort -PortFile $FrontendPortFile -DefaultPort 5173

Stop-StartupWorker
Stop-TrackedService -Kind 'backend' -Name 'backend' -PidFile $BackendPidFile -StartFile $BackendStartFile -ForceStop:$Force
Stop-TrackedService -Kind 'frontend' -Name 'frontend' -PidFile $FrontendPidFile -StartFile $FrontendStartFile -ForceStop:$Force
Stop-ServiceByPort -Kind 'backend' -Name 'backend' -Port $ResolvedBackendPort -ForceStop:$Force
Stop-ServiceByPort -Kind 'frontend' -Name 'frontend' -Port $ResolvedFrontendPort -ForceStop:$Force

Remove-TrackingFiles -PidFile $BackendPidFile -StartFile $BackendStartFile
Remove-TrackingFiles -PidFile $FrontendPidFile -StartFile $FrontendStartFile

$backendListeners = @(Get-NetTCPConnection -LocalPort $ResolvedBackendPort -State Listen -ErrorAction SilentlyContinue)
$frontendListeners = @(Get-NetTCPConnection -LocalPort $ResolvedFrontendPort -State Listen -ErrorAction SilentlyContinue)

if ($backendListeners.Count -eq 0) {
    Remove-Item -LiteralPath $BackendPortFile -Force -ErrorAction SilentlyContinue
}
if ($frontendListeners.Count -eq 0) {
    Remove-Item -LiteralPath $FrontendPortFile -Force -ErrorAction SilentlyContinue
}

$hasRemainingListener = (($backendListeners.Count -gt 0) -or ($frontendListeners.Count -gt 0))
if ($hasRemainingListener) {
    Write-Host 'DONE  Known project processes were stopped, but an unknown port owner remains.' -ForegroundColor Yellow
    exit 1
}

Write-Host 'DONE  Backend and frontend are stopped; ports are free.' -ForegroundColor Green
