"""B2 rule tests: relations, 神煞 seeds, 起运, 大运, 流运."""
from __future__ import annotations

from datetime import UTC, datetime

from app.domain.pillars import Branch, FourPillars, Pillar, Stem
from app.domain.profile import load_profile
from app.domain.rules import (
    compute_liuyun,
    compute_qiyun_and_dayun,
    evaluate_relations,
    evaluate_shensha,
)


def _chart(*ganzhis: str) -> FourPillars:
    pillars = []
    for gz in ganzhis:
        pillars.append(Pillar(Stem(gz[0]), Branch(gz[1])))
    return FourPillars(year=pillars[0], month=pillars[1], day=pillars[2], hour=pillars[3])


class TestRelations:
    def test_clash_pair_detected(self):
        # 子午冲
        c = _chart("甲子", "丙寅", "戊辰", "庚午")
        rels = evaluate_relations(c)
        types = {r.type for r in rels}
        assert "clash" in types
        clash = next(r for r in rels if r.type == "clash")
        assert set(clash.branches) == {"子", "午"}

    def test_six_combination_detected(self):
        # 子丑合
        c = _chart("甲子", "乙丑", "丙寅", "丁卯")
        rels = evaluate_relations(c)
        combos = [r for r in rels if r.type == "six_combination"]
        assert any(set(r.branches) == {"子", "丑"} for r in combos)

    def test_three_combination_detected(self):
        # 申子辰 三合水局
        c = _chart("壬申", "甲子", "丙辰", "戊午")
        rels = evaluate_relations(c)
        tri = [r for r in rels if r.type == "three_combination"]
        assert any(set(r.branches) == {"申", "子", "辰"} for r in tri)

    def test_harm_pair_detected(self):
        # 子未害
        c = _chart("甲子", "乙未", "丙申", "丁酉")
        rels = evaluate_relations(c)
        harms = [r for r in rels if r.type == "harm"]
        assert any(set(r.branches) == {"子", "未"} for r in harms)


class TestShensha:
    def test_tianyi_guiren_day_stem_jia(self):
        # 戊 day → 贵人 at 丑/未. Need a valid 60-cycle 柱 containing 丑 or 未.
        # 乙丑 (position 1) and 辛未 (position 7) are valid.
        c = _chart("乙丑", "丙寅", "戊辰", "辛未")  # day master 戊
        hits = evaluate_shensha(c)
        names = {h.name for h in hits}
        assert "天乙贵人" in names

    def test_taohua_by_year_branch_group(self):
        # year branch 申 → 桃花 at 酉; need 酉 visible in chart
        c = _chart("甲申", "壬申", "丙申", "癸酉")  # year 申 + hour 酉
        hits = evaluate_shensha(c)
        taohua = [h for h in hits if h.name == "桃花"]
        assert any(h.target == "酉" for h in taohua)

    def test_yima_present(self):
        # year branch 申 → 驿马 at 寅; need 寅 visible in chart
        c = _chart("甲申", "壬申", "丙寅", "庚申")  # year 申 + month 寅
        hits = evaluate_shensha(c)
        names = {h.name for h in hits}
        assert "驿马" in names

    def test_wenchang_present(self):
        # day stem 壬 → 文昌 at 寅; need 壬 in day position and 寅 in chart.
        # 壬申 day → 文昌 = 寅. Need 寅 branch: 壬寅 (position 50).
        c = _chart("壬申", "癸酉", "壬寅", "癸卯")  # day master 壬
        hits = evaluate_shensha(c)
        names = {h.name for h in hits}
        assert "文昌贵人" in names


class TestQiyunDayun:
    def test_male_yang_year_forwards(self):
        # 男 + 阳年 (甲/丙/戊/庚/壬) → forward
        # Use a chart with year stem 甲 (yang)
        c = _chart("甲子", "丙寅", "戊辰", "庚午")  # year stem 甲
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
        # First 大运 pillar should be month_pillar + offset (default 1)
        # month 丙寅 → +1 forward on 60-cycle
        # Each period is 10 years
        for d in r.dayun:
            assert d.end_age - d.start_age == 10

    def test_female_yang_year_reverses(self):
        # 女 + 阳年 → reverse
        c = _chart("甲子", "丙寅", "戊辰", "庚午")  # year stem 甲 (yang)
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
        # First pillar is month (丙寅) advanced by offset (1) → 丁卯
        assert r.dayun[0].ganzhi == "丁卯"
        # Second → 戊辰
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
        # Day master of ctx.year_pillar is just the year's stem; sanity: must be a valid stem
        assert ctx.year_pillar.stem.char in "甲乙丙丁戊己庚辛壬癸"
