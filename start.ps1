<#
start.ps1 — 一键启动后端 + 前端

用法:
    .\start.ps1                  # 默认端口 (后端 8000, 前端 5173)
    .\start.ps1 -BackendPort 9000 -FrontendPort 5174

行为:
    - 创建 .runtime/ 目录存放 PID 与日志
    - 检测端口是否已被占用;占用时拒绝启动并提示用 stop.ps1
    - 首次启动会安装依赖 (pip install / npm install)
    - 从 ..\deepseek-apikey 读取 API key 注入 DEEPSEEK_API_KEY (不回显)
    - 后端 uvicorn 与前端 vite 都在后台运行,各自有日志
    - 健康检查失败时回滚并退出
#>

[CmdletBinding()]
param(
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5173,
    [switch]$SkipInstall,
    [switch]$Mock
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$RuntimeDir = Join-Path $ProjectRoot '.runtime'
$BackendPidFile = Join-Path $RuntimeDir 'backend.pid'
$FrontendPidFile = Join-Path $RuntimeDir 'frontend.pid'
$BackendStartFile = Join-Path $RuntimeDir 'backend.start'
$FrontendStartFile = Join-Path $RuntimeDir 'frontend.start'
$BackendLog = Join-Path $RuntimeDir 'backend.out.log'
$BackendErr = Join-Path $RuntimeDir 'backend.err.log'
$FrontendLog = Join-Path $RuntimeDir 'frontend.out.log'
$FrontendErr = Join-Path $RuntimeDir 'frontend.err.log'

if (-not (Test-Path $RuntimeDir)) { New-Item -ItemType Directory -Path $RuntimeDir | Out-Null }

if ($BackendPort -eq $FrontendPort) {
    Write-Host "ERROR: 前后端端口不能相同。" -ForegroundColor Red
    exit 1
}

function Test-Alive {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return $false }
    $procId = (Get-Content $PidFile -Raw).Trim()
    if ($procId -notmatch '^\d+$') { return $false }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    return $null -ne $proc
}

if (Test-Alive -PidFile $BackendPidFile) {
    Write-Host "ERROR: 后端已在运行 (pid: $((Get-Content $BackendPidFile).Trim())). 先运行 .\stop.ps1" -ForegroundColor Red
    exit 1
}
if (Test-Alive -PidFile $FrontendPidFile) {
    Write-Host "ERROR: 前端已在运行 (pid: $((Get-Content $FrontendPidFile).Trim())). 先运行 .\stop.ps1" -ForegroundColor Red
    exit 1
}

function Test-Port {
    param([int]$Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $listener
}
if (Test-Port -Port $BackendPort) {
    Write-Host "ERROR: 端口 $BackendPort 已被占用。修改 -BackendPort 或释放端口后重试。" -ForegroundColor Red
    exit 1
}
if (Test-Port -Port $FrontendPort) {
    Write-Host "ERROR: 端口 $FrontendPort 已被占用。修改 -FrontendPort 或释放端口后重试。" -ForegroundColor Red
    exit 1
}

$PythonLauncher = 'py'
try {
    $Python = (& $PythonLauncher -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Python)) { throw 'Python 3.12 unavailable' }
} catch {
    Write-Host "ERROR: 未找到 py (Python 3.12)。请安装并加入 PATH。" -ForegroundColor Red
    exit 1
}

Set-Location (Join-Path $ProjectRoot 'backend')
& $Python -c "import fastapi, uvicorn, app" 2>$null
$BackendDepsReady = $LASTEXITCODE -eq 0
if (-not $BackendDepsReady -and $SkipInstall) {
    Write-Host "ERROR: 后端依赖缺失，不能与 -SkipInstall 同时使用。" -ForegroundColor Red
    exit 1
}
if (-not $BackendDepsReady) {
    Write-Host "SETUP 安装后端依赖..." -ForegroundColor Cyan
    & $Python -m pip install -e .[dev] --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: 后端依赖安装失败" -ForegroundColor Red
        exit 1
    }
}

$KeyFile = Join-Path (Split-Path $ProjectRoot -Parent) 'deepseek-apikey'
$PreviousKey = $env:DEEPSEEK_API_KEY
$HadPreviousKey = Test-Path Env:DEEPSEEK_API_KEY
if (-not $Mock) {
    if (-not (Test-Path -LiteralPath $KeyFile)) {
        Write-Host "ERROR: 未找到 DeepSeek key 文件。使用 -Mock 可只启动设计模式。" -ForegroundColor Red
        exit 1
    }
    $env:DEEPSEEK_API_KEY = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $KeyFile)).Trim()
    if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
        Write-Host "ERROR: DeepSeek key 文件为空。" -ForegroundColor Red
        exit 1
    }
    $RagDb = Join-Path $ProjectRoot 'data\bazi_rag_dataset_v2_1\import\sqlite\bazi_rag.sqlite'
    if (-not (Test-Path -LiteralPath $RagDb)) {
        Write-Host "ERROR: 正式 RAG SQLite 数据不存在: $RagDb" -ForegroundColor Red
        exit 1
    }
}

