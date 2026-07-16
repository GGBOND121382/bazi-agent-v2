# 四柱组装伪代码

```text
FUNCTION assemble_four_pillars(calendar_result, profile):
    pillars = [year, month, day, hour]

    FOR position, ganzhi IN pillars:
        stem = lookup_stem(ganzhi.first_character)
        branch = lookup_branch(ganzhi.second_character)
        ASSERT stem and branch exist
        ASSERT sexagenary_pair_is_valid(stem.index, branch.index)

        pillar = {
            position,
            ganzhi,
            stem,
            branch,
            hidden_stems: hidden_stem_table[branch],
            nayin: calendar_result.nayin[position],
            twelve_stage: calculate_or_adapter(position, day_stem, branch),
            source_engine_fields
        }

    day_master = day_pillar.stem

    RETURN FourPillars(
        pillars,
        day_master,
        calculation_profile_id,
        engine_versions,
        boundary_warnings
    )
```

## 一致性检查

```text
- 四柱必须都是合法六十甲子组合；
- 日主必须等于日柱天干；
- 所有十神以日主为参考重新计算；
- 藏干只能来自版本化表；
- 任何文本字段不得反向覆盖结构化字段。
```
