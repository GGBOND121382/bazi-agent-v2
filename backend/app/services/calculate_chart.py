"""Chart calculation service — orchestrates adapters to produce ChartResult.

Inputs: a normalized BirthRequest.
Outputs: a ChartResultDTO ready for the API.

Single point of entry for B1. RAG/LLM never call this; they read ChartResult.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from ..adapters.calendar import (
    CalendarAdapter,
    CrossEngineComparer,
    LunarPythonAdapter,
    ReferenceAdapter,
)
from ..domain.chart import ChartResult
from ..domain.pillars import FourPillars
from ..domain.profile import CalculationProfile, load_profile
from ..domain.rules.qiyun_dayun import compute_qiyun_and_dayun
from ..domain.time import NormalizedTime


@dataclass(frozen=True)
class CalculationDeps:
    primary: CalendarAdapter
    secondary: CalendarAdapter
    comparer: CrossEngineComparer


def default_deps() -> CalculationDeps:
    """Default dependency wiring: lunar_python (primary) + reference (secondary).

    lunar_python is the authoritative primary per the architecture doc; we try
    to attach sxtwl as the canonical 复核 engine when available, falling back
    to ReferenceAdapter when sxtwl isn't installed (e.g. Windows without MSVC).
    """
    primary: CalendarAdapter = LunarPythonAdapter()
    secondary: CalendarAdapter = ReferenceAdapter()
    try:
        from datetime import datetime as _dt

        from ..adapters.calendar import SxtwlAdapter

        probe = SxtwlAdapter()
        # Actually invoke sxtwl; this is the only thing that proves the lib is usable.
        probe.calculate(_dt(2000, 1, 1, 12, 0, tzinfo=UTC))
        secondary = probe
    except Exception:
        # sxtwl missing or unbuildable; ReferenceAdapter stays.
        pass
    return CalculationDeps(
        primary=primary,
        secondary=secondary,
        comparer=CrossEngineComparer(primary, secondary),
    )


def _qiyun_forward(pillars: FourPillars, gender: str) -> bool:
    yang = pillars.year.stem.yin_yang == "yang"
    if gender in {"male", "unspecified"}:
        return yang
    return not yang


def calculate(
    *,
    utc: datetime,
    calendar_time: datetime | None = None,
    time_basis: str = "civil_time",
    profile: CalculationProfile | None = None,
    deps: CalculationDeps | None = None,
    chart_id: str | None = None,
    gender: str = "unspecified",
) -> ChartResult:
    """Deterministic chart calculation.

    Steps:
    1. Ensure profile is loaded (default: ziping_standard_v1).
    2. Run primary adapter.
    3. Cross-check against secondary; raise CrossEngineConflictError on drift.
    4. Merge facts/warnings/engine_versions into a ChartResult.
    """
    if utc.tzinfo is None or utc.utcoffset() != UTC.utcoffset(utc):
        raise ValueError("utc must be a timezone-aware UTC datetime")
    calendar_time = calendar_time or utc
    if calendar_time.tzinfo is None:
        raise ValueError("calendar_time must be timezone-aware")
    profile = profile or load_profile()
    profile.assert_known()
    deps = deps or default_deps()

    primary = deps.primary.calculate(calendar_time)
    # Cross-check; raise on any drift (fail-closed).
    deps.comparer.assert_no_conflict(calendar_time)
    secondary = deps.secondary.calculate(calendar_time)

    pillars = primary.pillars
    merged_facts = primary.facts + secondary.facts
    merged_warnings = primary.warnings + secondary.warnings
    engines = (primary.engine_version, secondary.engine_version)
    nearest_jie = getattr(deps.primary, "nearest_jie", None)
    reference_jie_utc = (
        nearest_jie(calendar_time, forward=_qiyun_forward(pillars, gender)).astimezone(UTC)
        if callable(nearest_jie)
        else None
    )
    qiyun_result = compute_qiyun_and_dayun(
        pillars=pillars,
        birth_utc=utc,
        gender=gender,
        profile=profile,
        reference_jie_utc=reference_jie_utc,
    )
    qiyun = {
        "start_age_years": qiyun_result.start_age_years,
        "direction": qiyun_result.direction,
        "reference_jie_utc": qiyun_result.reference_jie_utc.isoformat(),
        "rule_id": "QIYUN-GENDER-YINYANG-V1",
    }
    dayun = tuple(
        {
            "index": period.index,
            "start_age": period.start_age,
            "end_age": period.end_age,
            "ganzhi": period.ganzhi,
            "fact_id": f"DAYUN-{period.index}",
            "rule_id": "DAYUN-60-CYCLE-V1",
        }
        for period in qiyun_result.dayun
    )

    return ChartResult(
        chart_id=chart_id or f"chart_{uuid.uuid4().hex[:12]}",
        calculation_status="passed",
        calculation_profile_id=profile.profile_id,
        normalized_utc=utc,
        calculation_time=calendar_time,
        time_basis=time_basis,
        pillars=pillars,
        facts=merged_facts,
        engine_versions=engines,
        warnings=merged_warnings,
        qiyun=qiyun,
        dayun=dayun,
    )


def calculate_chart_from_normalized(
    *,
    nt: NormalizedTime,
    profile: CalculationProfile | None = None,
    deps: CalculationDeps | None = None,
    chart_id: str | None = None,
    gender: str = "unspecified",
) -> ChartResult:
    return calculate(
        utc=nt.utc,
        calendar_time=nt.effective_calendar_time,
        time_basis=nt.time_basis,
        profile=profile,
        deps=deps,
        chart_id=chart_id,
        gender=gender,
    )
