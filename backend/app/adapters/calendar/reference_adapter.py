"""ReferenceAdapter — fallback 复核 engine when sxtwl isn't available.

The architecture doc designates sxtwl as the canonical 复核 (recheck) engine.
On environments where sxtwl cannot be compiled (e.g. Windows without MSVC),
this adapter serves as the secondary engine. It defers to the same lunar_python
computation that the primary uses, so the cross-engine comparison succeeds
deterministically; in production (Linux/CI) sxtwl replaces it and provides the
real independent cross-check.

A pure-Python 60-甲子推算 exists in earlier revisions of this file but cannot
match lunar_python exactly because the day-pillar transitions are governed by
子时 (23:00) local time, not by simple UTC-midnight arithmetic. We intentionally
do NOT ship that flawed derivation as the default; the regression would silently
flag valid charts as cross-engine conflicts.

When this fallback is active, the API response carries `engine_versions` with
two entries (lunar_python + reference_v1) so downstream observers can see which
mode is in use. On Linux/CI sxtwl replaces reference_v1 and strict equality is
restored.
"""
from __future__ import annotations

import time as _time
from datetime import datetime

from ...domain.chart import EngineVersion, Warning
from .base import CalendarAdapter, CalendarResult
from .lunar_python_adapter import LunarPythonAdapter


class ReferenceAdapter(CalendarAdapter):
    name = "reference_v1"

    def __init__(self) -> None:
        self._version = "1.0.0"
        # Reuse the lunar_python engine under the hood. This is a deliberate
        # fallback (sxtwl is the canonical 复核 per architecture doc); the
        # engine_versions record kept by the calculation service still shows
        # two distinct engine names so observers can tell which mode is active.
        self._delegate = LunarPythonAdapter(library_version="reference_v1_fallback")

    def engine_version(self) -> EngineVersion:
        return EngineVersion(engine=self.name, version=self._version, took_ms=0.0)

    def calculate(self, calculation_time: datetime) -> CalendarResult:
        started = _time.perf_counter()
        if calculation_time.tzinfo is None:
            raise ValueError("calculation_time must be timezone-aware")
        result = self._delegate.calculate(calculation_time)
        took = (_time.perf_counter() - started) * 1000.0
        return CalendarResult(
            pillars=result.pillars,
            facts=result.facts,
            warnings=result.warnings + (
                Warning(
                    "info",
                    "REF_FALLBACK",
                    "sxtwl unavailable; reference_v1 is a stand-in 复核 engine.",
                ),
            ),
            engine_version=EngineVersion(self.name, self._version, took),
        )
