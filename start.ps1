<#
start.ps1 — 一键后台启动后端 + 前端

用法:
    .\start.ps1                                  # 默认后台启动，终端立即返回
    .\start.ps1 -Mock                            # Mock 模式后台启动
    .\start.ps1 -Wait                            # 前台等待并显示启动过程，便于排错
    .\start.ps1 -BackendPort 9000 -FrontendPort 5174

行为:
    - 默认创建独立后台启动进程，当前 PowerShell 立即恢复可用
    - 创建 .runtime/ 保存 PID、端口、启动状态与日志
    - 精确显示端口占用进程，不再只提示“端口被占用”
    - 首次启动可安装依赖
    - 从 ..\deepseek-apikey 读取 API key，不回显
    - 后端 uvicorn 与前端 Vite 均为后台进程
    - 使用真实总截止时间执行健康检查，失败时自动回滚
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

if (-not (Test-Path $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

function Get-TrackedProcess {
    param([string]$PidFile)

    if (-not (Test-Path $PidFile)) { return $null }
    $procId = (Get-Content $PidFile -Raw).Trim()
    if ($procId -notmatch '^\d+$') { return $null }
    return Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue
}

function Get-PortOwner {
    param([int]$Port)

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $listener) { return $null }

    $procId = [int]$listener.OwningProcess
    $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    $process = Get-Process -Id $procId -ErrorAction SilentlyContinue

    return [PSCustomObject]@{
        Pid = $procId
        Name = if ($null -ne $process) { $process.ProcessName } else { '<unknown>' }
        CommandLine = if ($null -ne $cim) { $cim.CommandLine } else { '<unavailable>' }
    }
}

function Assert-PortsAvailable {
    if ($BackendPort -eq $FrontendPort) {
        throw '前后端端口不能相同。'
    }

    foreach ($item in @(
        [PSCustomObject]@{ Name = '后端'; Port = $BackendPort },
        [PSCustomObject]@{ Name = '前端'; Port = $FrontendPort }
    )) {
        $owner = Get-PortOwner -Port $item.Port
        if ($null -ne $owner) {
            throw ("{0}端口 {1} 已被占用：PID={2}，进程={3}`n命令行：{4}`n先运行 .\stop.ps1，或修改端口后重试。" -f `
                $item.Name, $item.Port, $owner.Pid, $owner.Name, $owner.CommandLine)
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
    do {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)

    Write-Host "TIMEOUT $Description 在 ${TimeoutSeconds}s 内未就绪：$Uri" -ForegroundColor Red
    return $false
}

function Start-DetachedWorker {
    $startupProcess = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $startupProcess) {
        throw "已有启动任务正在运行，PID=$($startupProcess.Id)。运行 .\status.ps1 查看状态。"
    }
    Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue

    if ($null -ne (Get-TrackedProcess -PidFile $BackendPidFile)) {
        throw "后端已在运行。先运行 .\stop.ps1。"
    }
    if ($null -ne (Get-TrackedProcess -PidFile $FrontendPidFile)) {
        throw "前端已在运行。先运行 .\stop.ps1。"
    }
    Assert-PortsAvailable

    Remove-Item $StartupOutLog,$StartupErrLog -Force -ErrorAction SilentlyContinue

    $powerShellExe = (Get-Process -Id $PID).Path
    if ([string]::IsNullOrWhiteSpace($powerShellExe)) {
        $candidate = Join-Path $PSHOME 'powershell.exe'
        if (-not (Test-Path $candidate)) { $candidate = Join-Path $PSHOME 'pwsh.exe' }
        $powerShellExe = $candidate
    }

    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $PSCommandPath),
        '-Worker',
        '-BackendPort', "$BackendPort",
        '-FrontendPort', "$FrontendPort"
    )
    if ($SkipInstall) { $arguments += '-SkipInstall' }
    if ($Mock) { $arguments += '-Mock' }

    $process = Start-Process -FilePath $powerShellExe `
        -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $StartupOutLog `
        -RedirectStandardError $StartupErrLog `
        -WindowStyle Hidden `
        -PassThru

    $process.Id | Set-Content $StartupPidFile -NoNewline
    Start-Sleep -Milliseconds 250

    if ($process.HasExited) {
        $details = ''
        if (Test-Path $StartupErrLog) {
            $details = (Get-Content $StartupErrLog -Tail 30 -ErrorAction SilentlyContinue) -join "`n"
        }
        throw "后台启动任务立即退出。`n$details"
    }

    Write-Host "START 已提交后台启动任务，PID=$($process.Id)。当前终端可以继续使用。" -ForegroundColor Green
    Write-Host "STATUS .\status.ps1" -ForegroundColor Cyan
    Write-Host "LOG    Get-Content '$StartupOutLog' -Wait" -ForegroundColor Cyan
    Write-Host "ERROR  Get-Content '$StartupErrLog' -Wait" -ForegroundColor Cyan
}

function Invoke-StartWorker {
    Set-Location $ProjectRoot

    if ($null -ne (Get-TrackedProcess -PidFile $BackendPidFile)) {
        throw '后端已在运行。先运行 .\stop.ps1。'
    }
    if ($null -ne (Get-TrackedProcess -PidFile $FrontendPidFile)) {
        throw '前端已在运行。先运行 .\stop.ps1。'
    }
    Assert-PortsAvailable

    $BackendPort | Set-Content $BackendPortFile -NoNewline
    $FrontendPort | Set-Content $FrontendPortFile -NoNewline

    $pythonLauncher = 'py'
    try {
        $python = (& $pythonLauncher -3.12 -c "import sys; print(sys.executable)" 2>$null |
            Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) {
            throw 'Python 3.12 unavailable'
        }
    } catch {
        throw '未找到 py (Python 3.12)。请安装 Python 3.12 并加入 PATH。'
    }

    $backendDir = Join-Path $ProjectRoot 'backend'
    Set-Location $backendDir
    & $python -c "import fastapi, uvicorn, app" 2>$null
    $backendDepsReady = $LASTEXITCODE -eq 0
    if (-not $backendDepsReady -and $SkipInstall) {
        throw '后端依赖缺失，不能与 -SkipInstall 同时使用。'
    }
    if (-not $backendDepsReady) {
        Write-Host 'SETUP 安装后端依赖...' -ForegroundColor Cyan
        & $python -m pip install -e '.[dev]'
        if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败。' }
    }

    $keyFile = Join-Path (Split-Path $ProjectRoot -Parent) 'deepseek-apikey'
    $previousKey = $env:DEEPSEEK_API_KEY
    $hadPreviousKey = Test-Path Env:DEEPSEEK_API_KEY
    if (-not $Mock) {
        if (-not (Test-Path -LiteralPath $keyFile)) {
            throw '未找到 DeepSeek key 文件。使用 -Mock 可只启动设计模式。'
        }
        $env:DEEPSEEK_API_KEY = [IO.File]::ReadAllText(
            (Resolve-Path -LiteralPath $keyFile)
        ).Trim()
        if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
            throw 'DeepSeek key 文件为空。'
        }
        $ragDb = Join-Path $ProjectRoot 'data\bazi_rag_dataset_v2_1\import\sqlite\bazi_rag.sqlite'
        if (-not (Test-Path -LiteralPath $ragDb)) {
            throw "正式 RAG SQLite 数据不存在：$ragDb"
        }
    }

    Write-Host "START 后端 uvicorn (port $BackendPort)..." -ForegroundColor Green
    try {
        $backendProc = Start-Process -FilePath $python -ArgumentList @(
            '-m', 'uvicorn', 'app.main:app',
            '--app-dir', ('"{0}"' -f $backendDir),
            '--host', '127.0.0.1',
            '--port', "$BackendPort",
            '--log-level', 'info'
        ) -WorkingDirectory $backendDir `
            -RedirectStandardOutput $BackendLog `
            -RedirectStandardError $BackendErr `
            -PassThru -WindowStyle Hidden
    } finally {
        if ($hadPreviousKey) { $env:DEEPSEEK_API_KEY = $previousKey }
        else { Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue }
    }

    $backendProc.Id | Set-Content $BackendPidFile -NoNewline
    $backendProc.StartTime.ToUniversalTime().Ticks | Set-Content $BackendStartFile -NoNewline

    $frontendDir = Join-Path $ProjectRoot 'frontend'
    Set-Location $frontendDir
    if (-not (Get-Command node.exe -ErrorAction SilentlyContinue) -or
        -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw '未找到 Node.js/npm。'
    }
    if (-not (Test-Path 'node_modules\vite\bin\vite.js')) {
        if ($SkipInstall) {
            throw '前端依赖缺失，不能与 -SkipInstall 同时使用。'
        }
        Write-Host 'SETUP 安装前端依赖 (npm install)...' -ForegroundColor Cyan
        & npm.cmd install --prefer-offline --no-audit --no-fund --no-progress
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。' }
    }

    $previousMock = $env:VITE_USE_MOCKS
    $hadPreviousMock = Test-Path Env:VITE_USE_MOCKS
    $previousTarget = $env:VITE_API_TARGET
    $hadPreviousTarget = Test-Path Env:VITE_API_TARGET
    if ($Mock) { $env:VITE_USE_MOCKS = 'true' }
    else { Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue }
    $env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"

    Write-Host "START 前端 vite dev (port $FrontendPort)..." -ForegroundColor Green
    try {
        $node = (Get-Command node.exe).Source
        $viteScript = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
        $frontendProc = Start-Process -FilePath $node -ArgumentList @(
            ('"{0}"' -f $viteScript),
            '--host', '127.0.0.1',
            '--port', "$FrontendPort"
        ) -WorkingDirectory $frontendDir `
            -RedirectStandardOutput $FrontendLog `
            -RedirectStandardError $FrontendErr `
            -PassThru -WindowStyle Hidden
    } finally {
        if ($hadPreviousMock) { $env:VITE_USE_MOCKS = $previousMock }
        else { Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue }
        if ($hadPreviousTarget) { $env:VITE_API_TARGET = $previousTarget }
        else { Remove-Item Env:VITE_API_TARGET -ErrorAction SilentlyContinue }
    }

    $frontendProc.Id | Set-Content $FrontendPidFile -NoNewline
    $frontendProc.StartTime.ToUniversalTime().Ticks | Set-Content $FrontendStartFile -NoNewline

    Write-Host 'HEALTH 等待后端服务就绪...' -ForegroundColor Cyan
    $backendOk = Wait-HttpReady `
        -Uri "http://127.0.0.1:$BackendPort/api/v1/health" `
        -TimeoutSeconds 20 `
        -Description '后端'
    if (-not $backendOk) {
        throw "后端未就绪。日志：$BackendLog / $BackendErr"
    }

    Write-Host 'HEALTH 等待前端与 API 代理就绪...' -ForegroundColor Cyan
    $frontendPageOk = Wait-HttpReady `
        -Uri "http://127.0.0.1:$FrontendPort/" `
        -TimeoutSeconds 20 `
        -Description '前端页面'
    $frontendProxyOk = Wait-HttpReady `
        -Uri "http://127.0.0.1:$FrontendPort/api/v1/health" `
        -TimeoutSeconds 10 `
        -Description '前端 API 代理'
    if (-not $frontendPageOk -or -not $frontendProxyOk) {
        throw "前端或 API 代理未就绪。日志：$FrontendLog / $FrontendErr"
    }

    Write-Host "OK 后端 http://127.0.0.1:$BackendPort (pid $($backendProc.Id))" -ForegroundColor Green
    Write-Host "OK 前端 http://127.0.0.1:$FrontendPort (pid $($frontendProc.Id))" -ForegroundColor Green
    Write-Host '停止：.\stop.ps1' -ForegroundColor Cyan
}

if (-not $Worker -and -not $Wait) {
    try {
        Start-DetachedWorker
        return
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
        & (Join-Path $ProjectRoot 'stop.ps1') `
            -Force `
            -BackendPort $BackendPort `
            -FrontendPort $FrontendPort
    } catch { }
} finally {
    if ($Worker) {
        Remove-Item $StartupPidFile -Force -ErrorAction SilentlyContinue
    }
    Set-Location $ProjectRoot
}

exit $exitCode
