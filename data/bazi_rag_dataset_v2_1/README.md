# 八字智能体 RAG 数据集 v2.1

这是面向八字命理智能体的中文分层 RAG 数据包。版本 2.1 删除全部韩文命例，并将 BaziQA 与 MingLi-Bench 的正式 Contest8 数据作为生产案例库接入。

## 数据规模

- **生产 RAG：7,637 条**
  - A 级核心规则与古籍块：234 条
  - C 级中文解释问答：7,203 条
  - C 级正式命例问答：200 条
- 隔离问答：1,798 条
- 低可信合成推理语料：427 条，默认禁用
- 韩文语料：0 条

## 基准数据去重

BaziQA Contest8 2021–2025 共 200 道题。MingLi-Bench 的 160 道题来自 2022–2025 Contest8，与 BaziQA 对应部分重合。因此生产库增加 **200 个唯一案例向量**，其中 160 条同时记录 BaziQA 和 MingLi-Bench 两套来源，不重复建索引。

`benchmark_case_qa` 保存出生资料、问题、答案字母和正确答案全文。它属于历史案例资料，可用于相似案例检索，但不能自动上升为普遍规则，也不能据此断言当前用户必然发生同类事件。

## 目录

```text
bazi_rag_dataset_v2_1/
├── data/production/
│   ├── approved_core.jsonl
│   ├── qa_explanations.jsonl
│   ├── benchmark_case_qa.jsonl
│   └── combined_rag.jsonl
├── data/quarantine/qa_flagged.jsonl
├── data/low_trust/synthetic_reasoning_corpus.jsonl
├── data/source_registry/
├── data/excluded/
├── import/qdrant/payloads.jsonl
├── import/chroma/documents.jsonl
├── import/sqlite/bazi_rag.sqlite
├── config/retrieval_policy.yaml
├── reports/
├── schemas/
└── scripts/
```

## 三路检索

1. `authoritative_evidence`：只检索 A/B 级规则，负责支撑规则性结论。
2. `similar_cases`：检索 `benchmark_case_qa`，用于历史案例类比。
3. `explanation_examples`：检索普通 C 级问答，用于通俗表达。

确定性排盘结果始终优先于任何 RAG 文本。

## Celebrity50 说明

BaziQA 仓库的 Celebrity50 是辅助人物传记问答，不属于正式 200 道 Contest8 基准核心；当前仓库 README 与辅助文件实际问题数量存在漂移。本版没有将其冒充为已审定案例，状态记录见 `data/source_registry/celebrity50_auxiliary_status.json`。
