"""lunar_python adapter — primary calendar engine.

Wraps the lunar_python library. Outputs FourPillars + facts + warnings.

NOTE: this module is the ONLY place that imports lunar_python.
"""
from __future__ import annotations

import time as _time
from datetime import datetime
from functools import lru_cache

from lunar_python import Solar

from ...domain.chart import EngineVersion, Fact
from ...domain.pillars import Branch, FourPillars, Pillar, Stem
from .base import CalendarAdapter, CalendarResult


@lru_cache(maxsize=1)
def _lib_version() -> str:
    try:
        import lunar_python
        return getattr(lunar_python, "__version__", "unknown")
    except Exception:  # pragma: no cover
        return "unknown"


class LunarPythonAdapter(CalendarAdapter):
    name = "lunar_python"

    def __init__(self, *, library_version: str | None = None) -> None:
        self._library_version = library_version or _lib_version()

    def engine_version(self) -> EngineVersion:
        return EngineVersion(engine=self.name, version=self._library_version, took_ms=0.0)

    def calculate(self, calculation_time: datetime) -> CalendarResult:
        started = _time.perf_counter()
        if calculation_time.tzinfo is None:
            raise ValueError("calculation_time must be timezone-aware")

        # lunar_python consumes wall-clock fields and has no timezone model. The
        # caller must therefore pass the selected civil/solar calculation time,
        # not the normalized UTC instant.
        local_naive = calculation_time.replace(tzinfo=None)
        solar = Solar.fromYmdHms(
            local_naive.year, local_naive.month, local_naive.day,
            local_naive.hour, local_naive.minute, local_naive.second,
        )
        lunar = solar.getLunar()

        year_p = self._build_pillar(lunar.getYearInGanZhi(), "year")
        month_p = self._build_pillar(lunar.getMonthInGanZhi(), "month")
        day_p = self._build_pillar(lunar.getDayInGanZhi(), "day")
        hour_p = self._build_pillar(lunar.getTimeInGanZhi(), "hour")

        pillars = FourPillars(year=year_p, month=month_p, day=day_p, hour=hour_p)

        facts: list[Fact] = [
            Fact("FACT-Y-1", "pillar", str(year_p), "RULE-PILLAR-YEAR", (calculation_time.year,)),
            Fact("FACT-M-1", "pillar", str(month_p), "RULE-PILLAR-MONTH", (calculation_time.year, calculation_time.month)),
            Fact("FACT-D-1", "pillar", str(day_p), "RULE-PILLAR-DAY", (calculation_time.year, calculation_time.month, calculation_time.day)),
            Fact("FACT-H-1", "pillar", str(hour_p), "RULE-PILLAR-HOUR", (calculation_time.year, calculation_time.month, calculation_time.day, calculation_time.hour)),
            Fact("FACT-DM-1", "day_master", str(pillars.day_master), "RULE-DAY-MASTER", (str(day_p.stem),)),
        ]
        took = (_time.perf_counter() - started) * 1000.0
        return CalendarResult(
            pillars=pillars,
            facts=tuple(facts),
            warnings=(),
            engine_version=EngineVersion(self.name, self._library_version, took),
        )

    def nearest_jie(self, calculation_time: datetime, *, forward: bool) -> datetime:
        """Return the precise next/previous 节 instant in the adapter time basis."""
        if calculation_time.tzinfo is None:
            raise ValueError("calculation_time must be timezone-aware")
        local = calculation_time.replace(tzinfo=None)
        solar = Solar.fromYmdHms(
            local.year, local.month, local.day, local.hour, local.minute, local.second
        )
        lunar = solar.getLunar()
        jie = lunar.getNextJie(False) if forward else lunar.getPrevJie(False)
        value = jie.getSolar()
        return datetime(
            value.getYear(),
            value.getMonth(),
            value.getDay(),
            value.getHour(),
            value.getMinute(),
            value.getSecond(),
            tzinfo=calculation_time.tzinfo,
        )

    @staticmethod
    def _build_pillar(gz: str, position: str) -> Pillar:
        if not isinstance(gz, str) or len(gz) < 2:
            raise ValueError(f"unexpected ganzhi from library for {position}: {gz!r}")
        stem = Stem(gz[0])
        branch = Branch(gz[1])
        return Pillar(stem=stem, branch=branch)
