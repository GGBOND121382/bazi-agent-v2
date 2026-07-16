# DECISION LOG

## 2026-07-16 — v2 启动冻结

### DEC-001：计算 Profile = `ziping_standard_v1`
- 来源：`contracts/calculation_profile_v1.yaml`
- 决策：以 `ziping_standard_v1` 为唯一默认 profile
- 影响：所有 chart 必须携带 `calculation_profile_id`；前端 profile 切换为只读摘要
- 变更流程：任何修改必须先改 yaml + 更新 `schema_version`，后端通过 `PROFILE_UNKNOWN` 拒绝旧 ID

### DEC-002：JSON Schema 版本化
- 全部 13 个 schema 的 `$id` 与 `schema_version` 字段冻结
- 后端 Pydantic 模型与前端 TS 类型均从 schema 自动生成
- 任何 schema 修改必须走 PR + contract snapshot 回归

### DEC-003：API 错误体 = `api-error-v1`
- 拒绝暴露 Python traceback / SQL / 栈帧
- 所有错误含 `request_id`、`error_code`、`message_key`、`retryable`
- `safe_details` 仅放非敏感上下文（不出现生日、地点、姓名）

### DEC-004：任务状态机（`01_architecture/async_job_state_machine.md`）
- 合法转移：
  - `queued → calculating → {needs_user_resolution → calculating?}`
  - `calculating → retrieving → interpreting → verifying → report_building → completed`
  - 任意阶段 → `failed` / `cancelled`
  - `verifying → revision_pending → interpreting`（修订回环）
- 非法转移由后端拒绝并记录 `JOB_STATE_INVALID`

### DEC-005：LLM/RAG 隔离门
- 基础排盘（B1+B2+B3+I1）单元 + 契约 + Golden 全部通过之前
- 不实现 `08_rag_pipeline.md`、`09_llm_analysis_and_validation.md`、`10_report_generation.md` 中的任何代码
- 不加载 `04_data/evaluation/` 中任何文件
- 触发门检查：`scripts/gates/pre_rag_gate.py`（B1 unit + contract + golden 全绿）

### DEC-006：API key 注入
- DeepSeek API key 仅通过环境变量 `DEEPSEEK_API_KEY` 读取
- 文件 `deepseek-apikey` 仅作本地占位，禁止进 git（`.gitignore` 已加入）
- LLM adapter 启动时若 `DEEPSEEK_API_KEY` 缺失则显式 fail-closed（不在 mock 模式下静默）

### DEC-007：评测集物理隔离
- `contracts/evaluation/` 与 `04_data/evaluation/` 永久仅可由 `scripts/eval/` 读取
- RAG 索引构建脚本读取前必须先执行 `assert not is_evaluation_path()`
- 任何 import 评测集到 `domain/`、`adapters/`、`services/` 都由 lint 规则拒绝

## 待办

- DEC-008：Vue 与组件库版本在 `npm install` 后写入 lockfile，决策时记录
- DEC-009：playwright browser 在 CI 中下载策略