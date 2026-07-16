# 输入、时区和真太阳时伪代码

## 输入标准化

```text
FUNCTION normalize_birth_input(request):
    REQUIRE valid Gregorian date and time
    REQUIRE gender in allowed enum
    REQUIRE timezone OR resolvable birthplace

    zone = ZoneInfo(request.timezone)
    local_naive = datetime(request.year, month, day, hour, minute, second)

    candidates = localize_with_dst_detection(local_naive, zone)
    IF candidates is empty:
        RAISE NonexistentLocalTime
    IF candidates has two and request.fold is absent:
        RETURN AmbiguousTimeCandidates(candidates)

    civil_time = selected aware datetime

    SWITCH profile.time_basis.default:
        CASE civil_time:
            corrected = civil_time
        CASE local_mean_solar_time:
            REQUIRE longitude
            standard_meridian = utc_offset_hours(civil_time) * 15 degrees
            correction_minutes = 4 * (longitude - standard_meridian)
            corrected = civil_time + correction_minutes
        CASE true_solar_time:
            REQUIRE longitude
            mean_correction = 4 * (longitude - standard_meridian)
            eot_correction = equation_of_time(civil_time.date)
            corrected = civil_time + mean_correction + eot_correction

    RETURN {
        original_time,
        civil_time,
        corrected_time,
        timezone,
        utc_time,
        corrections,
        algorithm_version
    }
```

## 边界分析

```text
FUNCTION analyze_boundaries(corrected_time, solar_terms, profile):
    distances = {
        previous_jie: corrected_time - previous_jie.time,
        next_jie: next_jie.time - corrected_time,
        midnight_00: distance_to_nearest_00(corrected_time),
        late_zi_23: distance_to_nearest_23(corrected_time),
        hour_branch_boundary: distance_to_nearest_two_hour_boundary(corrected_time)
    }

    risks = every distance below configured threshold

    IF selected time correction crosses any boundary:
        mark material_change_possible = true

    RETURN distances and risks
```

真太阳时的 equation-of-time 实现必须放在独立 adapter，并用已知天文库或基准数据验证，不在 Prompt 中计算。
