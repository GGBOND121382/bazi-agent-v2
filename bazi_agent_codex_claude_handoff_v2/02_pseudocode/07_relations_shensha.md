# 合冲刑害与神煞伪代码

## 关系引擎

```text
FUNCTION compare_pillars(left, right, enabled_rules):
    facts = []

    IF unordered_pair(left.stem, right.stem) in stem_combinations:
        emit "stem_combination_candidate"

    IF unordered_pair(left.branch, right.branch) in branch_six_combinations:
        emit "branch_six_combination_candidate"

    IF unordered_pair(left.branch, right.branch) in branch_clashes:
        emit "branch_clash"

    IF unordered_pair(...) in harms / breaks / punishments:
        emit corresponding fact

    evaluate three-combination and three-meeting only with chart-level set matcher

    RETURN facts
```

“合”不等于“化”。化气需要季节、透干、环境等额外条件；MVP 只输出候选关系。

## 神煞

```text
INTERFACE ShenshaRule:
    id
    version
    reference_fields
    target_fields
    evaluate(chart_or_temporal_context) -> list[ShenshaMatch]

FUNCTION evaluate_shensha(context, rule_set):
    matches = []
    FOR rule IN registry.enabled(rule_set):
        matches += rule.evaluate(context)
    RETURN matches sorted by rule priority
```

每个 match 必须包含参考干支、命中干支、规则版本和来源。不得仅凭神煞生成重大人生结论。
