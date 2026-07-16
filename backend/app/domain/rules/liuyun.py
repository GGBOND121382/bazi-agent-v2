"""流运 (流年 / 流月 / 流日) context computation.

Pure functions; on-demand. The frontend asks "what does this year/month/day
look like for this chart?" and we compute the relevant 柱 + active 大运 overlay
+ active 神煞 / relations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ...adapters.calendar import CalendarAdapter, LunarPythonAdapter
from ..pillars import FourPillars, Pillar
from .qiyun_dayun import DayunPeriod


@dataclass(frozen=True, slots=True)
class LiuyunContext:
    target_year: int
    year_pillar: Pillar
    month_pillars: tuple[Pillar, ...]  # 12 monthly pillars (rough)
    active_dayun: DayunPeriod | None  # the 大运 that covers target_year's age


_ADAPTER: CalendarAdapter = LunarPythonAdapter()


def _lazy_adapter() -> CalendarAdapter:
    """Lazily resolve a usable calendar adapter (lunar_python primary, sxtwl if available)."""
    global _ADAPTER
    try:
        from ..adapters.calendar import SxtwlAdapter

        _ADAPTER = SxtwlAdapter()
        _ = _ADAPTER.engine_version()
    except Exception:
        _ADAPTER = LunarPythonAdapter()
    return _ADAPTER


def _resolve_year_pillar(year: int, adapter: CalendarAdapter) -> Pillar:
    """Compute the year pillar for the given civil year using 立春 approximation
    at 2024-02-04 (we use Jan 1 of the year as a coarse stand-in)."""

    utc = datetime(year, 6, 15, 12, 0, tzinfo=UTC)  # mid-year proxy
    r = adapter.calculate(utc)
    return r.pillars.year


def _resolve_month_pillars(year: int, adapter: CalendarAdapter) -> tuple[Pillar, ...]:
    pillars: list[Pillar] = []
    for m in range(1, 13):
        utc = datetime(year, m, 15, 12, 0, tzinfo=__import__("datetime").timezone.utc)
        r = adapter.calculate(utc)
        pillars.append(r.pillars.month)
    return tuple(pillars)


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
    """Compute the 流运 context for a target year/month/day.

    `target_year` is required. `target_month`/`target_day` are optional
    refinements (not used by this initial implementation; reserved for F4).
    """
    adapter = _lazy_adapter()
    year_p = _resolve_year_pillar(target_year, adapter)
    month_pillars = _resolve_month_pillars(target_year, adapter)
    # Active 大运: the one whose [start_age, end_age) window covers the age at target_year.
    # Without an explicit birth year in the call, we approximate by index = year offset.
    age_at_target = max(0, target_year - birth_year) if birth_year is not None else 0
    active: DayunPeriod | None = None
    for p in dayun_periods:
        if p.start_age <= age_at_target < p.end_age:
            active = p
            break
    return LiuyunContext(
        target_year=target_year,
        year_pillar=year_p,
        month_pillars=month_pillars,
        active_dayun=active,
    )
