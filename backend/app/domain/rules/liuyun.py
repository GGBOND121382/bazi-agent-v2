"""Backward-compatible 流运 context helpers.

New API responses use :mod:`temporal`; this small wrapper remains for callers
and tests that only need year/month pillars and an active legacy DayunPeriod.
It deliberately has no dependency on calendar adapters, avoiding a domain ↔
adapter import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass

from lunar_python import Solar

from ..pillars import Branch, FourPillars, Pillar, Stem
from .qiyun_dayun import DayunPeriod


@dataclass(frozen=True, slots=True)
class LiuyunContext:
    target_year: int
    year_pillar: Pillar
    month_pillars: tuple[Pillar, ...]
    active_dayun: DayunPeriod | None


def _pillar(ganzhi: str) -> Pillar:
    return Pillar(Stem(ganzhi[0]), Branch(ganzhi[1]))


def _resolve_year_pillar(year: int) -> Pillar:
    lunar = Solar.fromYmdHms(year, 6, 15, 12, 0, 0).getLunar()
    return _pillar(str(lunar.getYearInGanZhiExact()))


def _resolve_month_pillars(year: int) -> tuple[Pillar, ...]:
    # Five-tiger-dun months from the exact year's 立春干支 sequence.
    from lunar_python.eightchar import LiuYue

    # LiuYue only needs a parent exposing getGanZhi; use a tiny local object.
    class _Year:
        def getGanZhi(self) -> str:
            return _resolve_year_pillar(year).ganzhi

    return tuple(_pillar(str(LiuYue(_Year(), index).getGanZhi())) for index in range(12))


def compute_liuyun(
    *,
    natal: FourPillars,
    qiyun_start_age_years: int,
    dayun_periods: tuple[DayunPeriod, ...],
    target_year: int,
    target_month: int | None = None,
    target_day: int | None = None,
    birth_year: int | None = None,
) -> LiuyunContext:
    del natal, qiyun_start_age_years, target_month, target_day
    age_at_target = max(0, target_year - birth_year) if birth_year is not None else 0
    active = next(
        (period for period in dayun_periods if period.start_age <= age_at_target < period.end_age),
        None,
    )
    return LiuyunContext(
        target_year=target_year,
        year_pillar=_resolve_year_pillar(target_year),
        month_pillars=_resolve_month_pillars(target_year),
        active_dayun=active,
    )
