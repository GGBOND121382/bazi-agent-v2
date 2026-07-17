<#
start.ps1 — 一键后台启动后端和前端。

用法:
    .\start.ps1
    .\start.ps1 -Mock
    .\start.ps1 -Wait
    .\start.ps1 -BackendPort 9000 -FrontendPort 5174

默认在隐藏的后台 PowerShell 中完成依赖检查、服务启动和健康检查，
当前终端会立即恢复。使用 -Wait 可在当前终端观察启动过程。
兼容 Windows PowerShell 5.1。
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
        throw '前后端端口不能相同。'
    }

    $checks = @(
        [PSCustomObject]@{ Name = '后端'; Port = $BackendPort },
        [PSCustomObject]@{ Name = '前端'; Port = $FrontendPort }
    )

    foreach ($item in $checks) {
        $owner = Get-PortOwner -Port $item.Port
        if ($null -ne $owner) {
            $message = "{0}端口 {1} 已被占用：PID={2}，进程={3}`n命令行：{4}`n先运行 .\stop.ps1，或修改端口后重试。" -f $item.Name, $item.Port, $owner.Pid, $owner.Name, $owner.CommandLine
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

    Write-Host "TIMEOUT $Description 在 $TimeoutSeconds 秒内未就绪：$Uri" -ForegroundColor Red
    return $false
}

function Find-PowerShellExecutable {
    $currentProcess = Get-Process -Id $PID -ErrorAction SilentlyContinue
    if (($null -ne $currentProcess) -and (-not [string]::IsNullOrWhiteSpace($currentProcess.Path))) {
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

    throw '无法定位 PowerShell 可执行文件。'
}

function Start-DetachedWorker {
    $startupProcess = Get-TrackedProcess -PidFile $StartupPidFile
    if ($null -ne $startupProcess) {
        throw "已有启动任务正在运行，PID=$($startupProcess.Id)。运行 .\status.ps1 查看状态。"
    }
    Remove-Item -LiteralPath $StartupPidFile -Force -ErrorAction SilentlyContinue

    $backendProcess = Get-TrackedProcess -PidFile $BackendPidFile
    $frontendProcess = Get-TrackedProcess -PidFile $FrontendPidFile
    if ($null -ne $backendProcess) {
        throw '后端已在运行。先运行 .\stop.ps1。'
    }
    if ($null -ne $frontendProcess) {
        throw '前端已在运行。先运行 .\stop.ps1。'
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
        throw "后台启动任务立即退出。`n$details"
    }

    Write-Host "START 已提交后台启动任务，PID=$($startup.Id)。当前终端可以继续使用。" -ForegroundColor Green
    Write-Host 'STATUS .\status.ps1' -ForegroundColor Cyan
    Write-Host "LOG    Get-Content '$StartupOutLog' -Wait" -ForegroundColor Cyan
    Write-Host "ERROR  Get-Content '$StartupErrLog' -Wait" -ForegroundColor Cyan
}

function Resolve-Python312 {
    $pythonOutput = & py.exe -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw '未找到 py (Python 3.12)。请安装 Python 3.12 并加入 PATH。'
    }

    $python = (@($pythonOutput) | Select-Object -Last 1).Trim()
    if ([string]::IsNullOrWhiteSpace($python)) {
        throw '无法解析 Python 3.12 可执行文件路径。'
    }
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Python 3.12 可执行文件不存在：$python"
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
        throw '后端依赖缺失，不能与 -SkipInstall 同时使用。'
    }
    if (-not $dependenciesReady) {
        Write-Host 'SETUP 安装后端依赖...' -ForegroundColor Cyan
        & $Python -m pip install -e '.[dev]'
        if ($LASTEXITCODE -ne 0) {
            throw '后端依赖安装失败。'
        }
    }

    $keyFile = Join-Path (Split-Path $ProjectRoot -Parent) 'deepseek-apikey'
    $previousKey = $env:DEEPSEEK_API_KEY
    $hadPreviousKey = Test-Path Env:DEEPSEEK_API_KEY

    if (-not $Mock) {
        if (-not (Test-Path -LiteralPath $keyFile)) {
            throw '未找到 DeepSeek key 文件。使用 -Mock 可只启动设计模式。'
        }
        $resolvedKeyFile = Resolve-Path -LiteralPath $keyFile
        $env:DEEPSEEK_API_KEY = [IO.File]::ReadAllText($resolvedKeyFile).Trim()
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
        throw '未找到 Node.js/npm。'
    }

    $viteScript = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
    if (-not (Test-Path -LiteralPath $viteScript)) {
        if ($SkipInstall) {
            throw '前端依赖缺失，不能与 -SkipInstall 同时使用。'
        }
        Write-Host 'SETUP 安装前端依赖 (npm install)...' -ForegroundColor Cyan
        & npm.cmd install --prefer-offline --no-audit --no-fund --no-progress
        if ($LASTEXITCODE -ne 0) {
            throw '前端依赖安装失败。'
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

    Write-Host "START 前端 vite dev (port $FrontendPort)..." -ForegroundColor Green
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
        throw '后端已在运行。先运行 .\stop.ps1。'
    }
    if ($null -ne $frontendProcess) {
        throw '前端已在运行。先运行 .\stop.ps1。'
    }

    Assert-PortsAvailable
    $BackendPort | Set-Content -LiteralPath $BackendPortFile -NoNewline
    $FrontendPort | Set-Content -LiteralPath $FrontendPortFile -NoNewline

    $python = Resolve-Python312
    $backend = Start-Backend -Python $python
    $frontend = Start-Frontend

    Write-Host 'HEALTH 等待后端服务就绪...' -ForegroundColor Cyan
    $backendReady = Wait-HttpReady -Uri "http://127.0.0.1:$BackendPort/api/v1/health" -TimeoutSeconds 20 -Description '后端'
    if (-not $backendReady) {
        throw "后端未就绪。日志：$BackendLog / $BackendErr"
    }

    Write-Host 'HEALTH 等待前端和 API 代理就绪...' -ForegroundColor Cyan
    $frontendReady = Wait-HttpReady -Uri "http://127.0.0.1:$FrontendPort/" -TimeoutSeconds 20 -Description '前端页面'
    $proxyReady = Wait-HttpReady -Uri "http://127.0.0.1:$FrontendPort/api/v1/health" -TimeoutSeconds 10 -Description '前端 API 代理'
    if ((-not $frontendReady) -or (-not $proxyReady)) {
        throw "前端或 API 代理未就绪。日志：$FrontendLog / $FrontendErr"
    }

    Write-Host "OK    后端 http://127.0.0.1:$BackendPort (pid $($backend.Id))" -ForegroundColor Green
    Write-Host "OK    前端 http://127.0.0.1:$FrontendPort (pid $($frontend.Id))" -ForegroundColor Green
    Write-Host '停止：.\stop.ps1' -ForegroundColor Cyan
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
