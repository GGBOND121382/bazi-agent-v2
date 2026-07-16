"""sxtwl adapter — secondary (cross-check) calendar engine.

sxtwl is a small but trustworthy Chinese calendar library. We use it as the
复核 (recheck) engine: every chart must produce identical 柱 from both engines
within tolerance, otherwise we raise CrossEngineConflictError.
"""
from __future__ import annotations

import time as _time
from datetime import datetime
from functools import lru_cache

from ...domain.chart import EngineVersion, Fact
from ...domain.pillars import Branch, FourPillars, Pillar, Stem
from .base import CalendarAdapter, CalendarResult

_HEAVENLY_STEMS_SXTWL = tuple("甲乙丙丁戊己庚辛壬癸")
_EARTHLY_BRANCHES_SXTWL = tuple("子丑寅卯辰巳午未申酉戌亥")


@lru_cache(maxsize=1)
def _lib_version() -> str:
    try:
        import sxtwl

        return str(getattr(sxtwl, "__version__", "unknown"))
    except Exception:  # pragma: no cover
        return "unknown"


class SxtwlAdapter(CalendarAdapter):
    name = "sxtwl"

    def __init__(self, *, library_version: str | None = None) -> None:
        self._library_version = library_version or _lib_version()

    def engine_version(self) -> EngineVersion:
        return EngineVersion(engine=self.name, version=self._library_version, took_ms=0.0)

    def calculate(self, calculation_time: datetime) -> CalendarResult:
        started = _time.perf_counter()
        if calculation_time.tzinfo is None:
            raise ValueError("calculation_time must be timezone-aware")
        try:
            import sxtwl
        except ImportError as exc:
            raise RuntimeError(
                "sxtwl is not installed in this environment; "
                "use ReferenceAdapter as a stand-in 复核 engine."
            ) from exc
        day_obj = sxtwl.fromSolar(
            calculation_time.year, calculation_time.month, calculation_time.day
        )
        gz_year = day_obj.getYearGZ()
        gz_month = day_obj.getMonthGZ()
        gz_day = day_obj.getDayGZ()
        # sxtwl.getHourGZ accepts a normal 0-23 wall-clock hour. Passing a
        # pre-computed 0-11 branch index shifts the result and creates false
        # cross-engine conflicts on platforms where sxtwl is installed.
        gz_hour = day_obj.getHourGZ(calculation_time.hour)

        year_p = Pillar(
            Stem(_HEAVENLY_STEMS_SXTWL[gz_year.tg]),
            Branch(_EARTHLY_BRANCHES_SXTWL[gz_year.dz]),
        )
        month_p = Pillar(
            Stem(_HEAVENLY_STEMS_SXTWL[gz_month.tg]),
            Branch(_EARTHLY_BRANCHES_SXTWL[gz_month.dz]),
        )
        day_p = Pillar(
            Stem(_HEAVENLY_STEMS_SXTWL[gz_day.tg]),
            Branch(_EARTHLY_BRANCHES_SXTWL[gz_day.dz]),
        )
        hour_p = Pillar(
            Stem(_HEAVENLY_STEMS_SXTWL[gz_hour.tg]),
            Branch(_EARTHLY_BRANCHES_SXTWL[gz_hour.dz]),
        )

        pillars = FourPillars(year=year_p, month=month_p, day=day_p, hour=hour_p)
        facts: list[Fact] = [
            Fact("FACT-Y-1", "pillar", str(year_p), "RULE-PILLAR-YEAR", (calculation_time.year,)),
            Fact(
                "FACT-M-1",
                "pillar",
                str(month_p),
                "RULE-PILLAR-MONTH",
                (calculation_time.year, calculation_time.month),
            ),
            Fact(
                "FACT-D-1",
                "pillar",
                str(day_p),
                "RULE-PILLAR-DAY",
                (calculation_time.year, calculation_time.month, calculation_time.day),
            ),
            Fact(
                "FACT-H-1",
                "pillar",
                str(hour_p),
                "RULE-PILLAR-HOUR",
                (
                    calculation_time.year,
                    calculation_time.month,
                    calculation_time.day,
                    calculation_time.hour,
                ),
            ),
            Fact(
                "FACT-DM-1",
                "day_master",
                str(pillars.day_master),
                "RULE-DAY-MASTER",
                (str(day_p.stem),),
            ),
        ]
        took = (_time.perf_counter() - started) * 1000.0
        return CalendarResult(
            pillars=pillars,
            facts=tuple(facts),
            warnings=(),
            engine_version=EngineVersion(self.name, self._library_version, took),
        )
