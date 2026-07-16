# 算命智能体 — 开发说明

本仓库实现八字命理产品（确定性排盘 + RAG + 大模型分析 + Web 前端 + 报告导出）。
**所有计算口径、Schema、错误码、契约以 `contracts/` 为准**，不得擅自修改。

## 目录结构

```
.
├── backend/                    # Python 3.12 + FastAPI 后端
│   ├── app/
│   │   ├── domain/             # 纯领域模型（无外部依赖）
│   │   ├── adapters/           # 历法、地理、LLM 等外部适配器
│   │   ├── api/                # FastAPI 路由与 DTO
│   │   ├── services/           # 应用服务
│   │   ├── jobs/               # 异步任务内核 / SSE
│   │   └── utils/
│   └── tests/                  # 单元 / 契约 / Golden / e2e
├── frontend/                   # Vue 3 + TypeScript + Vite
│   ├── src/
│   │   ├── pages/              # 12 类页面（与 09_frontend 路线图对应）
│   │   ├── components/
│   │   ├── viewmodels/         # DTO → view-model mapper
│   │   ├── api/                # 自动生成的 TS 类型 + 请求客户端
│   │   ├── stores/             # Pinia（仅会话状态）
│   │   └── design/             # design tokens
│   └── tests/                  # 单元 / E2E / 视觉回归
├── contracts/                  # 冻结的契约
│   ├── schemas/                # JSON Schema（13 个）
│   ├── examples/               # mock JSON / JSONL
│   ├── core_tables/            # 天干、地支、藏干、十神、神煞种子
│   ├── calculation_profile_v1.yaml
│   ├── rag_seed/               # 隔离区之前的 RAG 种子
│   ├── evaluation/             # 评测集（仅 H1 阶段使用，物理隔离）
│   └── openapi.yaml            # OpenAPI 3.1 outline
└── docs/
    ├── IMPLEMENTATION_STATUS.md
    ├── DECISION_LOG.md
    └── API_CONTRACT_DIFF.md
```

## 信任边界（不可违反）

1. 领域层零外部依赖 — `backend/app/domain/` 不 import Web/DB/LLM SDK/前端。
2. 第三方历法只存在 adapter 层 — `backend/app/adapters/calendar/`。
3. 前端零兜底计算 — Vue 组件不计算干支/十神/关系。
4. LLM 仅消费已通过 `validation_status=passed` 的 `StructuredAnalysis` 与 `RagChunk`。
5. 评测集（`04_data/evaluation/`）不得进入 RAG/训练/few-shot；A1 之前不得被加载。
6. 出生信息、地点、API key 不进入普通日志/分析埋点/前端错误上报。

## 计算口径（冻结）

- profile_id = `ziping_standard_v1`
- 年界 = 立春精确时刻；月界 = 节气精确时刻；节气精度 = 秒
- 时区 = IANA zoneinfo；拒绝 naive datetime
- 模糊/不存在时间策略：`ambiguous_time_policy = require_fold_or_candidate`，`nonexistent_time_policy = reject_and_explain`
- 时基默认 `civil_time`，可选 `local_mean_solar_time` / `true_solar_time`
- 换日默认 `midnight_00`，可选 `late_zi_23` / `split_zi_hour`
- 大运方向 = 阴阳年干+性别；顺排参考 `next_jie`，逆排参考 `previous_jie`
- 起运折算 = 三天折一年；每运十年；首柱偏移 = 月柱 +1
- 神煞规则集 = `core_v1`，默认参考优先级：日干 > 日支 > 年干 > 年支
- 学校 = `ziping_standard`，禁止混派；不确定性语言必填；禁止确定性生死/疾病/收益断言

详见 `contracts/calculation_profile_v1.yaml`。

## 错误码（冻结）

所有 API 错误以 `contracts/schemas/api_error.schema.json` 输出：

```json
{
  "schema_version": "api-error-v1",
  "request_id": "req_...",
  "error_code": "CHART_CROSS_ENGINE_CONFLICT",
  "message_key": "chart.cross_engine_conflict",
  "retryable": false,
  "field_errors": [...],
  "safe_details": {...}
}
```

错误码清单（节选，完整见 `backend/app/api/error_codes.py`）：

| error_code | HTTP | 说明 |
|---|---|---|
| `INVALID_INPUT` | 422 | 入参不通过 schema |
| `TIMEZONE_UNKNOWN` | 422 | IANA 时区无法解析 |
| `AMBIGUOUS_TIME_REQUIRES_FOLD` | 422 | 模糊时间需 `fold=0/1` |
| `NONEXISTENT_TIME` | 422 | DST 跳跃中的不存在时间 |
| `CHART_CROSS_ENGINE_CONFLICT` | 409 | 双引擎分歧，需走 candidate-resolution |
| `CHART_NEEDS_USER_RESOLUTION` | 409 | 临界时间需用户确认 |
| `PROFILE_UNKNOWN` | 422 | `calculation_profile_id` 不在白名单 |
| `JOB_NOT_FOUND` | 404 | 任务不存在 |
| `JOB_NOT_CANCELLABLE` | 409 | 任务已终止 |
| `ANALYSIS_VALIDATION_FAILED` | 409 | 验证器拒绝（事实/引用错误） |
| `EVALUATION_SET_FORBIDDEN` | 403 | 试图把评测集注入 RAG/训练 |
| `RATE_LIMITED` | 429 | 限流 |
| `INTERNAL_ERROR` | 500 | 未分类内部错误（绝不返回栈） |

## 开发

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest -q

# Frontend
cd frontend
npm install
npm run dev
npm run test
npm run e2e
```

## 里程碑

详见根目录的 `HANDOFF_TO_CODEX_CLAUDE.md` 和 `00_project/milestone_plan.md`。
当前进度见 `docs/IMPLEMENTATION_STATUS.md`。