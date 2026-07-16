# 八字命理智能体 v2

当前版本可在本机运行完整链路：确定性排盘 → 正式 RAG 检索 → DeepSeek 结构化分析 → 确定性验证 → 报告。

## 最快启动（一键脚本，推荐）

仓库根目录已提供 `start.ps1` / `stop.ps1` / `status.ps1`（Windows PowerShell 5.1+）以及 `start.sh` / `stop.sh`（Git Bash / WSL / Linux），统一管理 PID、端口、日志和依赖安装。

```powershell
cd D:\claudeWorkspace\算命\handoff_v2
.\start.ps1                  # 后端 8000 + 前端 5173，自动注入 DEEPSEEK_API_KEY
# 浏览器打开 http://127.0.0.1:5173
.\status.ps1                 # 查看服务状态
.\stop.ps1                   # 优雅停止（5s 后 taskkill /T 兜底）
.\stop.ps1 -Force            # 立即强杀整棵进程树
```

```bash
# Bash 版等价用法
./start.sh                   # 后端 8000 + 前端 5173
./start.sh MOCK=1 SKIP_INSTALL=1 BACKEND_PORT=9000  # 自定义参数
./stop.sh
```

**行为约定**：
- 自动读取 `../deepseek-apikey` 注入 `DEEPSEEK_API_KEY`，**不在终端回显明文 key**。
- PID 文件在 `.runtime/backend.pid` / `.runtime/frontend.pid`，日志在 `.runtime/{name}.out.log` / `.err.log`（`.gitignore` 已排除）。
- 健康检查 `/api/v1/health` 在 15s 内必须 200；否则自动停止并回滚退出非零码。
- 端口被占、已有进程未停、Python/npm 缺失都会提前报错并给出修复指引。

完整安装、API 调用、验证与排错说明见 [docs/QUICKSTART.md](docs/QUICKSTART.md)。当前实现状态见 [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)。

## 最快启动（手动双窗口）

若需要手动控制（例如分别调试后端/前端、附加断点或环境变量），仍可用以下方式：

后端窗口：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2
$env:DEEPSEEK_API_KEY = [IO.File]::ReadAllText((Resolve-Path ..\deepseek-apikey)).Trim()
Set-Location .\backend
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端窗口：

```powershell
Set-Location D:\claudeWorkspace\算命\handoff_v2\frontend
Remove-Item Env:VITE_USE_MOCKS -ErrorAction SilentlyContinue
npm run dev
```

浏览器打开：<http://127.0.0.1:5173/>。点击“新建命盘”，排盘后点击“生成结构化分析”即可调用正式 RAG 和 DeepSeek。

> 当前存储为进程内单用户模式；重启后端会清空本次运行中的命盘、任务和报告。
