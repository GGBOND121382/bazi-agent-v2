"""Chart service — orchestrates the B1/B2 calculation with storage and time normalization.

This is the single point where a BirthRequest becomes a StoredChart. All API
routes for `/v1/charts` go through here. RAG/LLM never call this; they only
read stored charts.
"""
from __future__ import annotations

import logging
import uuid
from typing import cast

from ..adapters.storage import ChartStore, InMemoryChartStore
from ..adapters.time import normalize
from ..api.dto import BirthRequest, ChartResultDTO, TemporalContextViewDTO
from ..domain.chart import ChartResult
from ..domain.errors import InvalidInputError, ProfileError
from ..domain.pillars import Branch, Pillar, Stem
from ..domain.profile import CalculationProfile, load_profile
from ..domain.rules import compute_liuyun
from ..domain.rules.qiyun_dayun import DayunPeriod
from ..domain.time import NormalizedTime
from .calculate_chart import CalculationDeps, calculate_chart_from_normalized, default_deps
from .viewmodel_mapper import to_chart_result_dto

logger = logging.getLogger(__name__)


class ChartService:
    def __init__(
        self,
        *,
        store: ChartStore | None = None,
        deps: CalculationDeps | None = None,
    ) -> None:
        self.store = store or InMemoryChartStore()
        self.deps = deps or default_deps()

    def create_chart(
        self,
        *,
        request: BirthRequest,
        idempotency_key: str,
        chart_id: str | None = None,
        profile: CalculationProfile | None = None,
    ) -> tuple[ChartResultDTO, str, bool]:
        """Idempotent create. Returns (dto, chart_id, created_now)."""
        # Idempotency: return existing chart if the key was used before.
        existing = self.store.find_by_idempotency_key(idempotency_key)
        if existing:
            return to_chart_result_dto(existing.chart), existing.chart_id, False

        # Validate profile_id
        profile = profile or load_profile()
        if request.calculation_profile_id != profile.profile_id:
            raise ProfileError(
                f"calculation_profile_id {request.calculation_profile_id!r} does not match active profile",
                safe_details={"active": profile.profile_id, "requested": request.calculation_profile_id},
            )

        # Normalize time → UTC for deterministic calculation
        nt = self._normalize_time(request, profile)

        # Run deterministic calculation
        chart_id = chart_id or f"chart_{uuid.uuid4().hex[:12]}"
        result: ChartResult = calculate_chart_from_normalized(
            nt=nt,
            profile=profile,
            deps=self.deps,
            chart_id=chart_id,
            gender=request.gender,
        )
        # Override the result's chart_id in case calculate generated a new one
        result = ChartResult(
            chart_id=chart_id,
            calculation_status=result.calculation_status,
            calculation_profile_id=result.calculation_profile_id,
            normalized_utc=result.normalized_utc,
            calculation_time=result.calculation_time,
            time_basis=result.time_basis,
            pillars=result.pillars,
            facts=result.facts,
            engine_versions=result.engine_versions,
            warnings=result.warnings,
            qiyun=result.qiyun,
            dayun=result.dayun,
        )

        # Persist
        self.store.save(result)
        self.store.remember_idempotency_key(idempotency_key, chart_id)
        return to_chart_result_dto(result), chart_id, True

    def get_chart(self, chart_id: str) -> ChartResultDTO:
        stored = self.store.get(chart_id)
        if not stored or stored.deleted:
            raise InvalidInputError(f"chart not found: {chart_id}")
        return to_chart_result_dto(stored.chart)

    def list_charts(self) -> list[str]:
        return [s.chart_id for s in self.store.list_for_owner("anonymous")]

    def delete_chart(self, chart_id: str) -> bool:
        return self.store.delete(chart_id)

    def get_chart_result(self, chart_id: str) -> ChartResult:
        stored = self.store.get(chart_id)
        if not stored or stored.deleted:
            raise InvalidInputError(f"chart not found: {chart_id}")
        return stored.chart

    def set_note(self, chart_id: str, note: str) -> None:
        if len(note) > 500:
            raise InvalidInputError("note is too long")
        if self.store.set_note(chart_id, note) is None:
            raise InvalidInputError("chart not found")

    def get_temporal_context(self, chart_id: str, target_year: int) -> TemporalContextViewDTO:
        if target_year < 1900 or target_year > 2200:
            raise InvalidInputError("target year is outside the supported range")
        chart = self.get_chart_result(chart_id)
        if chart.calculation_status != "passed" or not chart.qiyun or not chart.dayun:
            raise InvalidInputError("temporal context requires a validated chart with dayun")
        periods = tuple(
            DayunPeriod(
                index=int(cast(str | int, item["index"])),
                start_age=int(cast(str | int, item["start_age"])),
                end_age=int(cast(str | int, item["end_age"])),
                ganzhi=str(item["ganzhi"]),
                pillar=Pillar(Stem(str(item["ganzhi"])[0]), Branch(str(item["ganzhi"])[1])),
            )
            for item in chart.dayun
        )
        context = compute_liuyun(
            natal=chart.pillars,
            qiyun_start_age_years=int(cast(str | int, chart.qiyun["start_age_years"])),
            dayun_periods=periods,
            target_year=target_year,
            birth_year=chart.normalized_utc.year,
        )
        active = next(
            (item for item in chart.dayun if context.active_dayun and item["index"] == context.active_dayun.index),
            None,
        )
        year_fact_id = f"LIUNIAN-{target_year}"
        year = {
            "ganzhi": context.year_pillar.ganzhi,
            "stem": context.year_pillar.stem.char,
            "branch": context.year_pillar.branch.char,
            "fact_id": year_fact_id,
            "rule_id": "LIUNIAN-CALENDAR-V1",
        }
        months = [
            {
                "index": index,
                "label": f"节气月 {index}",
                "ganzhi": pillar.ganzhi,
                "stem": pillar.stem.char,
                "branch": pillar.branch.char,
                "fact_id": f"LIUYUE-{target_year}-{index:02d}",
                "rule_id": "LIUYUE-JIEQI-V1",
            }
            for index, pillar in enumerate(context.month_pillars, start=1)
        ]
        breadcrumb = [
            {"level": "natal", "label": "原局", "ganzhi": chart.pillars.day.ganzhi},
            {"level": "dayun", "label": "大运", "ganzhi": active["ganzhi"] if active else None},
            {"level": "year", "label": "流年", "ganzhi": context.year_pillar.ganzhi},
        ]
        return TemporalContextViewDTO(
            chart_id=chart_id,
            target_year=target_year,
            breadcrumb=breadcrumb,
            active_dayun=active,
            year=year,
            months=months,
        )

    @staticmethod
    def _normalize_time(request: BirthRequest, profile: CalculationProfile) -> NormalizedTime:
        # If the request's birth_datetime_local is naive, attach the requested
        # timezone before normalizing. (The schema accepts both naive + IANA
        # name and offset-aware; we collapse to the latter before normalize().)
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        from ..domain.errors import TimeError

        local_dt = request.birth_datetime_local
        if local_dt.tzinfo is None:
            try:
                tz = ZoneInfo(request.timezone)
            except ZoneInfoNotFoundError as e:
                raise TimeError(
                    f"unknown timezone: {request.timezone}",
                    safe_details={"hint": "use IANA name like Asia/Shanghai"},
                ) from e
            local_dt = local_dt.replace(tzinfo=tz)
        return normalize(
            local_dt=local_dt,
            timezone_name=request.timezone,
            fold=request.fold,
            profile=profile,
            longitude=request.birthplace.longitude,
        )


_DEFAULT_SERVICE = ChartService()


def get_default_service() -> ChartService:
    return _DEFAULT_SERVICE
