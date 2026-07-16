<#
status.ps1 — 查看服务状态

用法:
    .\status.ps1
#>

$ProjectRoot = $PSScriptRoot
$RuntimeDir = Join-Path $ProjectRoot '.runtime'

function Show-One {
    param([string]$Name, [string]$PidFile, [int]$Port)
    if (Test-Path $PidFile) {
        $procId = (Get-Content $PidFile).Trim()
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            $uptime = (Get-Date) - $proc.StartTime
            Write-Host ("[up]    {0,-10} pid={1,-7} port={2,-5} 已运行 {3:hh\:mm\:ss}" -f $Name, $procId, $Port, $uptime) -ForegroundColor Green
            return
        }
    }
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host "ORPHAN $Name 端口 $Port 被 pid $($listener.OwningProcess) 占用,无 PID 文件" -ForegroundColor Yellow
    } else {
        Write-Host "DOWN  $Name 未运行" -ForegroundColor DarkGray
    }
}

Show-One -Name 'backend' -PidFile (Join-Path $RuntimeDir 'backend.pid') -Port 8000
Show-One -Name 'frontend' -PidFile (Join-Path $RuntimeDir 'frontend.pid') -Port 5173

try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 2
    Write-Host "HEALTH backend /api/v1/health → $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "HEALTH backend /api/v1/health 不可达" -ForegroundColor Red
}