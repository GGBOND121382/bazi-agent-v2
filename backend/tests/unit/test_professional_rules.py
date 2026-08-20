"""Regression coverage for professional 神煞 and 干支 relation output."""
from app.domain.pillars import Branch, FourPillars, Pillar, Stem
from app.domain.rules.relations import evaluate_relations
from app.domain.rules.shensha import evaluate_shensha, evaluate_shensha_for_target


def _pillar(ganzhi: str) -> Pillar:
    return Pillar(Stem(ganzhi[0]), Branch(ganzhi[1]))


def _four(year: str, month: str, day: str, hour: str) -> FourPillars:
    return FourPillars(
        year=_pillar(year),
        month=_pillar(month),
        day=_pillar(day),
        hour=_pillar(hour),
    )


def test_1995_reference_chart_matches_app_shensha_coverage() -> None:
    pillars = _four("乙亥", "戊子", "丁亥", "戊申")
    hits = evaluate_shensha(pillars)
    by_position = {
        position: {hit.name for hit in hits if hit.target_position == position}
        for position in ("year", "month", "day", "hour")
    }

    assert by_position == {
        "year": {"天乙贵人", "福星贵人", "国印贵人", "天医", "飞刃"},
        "month": {"天乙贵人", "太极贵人", "德秀贵人", "桃花"},
        "day": {
            "天乙贵人",
            "福星贵人",
            "国印贵人",
            "月德合",
            "天罗",
            "十恶大败",
            "天医",
            "飞刃",
        },
        "hour": {"天乙贵人", "德秀贵人", "天德合", "金舆", "披麻", "流霞", "劫煞", "空亡"},
    }
    assert len(hits) == 25
    assert all(hit.rule_id.startswith("SHENSHA-") for hit in hits)
    assert all(hit.rule_version == "classics_v2.3-wenzhen-compatible" for hit in hits)
    assert all(hit.source_title and hit.target_position for hit in hits)


def test_reference_chart_has_half_meeting_harm_and_self_punishment() -> None:
    relations = evaluate_relations(_four("乙亥", "戊子", "丁亥", "戊申"))
    signatures = {(item.type, item.branches, item.element) for item in relations}

    assert ("half_meeting", ("亥", "子"), "water") in signatures
    assert ("harm", ("申", "亥"), None) in signatures
    assert ("punishment", ("亥", "亥"), None) in signatures


def test_stem_combination_clash_and_branch_half_combination_are_detected() -> None:
    stem_relations = evaluate_relations(_four("甲子", "己丑", "庚申", "丙午"))
    stem_signatures = {(item.type, item.branches, item.element) for item in stem_relations}
    assert ("stem_combination", ("甲", "己"), "earth") in stem_signatures
    assert ("stem_clash", ("甲", "庚"), None) in stem_signatures

    branch_relations = evaluate_relations(_four("甲申", "丙子", "戊午", "庚寅"))
    branch_signatures = {(item.type, item.branches, item.element) for item in branch_relations}
    assert ("half_combination", ("申", "子"), "water") in branch_signatures
    assert ("half_combination", ("寅", "午"), "fire") in branch_signatures


def test_1999_user_chart_matches_reference_app_natal_shensha() -> None:
    pillars = _four("己卯", "庚午", "壬子", "丙午")
    hits = evaluate_shensha(pillars, gender="female")
    by_position = {
        position: {hit.name for hit in hits if hit.target_position == position}
        for position in ("year", "month", "day", "hour")
    }
    assert by_position == {
        "year": {"天乙贵人", "血刃", "空亡"},
        "month": {"勾绞煞", "天喜", "飞刃"},
        "day": {
            "天乙贵人", "四废日", "孤鸾煞", "红艳煞", "桃花",
            "红鸾", "披麻", "九丑日", "羊刃",
        },
        "hour": {"月德贵人", "德秀贵人", "勾绞煞", "天喜", "飞刃"},
    }
    assert "将星" not in by_position["year"]
    assert "将星" not in by_position["day"]
    assert "灾煞" not in by_position["month"]
    assert "词馆" not in by_position["month"]


def test_1999_user_chart_dayun_shensha_matches_reference_app() -> None:
    pillars = _four("己卯", "庚午", "壬子", "丙午")
    expected = {
        "辛未": {"太极贵人", "福星贵人", "国印贵人", "月德合", "华盖"},
        "壬申": {"天乙贵人", "太极贵人", "学堂", "金舆", "劫煞", "空亡"},
        "癸酉": {"文昌贵人", "德秀贵人", "天厨贵人", "桃花", "灾煞", "空亡"},
        "甲戌": {"太极贵人", "元辰"},
        "乙亥": {"天德贵人", "禄神", "词馆", "流霞", "亡神"},
        "丙子": {"天乙贵人", "月德贵人", "德秀贵人", "红艳煞", "将星", "桃花", "红鸾", "披麻", "羊刃"},
        "丁丑": {"太极贵人", "德秀贵人", "金舆", "吊客", "寡宿"},
        "戊寅": {"文昌贵人", "德秀贵人", "天厨贵人", "国印贵人", "天德合", "驿马", "亡神", "空亡"},
        "己卯": {"天乙贵人", "将星", "血刃", "空亡"},
        "庚辰": {"太极贵人", "福星贵人", "华盖"},
        "辛巳": {"天乙贵人", "太极贵人", "月德合", "驿马", "天医", "丧门", "孤辰", "劫煞"},
        "壬午": {"勾绞煞", "天喜", "飞刃"},
    }
    for ganzhi, names in expected.items():
        target = _pillar(ganzhi)
        actual = {
            hit.name
            for hit in evaluate_shensha_for_target(
                pillars, target, target_position="dayun", gender="female"
            )
        }
        assert actual == names, ganzhi
