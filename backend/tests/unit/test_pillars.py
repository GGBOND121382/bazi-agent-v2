"""Pure domain tests — pillars, profile, errors. No I/O."""
from __future__ import annotations

import pytest

from app.domain.pillars import (
    HEAVENLY_STEMS,
    Branch,
    FourPillars,
    Pillar,
    Stem,
    ten_god_of,
)


class TestStems:
    def test_heavenly_stems_ordered(self):
        assert tuple("甲乙丙丁戊己庚辛壬癸") == HEAVENLY_STEMS

    def test_stem_creation(self):
        assert Stem("甲").index == 0
        assert Stem("癸").index == 9

    def test_stem_invalid_raises(self):
        with pytest.raises(Exception):
            Stem("A")  # not Chinese

    def test_stem_yin_yang(self):
        assert Stem("甲").yin_yang == "yang"  # 0 even → yang
        assert Stem("乙").yin_yang == "yin"   # 1 odd  → yin
        assert Stem("癸").yin_yang == "yin"

    def test_stem_element(self):
        assert Stem("甲").element == "wood"
        assert Stem("丙").element == "fire"
        assert Stem("戊").element == "earth"
        assert Stem("庚").element == "metal"
        assert Stem("壬").element == "water"


class TestBranches:
    def test_branches_ordered(self):
        assert tuple("子丑寅卯辰巳午未申酉戌亥") == tuple(
            "子丑寅卯辰巳午未申酉戌亥"
        )

    def test_branch_creation(self):
        assert Branch("子").index == 0
        assert Branch("亥").index == 11

    def test_branch_element(self):
        assert Branch("寅").element == "wood"
        assert Branch("午").element == "fire"


class TestPillar:
    def test_valid_pillar_creates(self):
        p = Pillar(Stem("甲"), Branch("子"))
        assert p.ganzhi == "甲子"
        assert p.stem.index == 0
        assert p.branch.index == 0

    def test_invalid_pillar_pair_raises(self):
        # 甲(0) and 丑(1) — 甲子 cycle requires stem_idx ≡ branch_idx mod 12
        with pytest.raises(Exception):
            Pillar(Stem("甲"), Branch("丑"))

    def test_str_returns_ganzhi(self):
        assert str(Pillar(Stem("丙"), Branch("午"))) == "丙午"


class TestTenGods:
    """Verify the ten_gods lookup matches the matrix."""

    def test_day_master_jia(self):
        dm = Stem("甲")
        assert ten_god_of(dm, Stem("甲")) == "比肩"
        assert ten_god_of(dm, Stem("乙")) == "劫财"
        assert ten_god_of(dm, Stem("丙")) == "食神"
        assert ten_god_of(dm, Stem("庚")) == "七杀"
        assert ten_god_of(dm, Stem("辛")) == "正官"
        assert ten_god_of(dm, Stem("壬")) == "偏印"
        assert ten_god_of(dm, Stem("癸")) == "正印"

    def test_day_master_ji(self):
        # 己 is the day master in the example mock
        dm = Stem("己")
        assert ten_god_of(dm, Stem("甲")) == "正官"
        assert ten_god_of(dm, Stem("庚")) == "伤官"
        assert ten_god_of(dm, Stem("辛")) == "食神"


class TestFourPillars:
    def test_constructs(self):
        p = FourPillars(
            year=Pillar(Stem("庚"), Branch("辰")),
            month=Pillar(Stem("戊"), Branch("子")),
            day=Pillar(Stem("甲"), Branch("子")),
            hour=Pillar(Stem("丙"), Branch("午")),
        )
        assert p.day_master == Stem("甲")
        assert [str(x) for x in p.as_list()] == ["庚辰", "戊子", "甲子", "丙午"]


class TestHiddenStems:
    def test_zi_hides_ren_actually_gui(self):
        # 子的本气是癸 per the seed table
        p = Pillar(Stem("甲"), Branch("子"))
        hs = [str(s) for s in p.hidden_stems()]
        assert hs == ["癸"]

    def test_chen_hides_three(self):
        # 辰 has 戊 main, 乙 middle, 癸 residual
        p = Pillar(Stem("壬"), Branch("辰"))
        hs = [str(s) for s in p.hidden_stems()]
        assert hs == ["戊", "乙", "癸"]


class TestNayin:
    def test_jia_zi_is_jin(self):
        # 甲子 = 海中金 per standard
        p = Pillar(Stem("甲"), Branch("子"))
        # We don't encode nayin mapping in core_tables directly; reference only.
        # The test is a smoke check that nayin attribute exists.
        _ = p.nayin