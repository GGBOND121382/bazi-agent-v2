# CLAUDE.md

本文件为 Claude Code / Codex 等智能体在打开本仓库时提供上下文锚点。

## 工作流

- 严格按 `00_project/milestone_plan.md` 顺序推进，每个里程碑完成后必须跑对应测试（pytest + vitest + E2E）。
- 任何计算口径、Schema、错误码变更必须同步 `docs/DECISION_LOG.md` 和 `docs/API_CONTRACT_DIFF.md`。
- 基础排盘（B1+B2+B3+I1）全部测试通过前不得实现 RAG / LLM 相关代码（`02_pseudocode/08_rag_pipeline.md` 等）。
- 评测集（`contracts/evaluation/`）物理隔离，仅 H1 阶段使用。

## 关键约定

- **Python**：`py` 命令 = Python 3.12（Windows）。**不要用裸 `python`**（那是 2.7）。
- **API key**：`D:\claudeWorkspace\算命\deepseek-apikey`，从 `DEEPSEEK_API_KEY` 环境变量读取；**永不在终端回显明文 key**。
- **正式 RAG**：`data/bazi_rag_dataset_v2_1/`，只读 SQLite FTS5；A/B 可支持规则，C 级只作解释/历史类比，隔离和低可信集合禁止进入生产检索。
- **路径**：cwd 在多次 Bash 调用间会重置；尽量用绝对路径 `D:\claudeWorkspace\算命\handoff_v2\...`。
- **不要往 `bazi_agent_codex_claude_handoff_v2/` 写新代码**——那是原始启动包，只读。
- **sxtwl 在 Windows 不可用**（无 MSVC）；`ReferenceAdapter` 是 fallback（DEC-008）。
- **Pillar 校验** `(stem_index − branch_index) % 2 == 0`，不是 `% 12 == 0`。
- **lunar_python 是 camelCase**：`Solar.fromYmdHms` / `solar.getLunar()` / `lunar.getYearInGanZhi()`。

## 记忆

`.claude/memory/` 下保存项目记忆（`MEMORY.md` 索引），涵盖项目状态、RAG 数据、信任边界、部署待办、命令速查、踩坑记录、用户偏好等。新会话开始时按 `MEMORY.md` 顺序激活。

## 必读文档优先级

1. `docs/IMPLEMENTATION_STATUS.md` — 当前 Gate
2. `docs/DECISION_LOG.md` — 已冻结的设计决策
3. `docs/API_CONTRACT_DIFF.md` — 契约变更记录
4. `contracts/schemas/` — JSON Schema（13 个）
5. `contracts/calculation_profile_v1.yaml` — 计算 Profile
6. `HANDOFF_TO_CODEX_CLAUDE.md` — v2 启动原则

## 测试

```bash
# 后端（pytest）
cd backend && py -m pytest -q

# 前端（vitest + typecheck）
cd frontend && npm test && npm run typecheck

# E2E 烟测
cd backend && py -m uvicorn app.main:app --port 8770 &
curl -sS -X POST http://127.0.0.1:8770/api/v1/charts -H "Content-Type: application/json" \
  -H "Idempotency-Key: smoke" -d '{"schema_version":"birth-request-v1",...}'
```
