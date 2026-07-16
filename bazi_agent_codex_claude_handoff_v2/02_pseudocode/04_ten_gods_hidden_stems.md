# 十神与藏干伪代码

## 十神

```text
FUNCTION ten_god(day_stem, target_stem):
    day_element = day_stem.element
    target_element = target_stem.element
    same_polarity = day_stem.yin_yang == target_stem.yin_yang

    IF target_element == day_element:
        RETURN 比肩 if same_polarity else 劫财

    IF generates(day_element, target_element):
        RETURN 食神 if same_polarity else 伤官

    IF controls(day_element, target_element):
        RETURN 偏财 if same_polarity else 正财

    IF controls(target_element, day_element):
        RETURN 七杀 if same_polarity else 正官

    IF generates(target_element, day_element):
        RETURN 偏印 if same_polarity else 正印

    RAISE ImpossibleElementRelation
```

## 藏干

```text
FUNCTION derive_hidden_stems(chart):
    facts = []
    FOR pillar IN chart.pillars:
        entries = hidden_stem_table[pillar.branch]
        FOR entry IN entries:
            facts.append({
                location: pillar.position,
                branch: pillar.branch,
                hidden_stem: entry.stem,
                role: entry.role,
                ten_god: ten_god(chart.day_master, entry.stem),
                rule_id: HIDDEN_STEMS_CORE_V1
            })
    RETURN facts
```

权重不是基础事实。若后续用于旺衰评分，权重必须由独立 `hidden_stem_weight_model` 配置，不得混入藏干表。
