# Codex / Claude Code 接入指令

将本目录放入项目 `data/bazi_rag_dataset_v2_1/`，先阅读 README、DATA_CARD、GOVERNANCE、INTEGRATION 和 `config/retrieval_policy.yaml`。

1. 只导入 `data/production/combined_rag.jsonl`；不得导入 quarantine、low_trust 或 excluded。
2. 实现三个逻辑检索通道：`authoritative_evidence`、`similar_cases`、`explanation_examples`。
3. `benchmark_case_qa` 已作为生产 RAG 全量启用，但只能支持案例类比，不能支持普遍规则。
4. 2022–2025 的 MingLi-Bench 题与 BaziQA 重合，不要再重复导入；每条记录的 `source.provenance_chain` 已保留双来源。
5. 排盘、历法、十神、藏干、起运、大运、流年流月流日、刑冲合害和神煞以确定性计算引擎为准。
6. 最终规则性结论必须引用 A/B 级 chunk_id；案例引用必须显式标注为历史案例。
7. 涉及健康、死亡、投资、违法、灾劫等案例，不得生成确定性建议或恐吓性表述。
8. 接入后执行 `python scripts/validate_dataset.py`，并使用 `scripts/query_sqlite.py` 做冒烟测试。
