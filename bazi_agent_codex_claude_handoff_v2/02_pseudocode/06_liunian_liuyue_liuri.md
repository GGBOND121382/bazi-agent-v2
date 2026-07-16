# 流年、流月、流日伪代码

```text
FUNCTION temporal_context(chart, target_datetime, dayun_list, profile):
    current_dayun = find period containing target_datetime

    calendar = calendar_engine.calculate(target_datetime, profile)
    liunian = calendar.year_pillar
    liuyue = calendar.month_pillar
    liuri = calendar.day_pillar
    liushi = calendar.hour_pillar if requested

    contexts = {
        natal: chart.pillars,
        dayun: current_dayun,
        liunian,
        liuyue,
        liuri,
        liushi
    }

    relations = []
    FOR upper_level, lower_level IN allowed_comparison_pairs:
        relations += relation_engine.compare(contexts[upper_level], contexts[lower_level])

    RETURN TemporalContext(contexts, relations)
```

## 允许的层级比较

- 原局内部；
- 大运 ↔ 原局；
- 流年 ↔ 原局与大运；
- 流月 ↔ 原局、大运、流年；
- 流日 ↔ 原局、大运、流年、流月；
- 流时仅在用户明确请求时计算。

报告不得脱离上层背景单独解释流日。