Write-Host "START 后端 uvicorn (port $BackendPort)..." -ForegroundColor Green
try {
    $BackendProc = Start-Process -FilePath $Python -ArgumentList @(
        '-m', 'uvicorn', 'app.main:app',
        '--host', '127.0.0.1',
        '--port', $BackendPort,
        '--log-level', 'info'
    ) -WorkingDirectory (Join-Path $ProjectRoot 'backend') `
        -RedirectStandardOutput $BackendLog `
        -RedirectStandardError $BackendErr `
        -PassThru -WindowStyle Hidden
} finally {
    if ($HadPreviousKey) { $env:DEEPSEEK_API_KEY = $PreviousKey }
    else { Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue }
}

$BackendProc.Id | Set-Content $BackendPidFile -NoNewline
$BackendProc.StartTime.ToUniversalTime().Ticks | Set-Content $BackendStartFile -NoNewline

Set-Location (Join-Path $ProjectRoot 'frontend')
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: 未找到 Node.js/npm。" -ForegroundColor Red
    & (Join-Path $ProjectRoot 'stop.ps1') -Force
    exit 1
}
if (-not (Test-Path 'node_modules\vite\bin\vite.js')) {
    if ($SkipInstall) {
        Write-Host "ERROR: 前端依赖缺失，不能与 -SkipInstall 同时使用。" -ForegroundColor Red
        & (Join-Path $ProjectRoot 'stop.ps1') -Force
        exit 1
    } else {
        Write-Host "SETUP 安装前端依赖 (npm install)..." -ForegroundColor Cyan
        npm install --prefer-offline --no-audit --no-fund --no-progress 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: 前端依赖安装失败" -ForegroundColor Red
            & (Join-Path $ProjectRoot 'stop.ps1')
            exit 1
        }
    }
}

$PreviousMock = $env:VITE_USE_MOCKS
$HadPreviousMock = Test-Path Env:VITE_USE_MOCKS
$PreviousTarget = $env:VITE_API_TARGET
$HadPreviousTarget = Test-Path Env:VITE_API_TARGET
if ($Mock) { $env:VITE_USE_MOCKS = 'true' } else { Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue }
$env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"
Write-Host "START 前端 vite dev (port $FrontendPort)..." -ForegroundColor Green
try {
    $Node = (Get-Command node.exe).Source
    $ViteScript = Join-Path $ProjectRoot 'frontend\node_modules\vite\bin\vite.js'
    $FrontendProc = Start-Process -FilePath $Node -ArgumentList @($ViteScript, '--host', '127.0.0.1', '--port', "$FrontendPort") `
        -WorkingDirectory (Join-Path $ProjectRoot 'frontend') `
        -RedirectStandardOutput $FrontendLog `
        -RedirectStandardError $FrontendErr `
        -PassThru -WindowStyle Hidden
} catch {
    & (Join-Path $ProjectRoot 'stop.ps1') -Force
    throw
} finally {
    if ($HadPreviousMock) { $env:VITE_USE_MOCKS = $PreviousMock }
    else { Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue }
    if ($HadPreviousTarget) { $env:VITE_API_TARGET = $PreviousTarget }
    else { Remove-Item Env:VITE_API_TARGET -ErrorAction SilentlyContinue }
}

$FrontendProc.Id | Set-Content $FrontendPidFile -NoNewline
$FrontendProc.StartTime.ToUniversalTime().Ticks | Set-Content $FrontendStartFile -NoNewline

Write-Host "HEALTH 等待服务就绪..." -ForegroundColor Cyan
$BackendOk = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/v1/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $BackendOk = $true; break }
    } catch { }
}
if (-not $BackendOk) {
    Write-Host "ERROR: 后端 15s 内未响应 /api/v1/health。日志: $BackendLog" -ForegroundColor Red
    & (Join-Path $ProjectRoot 'stop.ps1')
    exit 1
}
$FrontendOk = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $page = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 2
        $proxy = Invoke-WebRequest -Uri "http://127.0.0.1:$FrontendPort/api/v1/health" -UseBasicParsing -TimeoutSec 2
        if ($page.StatusCode -eq 200 -and $proxy.StatusCode -eq 200) { $FrontendOk = $true; break }
    } catch { }
}
if (-not $FrontendOk) {
    Write-Host "ERROR: 前端或 API 代理 15s 内未就绪。日志: $FrontendLog / $FrontendErr" -ForegroundColor Red
    & (Join-Path $ProjectRoot 'stop.ps1') -Force
    exit 1
}
Write-Host "OK    后端 http://127.0.0.1:$BackendPort (pid $BackendProc.Id)" -ForegroundColor Green
Write-Host "OK    前端 http://127.0.0.1:$FrontendPort (pid $FrontendProc.Id) — 浏览器打开即可" -ForegroundColor Green
Write-Host ""
Write-Host "停止:  .\stop.ps1"
Write-Host "日志:  $BackendLog"
Write-Host "       $FrontendLog"
