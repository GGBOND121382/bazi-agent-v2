<#
status.ps1 — 查看后台启动任务和服务状态

用法:
    .\status.ps1
    .\status.ps1 -BackendPort 9000 -FrontendPort 5174
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

function Resolve-Port {
    param(
        [int]$ExplicitPort,
        [string]$PortFile,
        [int]$DefaultPort
    )

    if ($ExplicitPort -gt 0) { return $ExplicitPort }
    if (Test-Path $PortFile) {
        $value = (Get-Content $PortFile -Raw).Trim()
        if ($value -match '^\d+$') {
            $parsed = [int]$value
            if ($parsed -ge 1 -and $parsed -le 65535) { return $parsed }
        }
    }
    return $DefaultPort
}

$ResolvedBackendPort = Resolve-Port `
    -ExplicitPort $BackendPort `
    -PortFile $BackendPortFile `
    -DefaultPort 8000
$ResolvedFrontendPort = Resolve-Port `
    -ExplicitPort $FrontendPort `
    -PortFile $FrontendPortFile `
    -DefaultPort 5173

function Get-TrackedProcess {
    param([string]$PidFile)

    if (-not (Test-Path $PidFile)) { return $null }
    $procId = (Get-Content $PidFile -Raw).Trim()
    if ($procId -notmatch '^\d+$') { return $null }
    return Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue
}

function Show-StartupState {
    $process = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $process) {
        $uptime = (Get-Date) - $process.StartTime
        Write-Host ("STARTING 启动任务 pid={0} 已运行 {1:hh\:mm\:ss}" -f $process.Id, $uptime) -ForegroundColor Cyan
        Write-Host "         日志：Get-Content '$StartupOutLog' -Wait" -ForegroundColor DarkCyan
        return
    }

    if (Test-Path $StartupPidFile) {
        Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue
    }
}

function Show-One {
    param(
        [string]$Name,
        [string]$PidFile,
        [int]$Port
    )

    $process = Get-TrackedProcess -PidFile $PidFile
    if ($null -ne $process) {
        $uptime = (Get-Date) - $process.StartTime
        Write-Host ("UP      {0,-10} pid={1,-7} port={2,-5} 已运行 {3:hh\:mm\:ss}" -f `
            $Name, $process.Id, $Port, $uptime) -ForegroundColor Green
        return
    }

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($null -ne $listeners) {
        $processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        Write-Host "ORPHAN  $Name 端口 $Port 被 PID $($processIds -join ',') 占用，无有效 PID 跟踪" -ForegroundColor Yellow
        return
    }

    Write-Host "DOWN    $Name 未运行 (port $Port)" -ForegroundColor DarkGray
}

Show-StartupState
Show-One -Name 'backend' -PidFile $BackendPidFile -Port $ResolvedBackendPort
Show-One -Name 'frontend' -PidFile $FrontendPidFile -Port $ResolvedFrontendPort

try {
    $response = Invoke-WebRequest `
        -Uri "http://127.0.0.1:$ResolvedBackendPort/api/v1/health" `
        -UseBasicParsing `
        -TimeoutSec 2
    Write-Host "HEALTH  backend /api/v1/health -> $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host 'HEALTH  backend /api/v1/health 不可达' -ForegroundColor Red
}

if ((Get-TrackedProcess -PidFile $StartupPidFile) -eq $null -and
    (Get-TrackedProcess -PidFile $BackendPidFile) -eq $null -and
    (Get-TrackedProcess -PidFile $FrontendPidFile) -eq $null) {
    if (Test-Path $StartupErrLog) {
        $lastError = Get-Content $StartupErrLog -Tail 8 -ErrorAction SilentlyContinue
        if ($null -ne $lastError -and $lastError.Count -gt 0) {
            Write-Host 'LAST ERROR:' -ForegroundColor Yellow
            $lastError | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
        }
    }
}
