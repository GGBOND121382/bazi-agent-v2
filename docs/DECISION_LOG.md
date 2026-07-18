# DECISION LOG

## 2026-07-18

- **DEC-019**：`analysis-output-v1` 的六亲与大运专题采用显式字段契约：六亲使用 `relationship/evaluation/fact_refs`，大运使用 `order/period/gan_zhi/analysis/fact_refs`；校验与确定性兜底同时兼容旧版 `relation/conclusion/fact_ids` 和 `stage/ganzhi` 历史数据。专题内引用仍必须来自模型可见的确定性 `fact_id`。局部 JSON Patch 的 `replace.value` 必须绑定目标路径的真实子 Schema，不再允许任意 JSON。
- **DEC-020**：命盘对话继续使用 DeepSeek SSE 流式传输并启用 thinking，以保留复杂岁运分析质量。Prompt 明确区分 `reasoning_content` 与最终 `content`，要求思考后在 `content` 输出无 Markdown 围栏的单一 JSON 对象。若 DeepSeek 偶发将最终 JSON 留在 reasoning 尾部，适配器只提取末尾完整对象并执行真实 JSON Schema 校验，不向用户返回前面的思维过程；空内容、非法 JSON 或 Schema 不合格自动重试一次。最终 provider 失败通过 `MODEL_PROVIDER_ERROR`（HTTP 502、可重试）返回。

## 2026-07-17

- **DEC-014**：确定性校验只保护排盘事实、引用 ID 和极端高风险绝对断言；旺衰、格局、喜忌、用神、事业、财运、感情等属于模型结合 RAG 的解释层判断，不再因其具有流派性而禁止输出。
- **DEC-015**：`FACTUAL_TOKEN_MISMATCH` 不再作为删除整条解释的硬失败；未被当前引用文本直接覆盖的干支字符记录为内部 warning，报告正文不展示审查诊断。
- **DEC-016**：正式报告不自动追加通用免责声明、“未进行主观判断”或“已排除若干条解释”等模板文字；`limitations` 只保留本次确实缺失的数据或口径冲突。
- **DEC-017**：新增命盘上下文对话。年、月、日运势问题必须先由工具计算目标日期干支和大运/流年/流月上下文，再由模型结合 RAG 回答，模型不得重新排盘。
- **DEC-018**：移动端页面采用黑、白、金主视觉；排盘表与高级确定性字段优先在首屏可读，桌面端保持响应式扩展。

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
