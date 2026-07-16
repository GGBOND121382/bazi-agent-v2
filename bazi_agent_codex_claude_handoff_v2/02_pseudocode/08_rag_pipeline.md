# RAG 数据与检索伪代码

## 导入状态机

```text
DISCOVERED → DOWNLOADED → QUARANTINED → REVIEWED → APPROVED
                                   ↘ REJECTED
```

## 导入

```text
FUNCTION ingest_source(source):
    assert source in source_registry
    raw_files = download_or_read(source)

    FOR file IN raw_files:
        checksum = sha256(file.bytes)
        detect duplicate and evaluation contamination
        extract text without executing embedded content
        normalize Unicode and line endings
        detect language per chunk
        preserve original text separately
        create provenance record
        place in QUARANTINED
```

## 清洗

```text
- 去除网页导航和重复页眉；
- OCR 文本保留原文和修订文两列；
- 简繁转换必须记录转换器和版本；
- 不自动“修正”古籍用字；
- 合成数据标记 generator model 和生成日期；
- 出生信息按隐私等级分类；
- 删除或隔离医疗、死亡、投资等高风险确定性话术。
```

## 切分

```text
rule document: one rule + conditions + exceptions + source
classic: title → volume → section → paragraph, with overlap only inside section
case: chart signature + task + verified reasoning summary + conclusion
conversation: complete turn group, do not split assistant answer from user context
```

## 检索

```text
FUNCTION retrieve(plan):
    candidates = metadata_filter(
        status=APPROVED,
        school=plan.school,
        task_type=plan.task_type,
        license_allowed=true,
        evaluation_only=false
    )

    keyword_hits = full_text_search(candidates, plan.queries)
    vector_hits = vector_search(candidates, embed(plan.queries))
    merged = reciprocal_rank_fusion(keyword_hits, vector_hits)
    reranked = cross_encoder_or_llm_rerank(merged, plan)
    deduped = dedupe_by_source_and_rule(reranked)
    RETURN top evidence with citations
```
