# 八字命理智能体 v2

当前版本可在本机运行完整链路：登录 → 确定性排盘 → 正式 RAG 检索 → DeepSeek 结构化分析 → 确定性验证 → 六亲/健康/全生命周期大运报告 → 持久化问答。

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

## 登录与本地配置

首次启动会自动创建管理员：

```text
用户名：admin
密码：123456
```

本地配置文件为仓库根目录的 `config.local.env`：

```env
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=123456
DEFAULT_USER_PASSWORD=123456
BAZI_RUNTIME_DIR=runtime
ENABLE_REPORT_SHARING=false
```

管理员可进入 `/admin` 创建普通用户、重置密码，并查看用户的排盘和对话记录。新用户默认密码取 `DEFAULT_USER_PASSWORD`。密码在 SQLite 中以 PBKDF2 哈希保存。

> `INITIAL_ADMIN_PASSWORD` 只在数据库中尚无该管理员时生效。若数据库已经初始化，请在后台重置密码，或删除玩具环境的运行数据库重新初始化。

## 持久化数据与日志

默认运行目录位于仓库根目录：

```text
runtime/
├── bazi_agent.db          # 用户、命盘、报告、任务、对话、Prompt 与模型调用轨迹
└── logs/
    ├── application.log    # 应用运行日志，滚动保留
    ├── error.log          # 错误日志，滚动保留
    └── llm_calls.jsonl    # 每次模型调用的完整可审计记录
```

系统重启后，用户、命盘、报告、对话历史、实际 Prompt、RAG 命中、模型原始输出、验证结果和修复轮次均会保留。可在 `config.local.env` 中修改 `BAZI_RUNTIME_DIR`。

`llm_calls.jsonl` 和数据库中的调用轨迹不会记录 DeepSeek API Key、Cookie 或密码，但会包含出生信息、命盘上下文和用户问题，请按个人数据文件妥善保管。

## 本轮核心分析能力

- **六亲**：父母、兄弟姐妹、配偶婚恋、子女和家庭互动；同时结合十神六亲映射、宫位、透藏根气、喜忌与岁运触发。
- **健康**：五行偏性、寒暖燥湿、调候、气机、传统脏腑象义、保护因素和不同大运的变化。健康结论属于传统命理倾向，不代替医学诊断。
- **大运**：从出生至起运开始，逐柱分析全部大运的结构、事业、财运、感情六亲、健康和前后承接。
- **岁运交互确定性计算**：完整计算天干相克、原局四柱与岁运关系、岁运并临、严格伏吟、反吟候选、天克地冲，以及大运—流年—流月—流日之间的两两/三柱合冲刑害会；公历立春前仍按上一流年处理。
- **生成过程**：报告与每条问答均可查看实际 Prompt、确定性上下文、RAG 资料、可审计推理摘要、原始输出、验证和修复过程。
- **问真兼容规则**：新增童子煞、金神，修正勾绞和九丑口径；新增盖头、截脚、暗合候选、拱合/拱会、两支刑触发、四库齐全和争合候选。所有扩展项均保留 `variant` 与 `basis`，候选结构不等同合化或凶灾。

## 重置玩具环境

停止服务后删除 `runtime/bazi_agent.db` 即可清空用户、命盘、报告和对话；删除 `runtime/logs/` 可清空日志。正式使用前请先备份该目录。

## 设计与实施文档

- [本轮迭代计划](docs/ITERATION_PLAN_CORE_TOPICS_AND_TOY_PORTAL.md)
- [六亲、健康与全生命周期大运 Prompt 设计](docs/PROMPT_ARCHITECTURE_V6_CORE_TOPICS.md)
- [岁运交互确定性引擎 V3](docs/TEMPORAL_RELATION_ENGINE_V3.md)
- [岁运确定性关系修复报告](docs/TEMPORAL_RELATION_FIX_REPORT.md)
- [问真兼容神煞与关系规则 V1](docs/WENZHEN_COMPATIBILITY_RULES_V1.md)
- [12 个命造 Golden Validation](docs/WENZHEN_SAMPLE_GOLDEN_VALIDATION.md)
- [原 V5 Prompt 架构](docs/PROMPT_ARCHITECTURE_V5.md)
