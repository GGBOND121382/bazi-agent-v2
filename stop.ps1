<#
stop.ps1 — 一键停止后端 + 前端

用法:
    .\stop.ps1                                  # 停止默认或已记录端口
    .\stop.ps1 -Force                           # 立即强制终止进程树
    .\stop.ps1 -BackendPort 9000 -FrontendPort 5174

即使 PID 文件丢失，也会根据监听端口和命令行识别本项目进程并停止。
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

function Remove-Tracking {
    param([string]$PidFile, [string]$StartFile)
    Remove-Item $PidFile,$StartFile -Force -ErrorAction SilentlyContinue
}

function Stop-ProcessTree {
    param(
        [int]$ProcessId,
        [string]$Name,
        [switch]$ForceStop
    )

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "SKIP $Name PID $ProcessId 已不存在" -ForegroundColor DarkGray
        return
    }

    Write-Host "STOP $Name pid=$ProcessId ..." -ForegroundColor Yellow
    if ($ForceStop) {
        taskkill /F /T /PID $ProcessId 2>&1 | Out-Null
        Write-Host "KILLED $Name (force)" -ForegroundColor Red
        return
    }

    Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(3)
    do {
        Start-Sleep -Milliseconds 250
        if ($null -eq (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            Write-Host "STOPPED $Name" -ForegroundColor Green
            return
        }
    } while ((Get-Date) -lt $deadline)

    Write-Host "WARN $Name 未在 3s 内退出，终止进程树" -ForegroundColor Yellow
    taskkill /F /T /PID $ProcessId 2>&1 | Out-Null
}

function Stop-StartupWorker {
    if (-not (Test-Path $StartupPidFile)) { return }

    $procId = (Get-Content $StartupPidFile -Raw).Trim()
    if ($procId -notmatch '^\d+$') {
        Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $process = Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    $commandLine = if ($null -ne $cim) { [string]$cim.CommandLine } else { '' }
    $isWorker = $commandLine.IndexOf('start.ps1', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine.IndexOf('-Worker', [StringComparison]::OrdinalIgnoreCase) -ge 0

    if (-not $isWorker) {
        Write-Host "REFUSE startup PID $procId 身份不匹配，不终止" -ForegroundColor Red
        Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    Stop-ProcessTree -ProcessId ([int]$procId) -Name 'startup worker' -ForceStop:$true
    Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue
}

function Stop-TrackedProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string]$StartFile,
        [string]$CommandMarker,
        [switch]$ForceStop
    )

    if (-not (Test-Path $PidFile)) {
        Write-Host "DISCOVER $Name 无 PID 文件，随后按端口检查" -ForegroundColor DarkGray
        return
    }

    $procId = (Get-Content $PidFile -Raw).Trim()
    if ($procId -notmatch '^\d+$' -or -not (Test-Path $StartFile)) {
        Write-Host "WARN $Name 跟踪文件无效，清理后按端口检查" -ForegroundColor Yellow
        Remove-Tracking $PidFile $StartFile
        return
    }

    $process = Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Write-Host "SKIP $Name PID $procId 不存在，清理跟踪文件" -ForegroundColor DarkGray
        Remove-Tracking $PidFile $StartFile
        return
    }

    $expectedStart = (Get-Content $StartFile -Raw).Trim()
    $actualStart = $process.StartTime.ToUniversalTime().Ticks.ToString()
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    $commandLine = if ($null -ne $cim) { [string]$cim.CommandLine } else { '' }
    $markerMatches = $commandLine.IndexOf($CommandMarker, [StringComparison]::OrdinalIgnoreCase) -ge 0

    if ($expectedStart -ne $actualStart -or -not $markerMatches) {
        Write-Host "WARN $Name PID $procId 身份不匹配，清理跟踪文件后按端口检查" -ForegroundColor Yellow
        Remove-Tracking $PidFile $StartFile
        return
    }

    Stop-ProcessTree -ProcessId ([int]$procId) -Name $Name -ForceStop:$ForceStop
    Remove-Tracking $PidFile $StartFile
}

function Test-DiscoveredCommand {
    param(
        [string]$Name,
        [string]$CommandLine
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }

    if ($Name -eq 'backend') {
        return $CommandLine.IndexOf('app.main:app', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $CommandLine.IndexOf('uvicorn', [StringComparison]::OrdinalIgnoreCase) -ge 0
    }

    $viteScript = Join-Path $ProjectRoot 'frontend\node_modules\vite\bin\vite.js'
    $hasVite = $CommandLine.IndexOf('vite', [StringComparison]::OrdinalIgnoreCase) -ge 0
    $hasProjectPath = $CommandLine.IndexOf($ProjectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $CommandLine.IndexOf($viteScript, [StringComparison]::OrdinalIgnoreCase) -ge 0
    return $hasVite -and $hasProjectPath
}

function Stop-DiscoveredByPort {
    param(
        [string]$Name,
        [int]$Port,
        [switch]$ForceStop
    )

    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($null -eq $listeners) {
        Write-Host "DOWN $Name 端口 $Port 未监听" -ForegroundColor DarkGray
        return
    }

    $processIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($procId in $processIds) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        $commandLine = if ($null -ne $cim) { [string]$cim.CommandLine } else { '' }

        if (-not (Test-DiscoveredCommand -Name $Name -CommandLine $commandLine)) {
            Write-Host "REFUSE $Name 端口 $Port 的 PID $procId 无法确认为本项目进程" -ForegroundColor Red
            Write-Host "命令行：$commandLine" -ForegroundColor DarkYellow
            continue
        }

        Write-Host "FOUND $Name 孤儿进程：port=$Port pid=$procId" -ForegroundColor Yellow
        Stop-ProcessTree -ProcessId ([int]$procId) -Name $Name -ForceStop:$ForceStop
    }
}

Stop-StartupWorker

Stop-TrackedProcess -Name 'backend' `
    -PidFile $BackendPidFile `
    -StartFile $BackendStartFile `
    -CommandMarker 'app.main:app' `
    -ForceStop:$Force
Stop-TrackedProcess -Name 'frontend' `
    -PidFile $FrontendPidFile `
    -StartFile $FrontendStartFile `
    -CommandMarker 'vite' `
    -ForceStop:$Force

Stop-DiscoveredByPort -Name 'backend' -Port $ResolvedBackendPort -ForceStop:$Force
Stop-DiscoveredByPort -Name 'frontend' -Port $ResolvedFrontendPort -ForceStop:$Force

Remove-Tracking $BackendPidFile $BackendStartFile
Remove-Tracking $FrontendPidFile $FrontendStartFile

$backendStillListening = Get-NetTCPConnection `
    -LocalPort $ResolvedBackendPort `
    -State Listen `
    -ErrorAction SilentlyContinue
$frontendStillListening = Get-NetTCPConnection `
    -LocalPort $ResolvedFrontendPort `
    -State Listen `
    -ErrorAction SilentlyContinue

if ($null -eq $backendStillListening) {
    Remove-Item $BackendPortFile -Force -ErrorAction SilentlyContinue
}
if ($null -eq $frontendStillListening) {
    Remove-Item $FrontendPortFile -Force -ErrorAction SilentlyContinue
}

if ($null -ne $backendStillListening -or $null -ne $frontendStillListening) {
    Write-Host 'DONE 已停止可确认的本项目进程，但仍有无法确认的端口占用，详见上方 REFUSE。' -ForegroundColor Yellow
    exit 1
}

Write-Host 'DONE 后端和前端均已停止，端口已释放' -ForegroundColor Green
