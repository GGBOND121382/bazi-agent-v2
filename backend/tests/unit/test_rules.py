"""B2 rule tests: relations, 神煞 seeds, 起运, 大运, 流运."""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domain.pillars import Branch, FourPillars, Pillar, Stem
from app.domain.profile import load_profile
from app.domain.rules import (
    compute_liuyun,
    compute_qiyun_and_dayun,
    evaluate_relations,
    evaluate_shensha,
)
from app.domain.rules.temporal import build_temporal_context


def _chart(*ganzhis: str) -> FourPillars:
    pillars = []
    for gz in ganzhis:
        pillars.append(Pillar(Stem(gz[0]), Branch(gz[1])))
    return FourPillars(year=pillars[0], month=pillars[1], day=pillars[2], hour=pillars[3])


class TestRelations:
    def test_clash_pair_detected(self):
        c = _chart("甲子", "丙寅", "戊辰", "庚午")
        rels = evaluate_relations(c)
        types = {r.type for r in rels}
        assert "clash" in types
        clash = next(r for r in rels if r.type == "clash")
        assert set(clash.branches) == {"子", "午"}

    def test_six_combination_detected(self):
        c = _chart("甲子", "乙丑", "丙寅", "丁卯")
        rels = evaluate_relations(c)
        combos = [r for r in rels if r.type == "six_combination"]
        assert any(set(r.branches) == {"子", "丑"} for r in combos)

    def test_three_combination_detected(self):
        c = _chart("壬申", "甲子", "丙辰", "戊午")
        rels = evaluate_relations(c)
        tri = [r for r in rels if r.type == "three_combination"]
        assert any(set(r.branches) == {"申", "子", "辰"} for r in tri)

    def test_harm_pair_detected(self):
        c = _chart("甲子", "乙未", "丙申", "丁酉")
        rels = evaluate_relations(c)
        harms = [r for r in rels if r.type == "harm"]
        assert any(set(r.branches) == {"子", "未"} for r in harms)


class TestShensha:
    def test_tianyi_guiren_day_stem_jia(self):
        c = _chart("乙丑", "丙寅", "戊辰", "辛未")
        hits = evaluate_shensha(c)
        names = {h.name for h in hits}
        assert "天乙贵人" in names

    def test_taohua_by_year_branch_group(self):
        c = _chart("甲申", "壬申", "丙申", "癸酉")
        hits = evaluate_shensha(c)
        taohua = [h for h in hits if h.name == "桃花"]
        assert any(h.target == "酉" for h in taohua)

    def test_yima_present(self):
        c = _chart("甲申", "壬申", "丙寅", "庚申")
        hits = evaluate_shensha(c)
        names = {h.name for h in hits}
        assert "驿马" in names

    def test_wenchang_present(self):
        c = _chart("壬申", "癸酉", "壬寅", "癸卯")
        hits = evaluate_shensha(c)
        names = {h.name for h in hits}
        assert "文昌贵人" in names


class TestQiyunDayun:
    def test_male_yang_year_forwards(self):
        c = _chart("甲子", "丙寅", "戊辰", "庚午")
        p = load_profile()
        r = compute_qiyun_and_dayun(
            pillars=c,
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="male",
            profile=p,
            dayun_count=8,
        )
        assert r.direction == "forward"
        assert r.start_age_years >= 0
        assert len(r.dayun) == 8
        for d in r.dayun:
            assert d.end_age - d.start_age == 10

    def test_female_yang_year_reverses(self):
        c = _chart("甲子", "丙寅", "戊辰", "庚午")
        p = load_profile()
        r = compute_qiyun_and_dayun(
            pillars=c,
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="female",
            profile=p,
            dayun_count=8,
        )
        assert r.direction == "reverse"
        assert r.dayun[0].ganzhi == "乙丑"
        assert r.dayun[1].ganzhi == "甲子"

    def test_dayun_offsets_advance_correctly(self):
        c = _chart("甲子", "丙寅", "戊辰", "庚午")
        p = load_profile()
        r = compute_qiyun_and_dayun(
            pillars=c,
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="male",
            profile=p,
            dayun_count=8,
        )
        assert r.dayun[0].ganzhi == "丁卯"
        assert r.dayun[1].ganzhi == "戊辰"


