"""Chart service — orchestrates deterministic calculation with storage and time normalization.

This is the single point where a BirthRequest becomes a StoredChart. All API
routes for `/v1/charts` go through here. RAG/LLM only read stored chart facts.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import date

from ..adapters.storage import ChartStore, InMemoryChartStore, SQLiteChartStore
from ..adapters.time import normalize
from ..api.dto import BirthRequest, ChartResultDTO, TemporalContextViewDTO
from ..domain.chart import ChartResult
from ..domain.errors import InvalidInputError, ProfileError
from ..domain.profile import CalculationProfile, load_profile
from ..domain.rules.temporal import build_temporal_context, compute_exact_yun
from ..domain.time import NormalizedTime
from .calculate_chart import CalculationDeps, calculate_chart_from_normalized, default_deps
from .viewmodel_mapper import to_chart_result_dto

logger = logging.getLogger(__name__)

_KUA = {
    1: ("坎卦", "东四命"),
    2: ("坤卦", "西四命"),
    3: ("震卦", "东四命"),
    4: ("巽卦", "东四命"),
    6: ("乾卦", "西四命"),
    7: ("兑卦", "西四命"),
    8: ("艮卦", "西四命"),
    9: ("离卦", "东四命"),
}


def _digit_root(value: int) -> int:
    result = abs(value)
    while result > 9:
        result = sum(int(char) for char in str(result))
    return result or 9


def _kua_number(year: int, gender: str) -> int:
    seed = _digit_root(year % 100)
    if year >= 2000:
        number = _digit_root(9 - seed) if gender == "male" else _digit_root(seed + 6)
    else:
        number = _digit_root(10 - seed) if gender == "male" else _digit_root(seed + 5)
    if number == 5:
        return 2 if gender == "male" else 8
    return number


def _ming_gua(year: int, gender: str) -> str:
    def label(resolved_gender: str) -> str:
        name, group = _KUA[_kua_number(year, resolved_gender)]
        return f"{name}（{group}）"

    if gender in {"male", "female"}:
        return label(gender)
    return f"男命：{label('male')}；女命：{label('female')}"


def _with_exact_yun(chart: ChartResult) -> ChartResult:
    """Upgrade persisted v1 rounded Yun data on read without a destructive migration."""
    qiyun = chart.qiyun or {}
    if qiyun.get("rule_id") == "QIYUN-LUNAR-PYTHON-SECT2-V2":
        return chart
    raw_basic = chart.details.get("basic")
    basic = raw_basic if isinstance(raw_basic, dict) else {}
    gender = str(basic.get("gender", "unspecified"))
    try:
        exact_qiyun, exact_dayun = compute_exact_yun(chart.calculation_time, gender=gender)
    except (TypeError, ValueError):
        return chart
    reference = qiyun.get("reference_jie_utc")
    if reference:
        exact_qiyun["reference_jie_utc"] = reference
    return replace(chart, qiyun=exact_qiyun, dayun=tuple(exact_dayun))


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
        owner_id: str = "anonymous",
    ) -> tuple[ChartResultDTO, str, bool]:
        """Idempotent create. Returns (dto, chart_id, created_now)."""
        existing = self.store.find_by_idempotency_key(idempotency_key)
        if existing:
            return to_chart_result_dto(_with_exact_yun(existing.chart)), existing.chart_id, False

        profile = profile or load_profile()
        if request.calculation_profile_id != profile.profile_id:
            raise ProfileError(
                f"calculation_profile_id {request.calculation_profile_id!r} does not match active profile",
                safe_details={"active": profile.profile_id, "requested": request.calculation_profile_id},
            )

        nt = self._normalize_time(request, profile)
        chart_id = chart_id or f"chart_{uuid.uuid4().hex[:12]}"
        calculated = calculate_chart_from_normalized(
            nt=nt,
            profile=profile,
            deps=self.deps,
            chart_id=chart_id,
            gender=request.gender,
        )

        details = dict(calculated.details)
        basic_source = details.get("basic")
        basic = dict(basic_source) if isinstance(basic_source, dict) else {}
        basic.update(
            {
                "gender": request.gender,
                "birth_datetime_local": request.birth_datetime_local.isoformat(),
                "timezone": request.timezone,
                "time_precision": request.time_precision,
                "time_basis": calculated.time_basis,
                "civil_time": nt.local_civil.isoformat(),
                "local_mean_solar_time": (
                    nt.local_mean_solar.isoformat() if nt.local_mean_solar is not None else None
                ),
                "true_solar_time": nt.true_solar.isoformat() if nt.true_solar is not None else None,
                "calculation_time": calculated.calculation_time.isoformat(),
                "birthplace": request.birthplace.model_dump(exclude_none=True),
                "ming_gua": _ming_gua(request.birth_datetime_local.year, request.gender),
            }
        )
        details["basic"] = basic

        result = ChartResult(
            chart_id=chart_id,
            calculation_status=calculated.calculation_status,
            calculation_profile_id=calculated.calculation_profile_id,
            normalized_utc=calculated.normalized_utc,
            calculation_time=calculated.calculation_time,
            time_basis=calculated.time_basis,
            pillars=calculated.pillars,
            facts=calculated.facts,
            engine_versions=calculated.engine_versions,
            warnings=calculated.warnings,
            qiyun=calculated.qiyun,
            dayun=calculated.dayun,
            details=details,
        )

        self.store.save(result, owner_id=owner_id)
        self.store.remember_idempotency_key(idempotency_key, chart_id)
        return to_chart_result_dto(result), chart_id, True

    def get_chart(self, chart_id: str) -> ChartResultDTO:
        stored = self.store.get(chart_id)
        if not stored or stored.deleted:
            raise InvalidInputError(f"chart not found: {chart_id}")
        return to_chart_result_dto(_with_exact_yun(stored.chart))

    def list_charts(self, owner_id: str = "anonymous") -> list[str]:
        return [s.chart_id for s in self.store.list_for_owner(owner_id)]

    def delete_chart(self, chart_id: str) -> bool:
        return self.store.delete(chart_id)

    def get_chart_result(self, chart_id: str) -> ChartResult:
        stored = self.store.get(chart_id)
        if not stored or stored.deleted:
            raise InvalidInputError(f"chart not found: {chart_id}")
        return _with_exact_yun(stored.chart)

    def set_note(self, chart_id: str, note: str) -> None:
        if len(note) > 500:
            raise InvalidInputError("note is too long")
        if self.store.set_note(chart_id, note) is None:
            raise InvalidInputError("chart not found")

    def get_temporal_context(
        self,
        chart_id: str,
        target_year: int,
        target_date: date | None = None,
    ) -> TemporalContextViewDTO:
        if target_year < 1900 or target_year > 2200:
            raise InvalidInputError("target year is outside the supported range")
        if target_date is not None and target_date.year != target_year:
            raise InvalidInputError("target_date must fall inside target_year")
        chart = self.get_chart_result(chart_id)
        if chart.calculation_status != "passed":
            raise InvalidInputError("temporal context requires a validated chart")
        basic_source = chart.details.get("basic")
        basic = basic_source if isinstance(basic_source, dict) else {}
        gender = str(basic.get("gender", "unspecified"))
        try:
            context = build_temporal_context(
                chart.pillars,
                chart.calculation_time,
                gender=gender,
                target_year=target_year,
                target_date=target_date,
            )
        except (TypeError, ValueError) as exc:
            raise InvalidInputError(
                "unable to calculate exact temporal context",
                safe_details={"reason": str(exc)},
            ) from exc
        active = context.get("active_dayun")
        active_ganzhi = active.get("ganzhi") if isinstance(active, dict) else None
        year = context["year"]
        assert isinstance(year, dict)
        breadcrumb = [
            {"level": "natal", "label": "原局", "ganzhi": chart.pillars.day.ganzhi},
            {"level": "dayun", "label": "大运", "ganzhi": active_ganzhi},
            {"level": "year", "label": "流年", "ganzhi": year.get("ganzhi")},
        ]
        return TemporalContextViewDTO(
            chart_id=chart_id,
            target_year=target_year,
            breadcrumb=breadcrumb,
            qiyun=context.get("qiyun"),
            dayuns=context.get("dayuns", []),
            active_dayun=active if isinstance(active, dict) else None,
            year=year,
            months=context.get("months", []),
            selected_month=context.get("selected_month"),
            selected_day=context.get("selected_day"),
            interactions=context.get("interactions", []),
            interaction_summary=context.get("interaction_summary", {}),
            seasonal_strength=context.get("seasonal_strength", {}),
        )

    @staticmethod
    def _normalize_time(request: BirthRequest, profile: CalculationProfile) -> NormalizedTime:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        from ..domain.errors import TimeError

        local_dt = request.birth_datetime_local
        if local_dt.tzinfo is None:
            try:
                tz = ZoneInfo(request.timezone)
            except ZoneInfoNotFoundError as exc:
                raise TimeError(
                    f"unknown timezone: {request.timezone}",
                    safe_details={"hint": "use IANA name like Asia/Shanghai"},
                ) from exc
            local_dt = local_dt.replace(tzinfo=tz)
        return normalize(
            local_dt=local_dt,
            timezone_name=request.timezone,
            fold=request.fold,
            profile=profile,
            longitude=request.birthplace.longitude,
        )


_DEFAULT_SERVICE = ChartService(store=SQLiteChartStore())


def get_default_service() -> ChartService:
    return _DEFAULT_SERVICE
