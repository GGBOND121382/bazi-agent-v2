"""Read-only deterministic context supplied to interpretation models.

The LLM never performs calendar conversion or chart calculation.  This module
packages the outputs of the deterministic engines into one stable, auditable
context object and marks any absent fields explicitly.
"""
from __future__ import annotations

from typing import Any

from ...api.dto import ChartResultDTO, TemporalContextViewDTO

_ANALYSIS_DIMENSIONS = (
    "月令与旺相休囚死",
    "日主得令得地得势与强弱",
    "藏干透出通根与十神配置",
    "寒暖燥湿调候与五行流通",
    "天干地支合会冲刑害破及成化条件",
    "格局候选成立破格与排除条件",
    "扶抑调候病药通关及用相喜忌仇神",
    "纳音五行辅助校验",
    "神煞在原局结构中的喜忌与权重",
    "大运流年流月流日逐层触发",
    "性格能力事业财运感情健康与应期",
)


def _details(chart: ChartResultDTO) -> dict[str, Any]:
    raw = chart.calendar.get("deterministic_details", {})
    return dict(raw) if isinstance(raw, dict) else {}


def _missing_fields(details: dict[str, Any], chart: ChartResultDTO) -> list[str]:
    checks = {
        "pillar_details": details.get("pillars"),
        "five_elements": details.get("five_elements"),
        "ren_yuan_commander": details.get("basic", {}).get("ren_yuan_commander")
        if isinstance(details.get("basic"), dict)
        else None,
        "shensha": details.get("shensha"),
        "qiyun": chart.qiyun,
        "dayun": chart.dayun,
    }
    return [name for name, value in checks.items() if value in (None, [], {}, "")]


def build_analysis_context(
    *,
    chart: ChartResultDTO,
    computed_relations: list[dict[str, Any]],
    computed_shensha: list[dict[str, Any]],
    temporal: TemporalContextViewDTO | None = None,
) -> dict[str, Any]:
    """Build the sole chart/temporal fact source for the LLM."""
    details = _details(chart)
    temporal_payload: dict[str, Any] = {
        "qiyun": chart.qiyun,
        "dayun_table": chart.dayun or [],
        "precomputed_context": chart.temporal_context or [],
    }
    if temporal is not None:
        temporal_payload.update(
            {
                "target_year": temporal.target_year,
                "breadcrumb": temporal.breadcrumb,
                "active_dayun": temporal.active_dayun,
                "liunian": temporal.year,
                "liuyue_table": temporal.months,
                "selected_liuri": temporal.selected_day,
                "seasonal_strength": temporal.seasonal_strength,
            }
        )

    return {
        "context_version": "bazi-analysis-context-v1",
        "fact_authority": "deterministic_engine_only",
        "immutable": True,
        "calculation": {
            "chart_id": chart.chart_id,
            "profile_id": chart.calculation_profile_id,
            "status": chart.calculation_status,
            "normalized_time": chart.normalized_time,
            "engine_versions": [item.model_dump(mode="json") for item in chart.engine_versions],
            "warnings": [item.model_dump(mode="json") for item in chart.warnings],
        },
        "natal": {
            "day_master": chart.day_master,
            "pillars": [item.model_dump(mode="json") for item in chart.pillars],
            "facts": [item.model_dump(mode="json") for item in chart.facts],
            "pillar_details": details.get("pillars", []),
            "basic_details": details.get("basic", {}),
            "five_elements": details.get("five_elements", []),
            "seasonal_and_command": {
                "ren_yuan_commander": (
                    details.get("basic", {}).get("ren_yuan_commander")
                    if isinstance(details.get("basic"), dict)
                    else None
                ),
                "birth_solar_terms": (
                    details.get("basic", {}).get("birth_solar_terms")
                    if isinstance(details.get("basic"), dict)
                    else None
                ),
            },
            "relations": computed_relations,
            "shensha": computed_shensha,
        },
        "temporal": temporal_payload,
        "required_analysis_dimensions": list(_ANALYSIS_DIMENSIONS),
        "missing_or_uncertain_fields": _missing_fields(details, chart),
        "model_boundary": {
            "must_not_recalculate_calendar_or_pillars": True,
            "must_not_change_ten_gods_hidden_stems_nayin_relations_or_shensha": True,
            "may_interpret_strength_pattern_useful_gods_and_timing": True,
            "must_distinguish_fact_from_school_based_interpretation": True,
        },
    }
