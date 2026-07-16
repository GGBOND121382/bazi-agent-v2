# 大模型分析与验证伪代码

## 分析器输入

```text
- user_focus
- calculation_profile summary
- immutable chart_facts
- immutable computed_relations
- retrieved_evidence
- required output JSON Schema
```

## 分析器输出

```text
FOR each claim:
    claim_id
    topic
    statement
    fact_ids
    rule_ids
    evidence_ids
    counterevidence
    confidence
    school
    temporal_scope
```

## 验证器

```text
FUNCTION verify(chart, evidence, analysis):
    errors = []

    FOR claim IN analysis.claims:
        IF any fact_id not in chart.fact_index:
            errors += unknown fact
        IF any rule_id not in rule_registry:
            errors += unknown rule
        IF any evidence_id not in evidence.bundle:
            errors += hallucinated citation
        IF claim mentions stem/branch/ten-god not supported by referenced facts:
            errors += factual mismatch
        IF claim.school != configured school and mixed school forbidden:
            errors += school violation
        IF claim has deterministic medical/legal/financial/death assertion:
            errors += policy violation
        IF confidence high but counterevidence exists and is ignored:
            warnings += overconfidence

    cross_claim_consistency_check()
    quoted_text_exact_match_check()

    RETURN passed only when no errors
```

验证器优先使用代码和 Schema。可额外调用独立模型做语言层检查，但不能用模型投票覆盖确定性错误。
