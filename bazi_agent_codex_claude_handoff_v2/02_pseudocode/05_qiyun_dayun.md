# 起运与大运伪代码

## 顺逆

```text
FUNCTION determine_direction(gender, year_stem, profile):
    yang_year = year_stem.yin_yang == yang

    IF profile.direction_rule == gender_and_year_stem_yinyang:
        forward = (gender == male AND yang_year) OR
                  (gender == female AND NOT yang_year)
        RETURN forward ? FORWARD : REVERSE
```

## 参考节气

```text
FUNCTION choose_reference_jie(birth_time, direction, solar_terms):
    jie_terms = filter solar_terms to 12 "jie" boundaries
    IF direction == FORWARD:
        RETURN first jie strictly after birth_time
    ELSE:
        RETURN last jie at or before birth_time
```

是否“严格大于”和交接时刻相等时如何处理必须由 profile 固定并测试。

## 三天一岁折算

```text
FUNCTION interval_to_start_age(interval_seconds, profile):
    total_hours = abs(interval_seconds) / 3600

    # 传统折算：3日 = 1岁；1日 = 4月；1小时 = 5日
    total_age_months = total_hours / 6
    years = floor(total_age_months / 12)
    remaining_months = total_age_months - years * 12
    months = floor(remaining_months)
    days = round((remaining_months - months) * profile.traditional_month_days)

    normalize carry: 30 days -> 1 month; 12 months -> 1 year
    RETURN StartAge(years, months, days, raw_interval_seconds, strategy_id)
```

## 起运日期

```text
start_datetime = birth_datetime + relativedelta(
    years=start_age.years,
    months=start_age.months,
    days=start_age.days
)
```

保留原始间隔和折算结果，不要只保存最终日期。

## 大运柱

```text
FUNCTION generate_dayun(month_pillar, direction, start_datetime, count):
    month_cycle_index = sexagenary_index(month_pillar)
    step = +1 if FORWARD else -1

    FOR i in 1..count:
        pillar = sexagenary_cycle[(month_cycle_index + step * i) mod 60]
        period_start = start_datetime + (i - 1) calendar years * 10
        period_end = start_datetime + i calendar years * 10 - smallest_time_unit
        emit DayunPeriod(i, pillar, period_start, period_end)
```

不要用固定秒数表示十年。
