# IMPLEMENTATION STATUS

冻结日期：2026-07-16（v2 启动）

## 阶段与 Gate

| 阶段 | 状态 | 完成 Gate | 证据 |
|---|---|---|---|
| S0 monorepo + 质量基线 | 进行中 | backend/frontend 空项目可构建；OpenAPI → TS 类型流水线；无硬编码 | 见下方命令清单 |
| S1 领域模型 / Schema / API 契约 | 进行中 | 示例 JSON 同时通过 JSON Schema + Pydantic + 前端运行时 | contract snapshot tests |
| B1 时间/历法/四柱双引擎 | 进行中 | lunar_python + sxtwl 双引擎 0 关键分歧；Golden 通过 | pytest tests/unit/calendar |
| F1 设计系统 / 应用壳 | 进行中 | AppShell 渲染；5 个状态可见；Playwright 截图基线 | tests/e2e/shell.spec.ts |
| B2 规则/起运/大运/流运 | 待启动 | Golden 流运 100% | — |
| F2 出生信息向导 | 待启动 | 4 步向导 + 临界比较页；axe 通过 | — |
| B3 计算 API / 持久化 / 任务 | 待启动 | 幂等 + 任务状态机 + SSE | — |
| F3 计算进度与命盘核心页 | 待启动 | mock 数据可遍历 | — |
| I1 确定性计算联调 | 待启动 | 前端无兜底计算 | — |
| A1 RAG 数据治理 | **冻结**（必须 B1 全部测试通过） | raw → quarantine → approved 状态机 | — |
| A2 智能体 / 分析 / 报告块 | **冻结**（必须 I1 通过） | StructuredAnalysis 验证通过率 ≥ 99% | — |
| F4 流运交互 / 报告阅读 | 待启动 | 大运双轴 + EvidenceDrawer | — |
| I2 完整分析流水线 | 待启动 | SSE 断线重连 / 重试 / 报告生成 | — |
| R1 历史/PDF/分享/设置 | 待启动 | 打印路由 + 分享撤销 + 配置只读 | — |
| H1 评估/安全/性能/发布 | 待启动 | 评测隔离 + axe + 性能预算 | — |

## 关键证据命令

每完成一个里程碑必须运行以下命令并把输出归档：

```bash
# 后端
cd backend
ruff check .
mypy app
pytest -q --maxfail=1
pytest tests/contract -q

# 前端
cd frontend
npm run lint
npm run typecheck
npm run test
npm run e2e
```

输出落到 `docs/evidence/<phase>/`，并在 `API_CONTRACT_DIFF.md` 记录任何 schema 变更。