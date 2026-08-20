<#
status.ps1 - Show background startup, backend, and frontend status.

Usage:
    .\status.ps1
    .\status.ps1 -BackendPort 9000 -FrontendPort 5174

Compatible with Windows PowerShell 5.1.
#>

[CmdletBinding()]
param(
    [ValidateRange(0, 65535)][int]$BackendPort = 0,
    [ValidateRange(0, 65535)][int]$FrontendPort = 0
)

$ProjectRoot = $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot '.runtime'
$BackendPidFile = Join-Path $RuntimeDir 'backend.pid'
$FrontendPidFile = Join-Path $RuntimeDir 'frontend.pid'
$BackendPortFile = Join-Path $RuntimeDir 'backend.port'
$FrontendPortFile = Join-Path $RuntimeDir 'frontend.port'
$StartupPidFile = Join-Path $RuntimeDir 'startup.pid'
$StartupStateFile = Join-Path $RuntimeDir 'startup.state'
$StartupMessageFile = Join-Path $RuntimeDir 'startup.message'
$StartupOutLog = Join-Path $RuntimeDir 'startup.out.log'
$StartupErrLog = Join-Path $RuntimeDir 'startup.err.log'
$BackendErrLog = Join-Path $RuntimeDir 'backend.err.log'
$FrontendErrLog = Join-Path $RuntimeDir 'frontend.err.log'

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

function Get-PortOwners {
    param([int]$Port)

    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) {
        return @()
    }

    return @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Read-OptionalText {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return ''
    }

    return (Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue).Trim()
}

function Show-LogTail {
    param(
        [string]$Label,
        [string]$Path,
        [int]$Tail = 12
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $lines = @(Get-Content -LiteralPath $Path -Tail $Tail -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) {
        return
    }

    Write-Host "$Label ($Path):" -ForegroundColor Yellow
    foreach ($line in $lines) {
        Write-Host "  $line" -ForegroundColor DarkYellow
    }
}

function Show-StartupState {
    $process = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $process) {
        $uptime = (Get-Date) - $process.StartTime
        Write-Host ("STARTING startup pid={0} uptime={1:hh\:mm\:ss}" -f $process.Id, $uptime) -ForegroundColor Cyan
        Write-Host "         log: Get-Content '$StartupOutLog' -Wait" -ForegroundColor DarkCyan
        return 'starting'
    }

    if (Test-Path -LiteralPath $StartupPidFile) {
        Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
    }

    $state = Read-OptionalText -Path $StartupStateFile
    $message = Read-OptionalText -Path $StartupMessageFile

    if ($state -eq 'failed') {
        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = 'Detached startup failed without a recorded message.'
        }
        Write-Host "FAILED   startup: $message" -ForegroundColor Red
        Write-Host "         output: Get-Content '$StartupOutLog' -Tail 200" -ForegroundColor DarkYellow
        Write-Host "         error:  Get-Content '$StartupErrLog' -Tail 200" -ForegroundColor DarkYellow
        return 'failed'
    }

    if ($state -eq 'starting') {
        Write-Host 'STALE    startup state is starting, but the worker process is no longer running' -ForegroundColor Yellow
        if (-not [string]::IsNullOrWhiteSpace($message)) {
            Write-Host "         $message" -ForegroundColor DarkYellow
        }
        return 'stale'
    }

    return $state
}

function Show-ServiceState {
    param(
        [string]$Name,
        [string]$PidFile,
        [int]$Port
    )

    $process = Get-TrackedProcess -PidFile $PidFile
    if ($null -ne $process) {
        $uptime = (Get-Date) - $process.StartTime
        Write-Host ("UP       {0,-10} pid={1,-7} port={2,-5} uptime={3:hh\:mm\:ss}" -f $Name, $process.Id, $Port, $uptime) -ForegroundColor Green
        return
    }

    $owners = @(Get-PortOwners -Port $Port)
    if ($owners.Count -gt 0) {
        Write-Host "ORPHAN   $Name port $Port owned by PID $($owners -join ','); no valid PID tracking" -ForegroundColor Yellow
        foreach ($processIdValue in $owners) {
            $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$processIdValue" -ErrorAction SilentlyContinue
            if ($null -ne $cim) {
                Write-Host "         $($cim.CommandLine)" -ForegroundColor DarkYellow
            }
        }
        return
    }

    Write-Host "DOWN     $Name is not running (port $Port)" -ForegroundColor DarkGray
}

$ResolvedBackendPort = Resolve-ServicePort -ExplicitPort $BackendPort -PortFile $BackendPortFile -DefaultPort 8000
$ResolvedFrontendPort = Resolve-ServicePort -ExplicitPort $FrontendPort -PortFile $FrontendPortFile -DefaultPort 5173

$StartupState = Show-StartupState
Show-ServiceState -Name 'backend' -PidFile $BackendPidFile -Port $ResolvedBackendPort
Show-ServiceState -Name 'frontend' -PidFile $FrontendPidFile -Port $ResolvedFrontendPort

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$ResolvedBackendPort/api/v1/health" -UseBasicParsing -TimeoutSec 2
    Write-Host "HEALTH   backend /api/v1/health -> $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host 'HEALTH   backend /api/v1/health is unreachable' -ForegroundColor Red
}

$startupProcess = Get-TrackedProcess -PidFile $StartupPidFile
$backendProcess = Get-TrackedProcess -PidFile $BackendPidFile
$frontendProcess = Get-TrackedProcess -PidFile $FrontendPidFile
$allTrackedProcessesDown = (($null -eq $startupProcess) -and ($null -eq $backendProcess) -and ($null -eq $frontendProcess))

if ($allTrackedProcessesDown) {
    if ($StartupState -eq 'failed') {
        Show-LogTail -Label 'STARTUP OUTPUT' -Path $StartupOutLog
        Show-LogTail -Label 'STARTUP ERROR' -Path $StartupErrLog
        Show-LogTail -Label 'BACKEND ERROR' -Path $BackendErrLog
        Show-LogTail -Label 'FRONTEND ERROR' -Path $FrontendErrLog
    } elseif (Test-Path -LiteralPath $StartupErrLog) {
        Show-LogTail -Label 'LAST STARTUP ERROR' -Path $StartupErrLog -Tail 8
    }
}
