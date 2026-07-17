"""B2 rule tests: relations, 神煞 seeds, 起运, 大运, 流运."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
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
    pillars = [Pillar(Stem(gz[0]), Branch(gz[1])) for gz in ganzhis]
    return FourPillars(year=pillars[0], month=pillars[1], day=pillars[2], hour=pillars[3])


def _reference_temporal_context() -> dict[str, object]:
    return build_temporal_context(
        _chart("己卯", "庚午", "壬子", "丙午"),
        datetime(1999, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        gender="female",
        target_year=2026,
        target_date=date(2026, 7, 17),
    )


def _dict_item(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return value


def _list_items(value: object) -> list[dict[str, Any]]:
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


class TestRelations:
    def test_clash_pair_detected(self):
        rels = evaluate_relations(_chart("甲子", "丙寅", "戊辰", "庚午"))
        assert "clash" in {relation.type for relation in rels}
        clash = next(relation for relation in rels if relation.type == "clash")
        assert set(clash.branches) == {"子", "午"}

    def test_six_combination_detected(self):
        rels = evaluate_relations(_chart("甲子", "乙丑", "丙寅", "丁卯"))
        combos = [relation for relation in rels if relation.type == "six_combination"]
        assert any(set(relation.branches) == {"子", "丑"} for relation in combos)

    def test_three_combination_detected(self):
        rels = evaluate_relations(_chart("壬申", "甲子", "丙辰", "戊午"))
        triples = [relation for relation in rels if relation.type == "three_combination"]
        assert any(set(relation.branches) == {"申", "子", "辰"} for relation in triples)

    def test_harm_pair_detected(self):
        rels = evaluate_relations(_chart("甲子", "乙未", "丙申", "丁酉"))
        harms = [relation for relation in rels if relation.type == "harm"]
        assert any(set(relation.branches) == {"子", "未"} for relation in harms)


class TestShensha:
    def test_tianyi_guiren_day_stem_jia(self):
        names = {hit.name for hit in evaluate_shensha(_chart("乙丑", "丙寅", "戊辰", "辛未"))}
        assert "天乙贵人" in names

    def test_taohua_by_year_branch_group(self):
        hits = evaluate_shensha(_chart("甲申", "壬申", "丙申", "癸酉"))
        assert any(hit.name == "桃花" and hit.target == "酉" for hit in hits)

    def test_yima_present(self):
        names = {hit.name for hit in evaluate_shensha(_chart("甲申", "壬申", "丙寅", "庚申"))}
        assert "驿马" in names

    def test_wenchang_present(self):
        names = {hit.name for hit in evaluate_shensha(_chart("壬申", "癸酉", "壬寅", "癸卯"))}
        assert "文昌贵人" in names


class TestQiyunDayun:
    def test_male_yang_year_forwards(self):
        result = compute_qiyun_and_dayun(
            pillars=_chart("甲子", "丙寅", "戊辰", "庚午"),
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="male",
            profile=load_profile(),
            dayun_count=8,
        )
        assert result.direction == "forward"
        assert result.start_age_years >= 0
        assert len(result.dayun) == 8
        assert all(period.end_age - period.start_age == 10 for period in result.dayun)

    def test_female_yang_year_reverses(self):
        result = compute_qiyun_and_dayun(
            pillars=_chart("甲子", "丙寅", "戊辰", "庚午"),
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="female",
            profile=load_profile(),
            dayun_count=8,
        )
        assert result.direction == "reverse"
        assert result.dayun[0].ganzhi == "乙丑"
        assert result.dayun[1].ganzhi == "甲子"

    def test_dayun_offsets_advance_correctly(self):
        result = compute_qiyun_and_dayun(
            pillars=_chart("甲子", "丙寅", "戊辰", "庚午"),
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="male",
            profile=load_profile(),
            dayun_count=8,
        )
        assert result.dayun[0].ganzhi == "丁卯"
        assert result.dayun[1].ganzhi == "戊辰"


class TestLiuyun:
    def test_year_pillar_resolves(self):
        natal = _chart("甲子", "丙寅", "戊辰", "庚午")
        qiyun = compute_qiyun_and_dayun(
            pillars=natal,
            birth_utc=datetime(1984, 1, 15, 12, 0, tzinfo=UTC),
            gender="male",
            profile=load_profile(),
            dayun_count=8,
        )
        context = compute_liuyun(
            natal=natal,
            qiyun_start_age_years=qiyun.start_age_years,
            dayun_periods=qiyun.dayun,
            target_year=2025,
        )
        assert context.year_pillar is not None
        assert len(context.month_pillars) == 12
        assert context.year_pillar.stem.char in "甲乙丙丁戊己庚辛壬癸"


def test_1999_reference_qiyun_and_active_dayun_are_complete() -> None:
    context = _reference_temporal_context()
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
    active = _dict_item(context["active_dayun"])
    assert active["ganzhi"] == "癸酉"
    assert active["stem_ten_god"] == "劫财"
    assert active["branch_ten_god"] == "正印"
    assert active["hidden_stems"] == [{"stem": "辛", "ten_god": "正印"}]
    assert active["growth_stage"] == "沐浴"
    assert active["self_seat"] == "病"
    assert active["xunkong"] == "戌亥"
    assert active["nayin"] == "剑锋金"
    assert {item["name"] for item in _list_items(active["shensha"])} == {
        "文昌贵人", "德秀贵人", "天厨贵人", "桃花", "灾煞", "空亡"
    }


def test_1999_reference_2026_liunian_fields_are_complete() -> None:
    year = _dict_item(_reference_temporal_context()["year"])
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
    assert {item["name"] for item in _list_items(year["shensha"])} == {
        "月德贵人", "德秀贵人", "勾绞煞", "天喜", "飞刃"
    }


def test_1999_reference_2026_liuyue_fields_are_complete() -> None:
    months = _list_items(_reference_temporal_context()["months"])
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


def test_1999_reference_selected_liuri_fields_are_complete() -> None:
    selected_day = _dict_item(_reference_temporal_context()["selected_day"])
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
