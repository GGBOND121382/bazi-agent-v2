# DECISION LOG

## 2026-07-16

- **DEC-001**：默认计算口径固定为 `ziping_standard_v1`。
- **DEC-002**：领域层不依赖 Web/DB/LLM；第三方历法仅在 adapter。
- **DEC-003**：DeepSeek key 仅从 `DEEPSEEK_API_KEY` 读取，缺失时失败关闭，禁止日志/响应回显。
- **DEC-004**：LLM 只读取 `calculation_status=passed` 的事实和 approved evidence；代码验证错误不能由模型覆盖。
- **DEC-005**：正式报告要求验证状态 passed 且全部 claim approved。
- **DEC-006**：评测集只允许 `scripts/eval/` 读取，生产应用不得引用其路径。
- **DEC-007**：Windows 无可用 sxtwl 时使用带 `REF_FALLBACK` warning 的 ReferenceAdapter；部署环境应恢复独立双引擎。
- **DEC-008**：起运参考节由 adapter 提供精确 `getNextJie/getPrevJie` 时刻；逆排大运在 60 甲子上真实逆向推进。
- **DEC-009**：SSE 事件持久化并支持 `Last-Event-ID`；只输出阶段摘要，不输出 CoT/Provider 原文。
- **DEC-010**：分享默认关闭，token 仅创建时返回，服务端只存 hash，支持过期与撤销。
- **DEC-011**：用户负责正式 RAG 数据构造；本轮只实现并维护治理、检索、引用和隔离流程，不扩写 corpus。
- **DEC-012**：正式语料固定为 `data/bazi_rag_dataset_v2_1` v2.1.0；生产只读 SQLite FTS5 索引。`approved_core` 的 A/B 级材料可支持规则，`benchmark_case_qa` 与 `qa_explanations` 的 C 级材料只能用于历史类比/解释，隔离与低可信集合永不进入生产检索。
- **DEC-013**：检索上下文按 `authoritative_evidence`、`similar_cases`、`explanation_examples` 三组传给模型；确定性排盘事实覆盖任何 RAG 内容，验证器拒绝 C 级证据进入 `rule_ids`，历史案例必须显式声明非必然性。
