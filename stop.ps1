<#
stop.ps1 — 一键停止后端 + 前端

用法:
    .\stop.ps1                  # 优雅停止 (5s 超时后强杀)
    .\stop.ps1 -Force           # 立即强制终止
#>

[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'SilentlyContinue'
$ProjectRoot = $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot '.runtime'

function Remove-Tracking {
    param([string]$PidFile, [string]$StartFile)
    Remove-Item $PidFile,$StartFile -Force -ErrorAction SilentlyContinue
}

function Stop-One {
    param(
        [string]$Name,
        [string]$PidFile,
        [string]$StartFile,
        [string]$CommandMarker,
        [switch]$ForceStop
    )
    if (-not (Test-Path $PidFile)) {
        Write-Host "SKIP $Name 未运行 (无 PID 文件)" -ForegroundColor DarkGray
        return
    }
    $procId = (Get-Content $PidFile -Raw).Trim()
    if ($procId -notmatch '^\d+$' -or -not (Test-Path $StartFile)) {
        Write-Host "REFUSE $Name 跟踪文件无效；只清理跟踪文件，不终止任何进程。" -ForegroundColor Red
        Remove-Tracking $PidFile $StartFile
        return
    }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Write-Host "SKIP $Name PID $procId 不存在,清理 PID 文件" -ForegroundColor DarkGray
        Remove-Tracking $PidFile $StartFile
        return
    }
    $expectedStart = (Get-Content $StartFile -Raw).Trim()
    $actualStart = $proc.StartTime.ToUniversalTime().Ticks.ToString()
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($expectedStart -ne $actualStart -or $null -eq $cim -or $cim.CommandLine -notlike "*$CommandMarker*") {
        Write-Host "REFUSE $Name PID $procId 身份不匹配；可能是 PID 已复用。不会终止。" -ForegroundColor Red
        Remove-Tracking $PidFile $StartFile
        return
    }
    Write-Host "STOP $Name pid=$procId ..." -ForegroundColor Yellow
    if ($ForceStop) {
        # /T = tree (kill children too, e.g. npm.cmd → node → vite)
        taskkill /F /T /PID $procId 2>&1 | Out-Null
        Write-Host "KILLED $Name (force)" -ForegroundColor Red
    } else {
        # 先优雅,5s 后用 taskkill /T 兜底
        try { Stop-Process -Id $procId -ErrorAction SilentlyContinue } catch { }
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Milliseconds 500
            if ($null -eq (Get-Process -Id $procId -ErrorAction SilentlyContinue)) {
                Write-Host "STOPPED $Name 优雅退出" -ForegroundColor Green
                Remove-Tracking $PidFile $StartFile
                return
            }
        }
        Write-Host "WARN: $Name 5s 内未响应,杀进程树" -ForegroundColor Yellow
        taskkill /F /T /PID $procId 2>&1 | Out-Null
    }
    Remove-Tracking $PidFile $StartFile
}

Stop-One -Name 'backend' `
    -PidFile (Join-Path $RuntimeDir 'backend.pid') `
    -StartFile (Join-Path $RuntimeDir 'backend.start') `
    -CommandMarker 'app.main:app' -ForceStop:$Force
Stop-One -Name 'frontend' `
    -PidFile (Join-Path $RuntimeDir 'frontend.pid') `
    -StartFile (Join-Path $RuntimeDir 'frontend.start') `
    -CommandMarker 'vite' -ForceStop:$Force

Write-Host "DONE 停止完成" -ForegroundColor Green
