<#
status.ps1 — 查看后台启动任务、后端和前端状态。

用法:
    .\status.ps1
    .\status.ps1 -BackendPort 9000 -FrontendPort 5174

兼容 Windows PowerShell 5.1。
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
$StartupOutLog = Join-Path $RuntimeDir 'startup.out.log'
$StartupErrLog = Join-Path $RuntimeDir 'startup.err.log'

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

function Show-StartupState {
    $process = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $process) {
        $uptime = (Get-Date) - $process.StartTime
        Write-Host ("STARTING 启动任务 pid={0} 已运行 {1:hh\:mm\:ss}" -f $process.Id, $uptime) -ForegroundColor Cyan
        Write-Host "         日志：Get-Content '$StartupOutLog' -Wait" -ForegroundColor DarkCyan
        return
    }

    if (Test-Path -LiteralPath $StartupPidFile) {
        Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue
    }
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
        Write-Host ("UP       {0,-10} pid={1,-7} port={2,-5} 已运行 {3:hh\:mm\:ss}" -f $Name, $process.Id, $Port, $uptime) -ForegroundColor Green
        return
    }

    $owners = @(Get-PortOwners -Port $Port)
    if ($owners.Count -gt 0) {
        Write-Host "ORPHAN   $Name 端口 $Port 被 PID $($owners -join ',') 占用，无有效 PID 跟踪" -ForegroundColor Yellow
        foreach ($processIdValue in $owners) {
            $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$processIdValue" -ErrorAction SilentlyContinue
            if ($null -ne $cim) {
                Write-Host "         $($cim.CommandLine)" -ForegroundColor DarkYellow
            }
        }
        return
    }

    Write-Host "DOWN     $Name 未运行 (port $Port)" -ForegroundColor DarkGray
}

$ResolvedBackendPort = Resolve-ServicePort -ExplicitPort $BackendPort -PortFile $BackendPortFile -DefaultPort 8000
$ResolvedFrontendPort = Resolve-ServicePort -ExplicitPort $FrontendPort -PortFile $FrontendPortFile -DefaultPort 5173

Show-StartupState
Show-ServiceState -Name 'backend' -PidFile $BackendPidFile -Port $ResolvedBackendPort
Show-ServiceState -Name 'frontend' -PidFile $FrontendPidFile -Port $ResolvedFrontendPort

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$ResolvedBackendPort/api/v1/health" -UseBasicParsing -TimeoutSec 2
    Write-Host "HEALTH   backend /api/v1/health -> $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host 'HEALTH   backend /api/v1/health 不可达' -ForegroundColor Red
}

$startupProcess = Get-TrackedProcess -PidFile $StartupPidFile
$backendProcess = Get-TrackedProcess -PidFile $BackendPidFile
$frontendProcess = Get-TrackedProcess -PidFile $FrontendPidFile
$allTrackedProcessesDown = (($null -eq $startupProcess) -and ($null -eq $backendProcess) -and ($null -eq $frontendProcess))

if ($allTrackedProcessesDown -and (Test-Path -LiteralPath $StartupErrLog)) {
    $lastError = @(Get-Content -LiteralPath $StartupErrLog -Tail 8 -ErrorAction SilentlyContinue)
    if ($lastError.Count -gt 0) {
        Write-Host 'LAST ERROR:' -ForegroundColor Yellow
        foreach ($line in $lastError) {
            Write-Host "  $line" -ForegroundColor DarkYellow
        }
    }
}
