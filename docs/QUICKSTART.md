# 本地使用与启动指南

更新日期：2026-07-16。以下命令面向 Windows PowerShell。

## 0. 一键脚本（推荐）

```powershell
cd D:\claudeWorkspace\算命\handoff_v2
.\start.ps1                  # 后端 8000 + 前端 5173，自动注入 DEEPSEEK_API_KEY
.\status.ps1                 # 查看状态 + /api/v1/health
.\stop.ps1                   # 优雅停止（5s 后 taskkill /T 兜底）
.\stop.ps1 -Force            # 立即强杀整棵进程树
```

Bash 等价：

```bash
./start.sh    MOCK=1 SKIP_INSTALL=1 BACKEND_PORT=9000   # 自定义
./stop.sh     FORCE=1
```

PID 与日志在 `.runtime/` 目录（已 .gitignore 排除）。手动双窗口方式见 README.md 末尾。

## 1. 当前能做什么

本机已真实验证以下完整链路：

1. 输入出生时间、时区和地点并执行确定性排盘。
2. 从 `bazi_rag_dataset_v2_1` 的只读 SQLite FTS5 索引检索证据。
3. 将证据按 A/B 权威规则、C 级历史案例、C 级解释示例分组。
4. 调用 `deepseek-chat` 生成结构化分析。
5. 由代码检查事实、规则、引用、风险措辞和案例限定语。
6. 只有验证通过才生成正式报告。

合成命盘的真实在线验收结果为：`validation=passed`、`report_created=true`，使用 8 条权威证据和 4 条解释示例。

## 2. 前置条件

- Windows PowerShell。
- Python 3.12；本机使用 `py` 命令。
- Node.js 与 npm。
- 正式 RAG 数据目录已存在：`data/bazi_rag_dataset_v2_1/`。
- DeepSeek key 文件位于项目上一级：`D:\claudeWorkspace\算命\deepseek-apikey`。

当前机器依赖已经安装。全新环境可执行：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2\backend
py -m pip install -e ".[dev]"

Set-Location ..\frontend
npm install
```

Windows 如果无法编译 `sxtwl`，项目会使用带警告标记的 `ReferenceAdapter` 作为复核引擎；当前测试已覆盖该降级路径。

## 3. 启动后端

打开第一个 PowerShell 窗口：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2

# 只把 key 注入当前 PowerShell 进程；不会写入项目文件。
$env:DEEPSEEK_API_KEY = [IO.File]::ReadAllText((Resolve-Path ..\deepseek-apikey)).Trim()

Set-Location .\backend
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端地址：

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- Swagger API 文档：<http://127.0.0.1:8000/api/docs>

停止后端时按 `Ctrl+C`。如需清除当前窗口中的环境变量：

```powershell
Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
```

不要使用会把 key 明文打印出来的命令，也不要把 key 写入 `.env`、源码、日志或聊天内容。

## 4. 启动前端

保持后端运行，再打开第二个 PowerShell 窗口：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2\frontend

# 确保使用真实后端，而不是设计用 mock。
Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue

npm run dev
```

浏览器打开 <http://127.0.0.1:5173/>，操作顺序：

1. 点击“新建命盘”。
2. 填写出生资料并提交。
3. 在命盘页面查看确定性结果。
4. 点击“生成结构化分析”。此步骤会产生 DeepSeek API 调用和相应费用。
5. 等待任务完成并进入报告页面。

## 5. 不启动前端，直接调用 API

先按第 3 节启动后端，再在另一个 PowerShell 窗口执行以下合成示例。

### 5.1 创建命盘

```powershell
$baseUrl = 'http://127.0.0.1:8000/api/v1'

$birth = @{
    schema_version = 'birth-request-v1'
    gender = 'unspecified'
    birth_datetime_local = '1990-06-15T12:00:00'
    timezone = 'Asia/Shanghai'
    birthplace = @{
        country = 'CN'
        city = 'Shanghai'
        longitude = 121.47
        latitude = 31.23
    }
    calculation_profile_id = 'ziping_standard_v1'
}

$chart = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/charts" `
    -Headers @{ 'Idempotency-Key' = "chart-$([guid]::NewGuid())" } `
    -ContentType 'application/json' `
    -Body ($birth | ConvertTo-Json -Depth 6)

$chart | ConvertTo-Json -Depth 6
```

### 5.2 启动 RAG + DeepSeek 分析

```powershell
$analysisRequest = @{
    user_focus = @('命局结构', '事业')
    school = 'engineering_policy'
}

$job = Invoke-RestMethod `
    -Method Post `
    -Uri "$baseUrl/charts/$($chart.chart_id)/analyses" `
    -Headers @{ 'Idempotency-Key' = "analysis-$([guid]::NewGuid())" } `
    -ContentType 'application/json' `
    -Body ($analysisRequest | ConvertTo-Json -Depth 4)

$job | ConvertTo-Json
```

### 5.3 等待任务完成并读取报告

```powershell
do {
    Start-Sleep -Seconds 2
    $state = Invoke-RestMethod -Uri "$baseUrl/jobs/$($job.job_id)"
    Write-Host "stage=$($state.stage) progress=$($state.progress)"
} while ($state.stage -notin @('completed', 'failed', 'cancelled'))

if ($state.stage -eq 'completed') {
    $report = Invoke-RestMethod -Uri "$baseUrl/reports/$($state.result_ref)"
    $report | ConvertTo-Json -Depth 10
} else {
    $state | ConvertTo-Json
}
```

需要观察 SSE 事件时可使用：

```powershell
curl.exe -N "$baseUrl/jobs/$($job.job_id)/events"
```

## 6. 验证 RAG 和代码

从项目根目录检查正式数据：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2
py .\data\bazi_rag_dataset_v2_1\scripts\validate_dataset.py
```

预期生产记录为 7,637 条：权威核心 234、解释示例 7,203、历史案例 200。

运行后端质量门禁：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2\backend
py -m mypy app
py -m ruff check app tests
py -m pytest -q
```

运行前端质量门禁：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2\frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## 7. 常见问题

### 分析任务显示 `failed`

确认后端启动前已经设置 `DEEPSEEK_API_KEY`，并确认网络可访问 DeepSeek API。报告采用失败关闭策略：模型输出没有通过事实和引用验证时，不会生成正式报告。

### 端口被占用

后端可改用 8001：

```powershell
py -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

然后在启动前端的窗口中指定代理目标：

```powershell
$env:VITE_API_TARGET = 'http://127.0.0.1:8001'
npm run dev
```

### 找不到 RAG 数据

默认目录是 `data/bazi_rag_dataset_v2_1`。如需放到其他位置，在启动后端前设置：

```powershell
$env:BAZI_RAG_DATASET_DIR = 'D:\your-path\bazi_rag_dataset_v2_1'
```

### 重启后历史记录消失

当前本地玩具版使用仓库根目录 `runtime/bazi_agent.db` 持久化用户、命盘、任务、报告和对话，重启后不会清空；Prompt 与模型调用轨迹同时写入数据库和 `runtime/logs/llm_calls.jsonl`。若未来需要多实例部署，再替换为 PostgreSQL、独立任务队列和对象存储。

### 安全与用途边界

- 传统命理解释仅作文化研究与辅助阅读，不构成医疗、投资或法律建议。
- C 级解释和历史案例不能作为通用规则或必然预测。
- 后端不会输出模型内部思维链；只有通过确定性验证的 claim 才能进入报告。
