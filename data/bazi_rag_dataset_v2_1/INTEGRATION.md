# 智能体集成说明

## 生产入口

读取 `data/production/combined_rag.jsonl`，向量化字段优先使用 `retrieval_text_zh_cn`，为空时使用 `retrieval_text`。

## 三路检索

- 规则通道：`collection=approved_core`，要求 `can_support_claim=true`。
- 案例通道：`collection=benchmark_case_qa`，要求 `can_support_case_analogy=true`。
- 解释通道：`collection=qa_explanations`，要求 `can_supply_explanation=true`。

推荐上下文结构：

```json
{
  "authoritative_evidence": [],
  "similar_cases": [],
  "explanation_examples": [],
  "conflicting_evidence": []
}
```

Prompt 必须声明：相似案例只用于类比，不得据此推断当前用户必然发生相同事件；规则性结论必须由 A/B 级证据或确定性引擎支撑。

SQLite FTS5 数据库位于 `import/sqlite/bazi_rag.sqlite`，使用 trigram tokenizer，支持中文子串检索。