class TestLiuyun:
    def test_year_pillar_resolves(self):
        c = _chart("甲子", "丙寅", "戊辰", "庚午")
        p = load_profile()
        qd = compute_qiyun_and_dayun(
            pillars=c,
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="male",
            profile=p,
            dayun_count=8,
        )
        ctx = compute_liuyun(
            natal=c,
            qiyun_start_age_years=qd.start_age_years,
            dayun_periods=qd.dayun,
            target_year=2025,
        )
        assert ctx.year_pillar is not None
        assert len(ctx.month_pillars) == 12
        assert ctx.year_pillar.stem.char in "甲乙丙丁戊己庚辛壬癸"


def test_exact_temporal_context_matches_1999_reference_app() -> None:
    chart = _chart("己卯", "庚午", "壬子", "丙午")
    context = build_temporal_context(
        chart,
        datetime(1999, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        gender="female",
        target_year=2026,
        target_date=date(2026, 7, 17),
    )
    assert context["qiyun"] == {
        "direction": "forward",
        "start_years": 2,
        "start_months": 9,
        "start_days": 17,
        "start_hours": 0,
        "start_age_years": 2,
        "start_datetime": "2002-04-15T12:00:00+08:00",
        "rule_id": "QIYUN-LUNAR-PYTHON-SECT2-V2",
    }

    active = context["active_dayun"]
    assert isinstance(active, dict)
    assert active["ganzhi"] == "癸酉"
    assert active["stem_ten_god"] == "劫财"
    assert active["branch_ten_god"] == "正印"
    assert active["hidden_stems"] == [{"stem": "辛", "ten_god": "正印"}]
    assert active["growth_stage"] == "沐浴"
    assert active["self_seat"] == "病"
    assert active["xunkong"] == "戌亥"
    assert active["nayin"] == "剑锋金"
    assert {item["name"] for item in active["shensha"]} == {
        "文昌贵人", "德秀贵人", "天厨贵人", "桃花", "灾煞", "空亡"
    }

    year = context["year"]
    assert isinstance(year, dict)
    assert year["ganzhi"] == "丙午"
    assert year["xiaoyun"] == "甲戌"
    assert year["stem_ten_god"] == "偏财"
    assert year["branch_ten_god"] == "正财"
    assert year["hidden_stems"] == [
        {"stem": "丁", "ten_god": "正财"},
        {"stem": "己", "ten_god": "正官"},
    ]
    assert year["growth_stage"] == "胎"
    assert year["self_seat"] == "帝旺"
    assert year["xunkong"] == "寅卯"
    assert year["nayin"] == "天河水"
    assert {item["name"] for item in year["shensha"]} == {
        "月德贵人", "德秀贵人", "勾绞煞", "天喜", "飞刃"
    }

    months = context["months"]
    assert isinstance(months, list)
    assert [item["ganzhi"] for item in months] == [
        "庚寅", "辛卯", "壬辰", "癸巳", "甲午", "乙未",
        "丙申", "丁酉", "戊戌", "己亥", "庚子", "辛丑",
    ]
    assert months[0]["start_datetime"] == "2026-02-04T04:02:08+08:00"
    july_month = months[5]
    assert july_month["ganzhi"] == "乙未"
    assert july_month["stem_ten_god"] == "伤官"
    assert july_month["branch_ten_god"] == "正官"
    assert july_month["hidden_stems"] == [
        {"stem": "己", "ten_god": "正官"},
        {"stem": "丁", "ten_god": "正财"},
        {"stem": "乙", "ten_god": "伤官"},
    ]
    assert july_month["growth_stage"] == "养"
    assert july_month["self_seat"] == "养"
    assert july_month["xunkong"] == "辰巳"
    assert july_month["nayin"] == "沙中金"
    assert isinstance(july_month["shensha"], list)

    selected_day = context["selected_day"]
    assert isinstance(selected_day, dict)
    assert selected_day["date"] == "2026-07-17"
    assert selected_day["month_ganzhi"] == "乙未"
    assert selected_day["ganzhi"] == "壬辰"
    assert selected_day["stem_ten_god"] == "比肩"
    assert selected_day["branch_ten_god"] == "七杀"
    assert selected_day["hidden_stems"] == [
        {"stem": "戊", "ten_god": "七杀"},
        {"stem": "乙", "ten_god": "伤官"},
        {"stem": "癸", "ten_god": "劫财"},
    ]
    assert selected_day["growth_stage"] == "墓"
    assert selected_day["self_seat"] == "墓"
    assert selected_day["xunkong"] == "午未"
    assert selected_day["nayin"] == "长流水"
    assert isinstance(selected_day["shensha"], list)
