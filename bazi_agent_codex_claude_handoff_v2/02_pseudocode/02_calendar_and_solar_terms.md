# 农历、节气和柱位历法伪代码

## Adapter 原则

```text
INTERFACE CalendarEngineProtocol:
    calculate(aware_datetime, profile) -> CalendarEngineResult
    list_solar_terms(year, timezone) -> list[SolarTerm]
    metadata() -> EngineMetadata
```

## 主流程

```text
FUNCTION calculate_calendar(dt, profile):
    engine_result = third_party_library.calculate(dt)

    lunar_date = normalize_lunar_date(engine_result)
    solar_terms = normalize_solar_terms(engine_result, dt.year - 1 .. dt.year + 1)

    year_pillar = choose_year_pillar(engine_result, profile.calendar.year_boundary)
    month_pillar = choose_month_pillar(engine_result, profile.calendar.month_boundary)
    day_pillar = choose_day_pillar(engine_result, profile.day_boundary)
    hour_pillar = choose_hour_pillar(engine_result, day_pillar, profile.day_boundary)

    RETURN internal DTO only
```

## 月支的可验证映射

以精确“节”交接时刻划分：

```text
立春→寅, 惊蛰→卯, 清明→辰, 立夏→巳,
芒种→午, 小暑→未, 立秋→申, 白露→酉,
寒露→戌, 立冬→亥, 大雪→子, 小寒→丑
```

## 五虎遁月干校验

```text
甲己年：丙寅起
乙庚年：戊寅起
丙辛年：庚寅起
丁壬年：壬寅起
戊癸年：甲寅起

month_stem_index = (yin_month_start_stem_index + month_offset_from_yin) mod 10
```

## 五鼠遁时干校验

```text
甲己日：甲子起
乙庚日：丙子起
丙辛日：戊子起
丁壬日：庚子起
戊癸日：壬子起

hour_stem_index = (zi_hour_start_stem_index + hour_branch_index) mod 10
```

日柱不要在 MVP 中自行实现天文公式。使用两个独立库交叉核验，并用金标案例锁定版本。
