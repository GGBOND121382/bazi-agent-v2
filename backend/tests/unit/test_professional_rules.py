"""Regression coverage for professional 神煞 and 干支 relation output."""
from app.domain.pillars import Branch, FourPillars, Pillar, Stem
from app.domain.rules.relations import evaluate_relations
from app.domain.rules.shensha import evaluate_shensha


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
    assert all(hit.rule_version == "classics_v2.1" for hit in hits)
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
