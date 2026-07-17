"""Domain ChartResult → API/view-model DTO mappers."""
from __future__ import annotations

from typing import Any, cast

from ..api.dto import (
    ChartOverviewViewDTO,
    ChartResultDTO,
    EngineVersionDTO,
    FactDTO,
    PillarDTO,
    PillarViewDTO,
    WarningDTO,
)
from ..domain.chart import ChartResult
from ..domain.rules import evaluate_relations, evaluate_shensha

_RELATION_LABELS = {
    "stem_combination": "天干五合",
    "stem_clash": "天干相冲",
    "six_combination": "六合",
    "three_combination": "三合",
    "half_combination": "半合",
    "three_meeting": "三会",
    "half_meeting": "半会",
    "clash": "六冲",
    "harm": "六害",
    "break": "相破",
    "punishment": "相刑",
}
_ELEMENT_LABELS = {
    "wood": "木",
    "fire": "火",
    "earth": "土",
    "metal": "金",
    "water": "水",
}


def _enriched_details(result: ChartResult) -> dict[str, object]:
    """Return API details with the authoritative v2 神煞 result attached.

    Calendar adapters remain focused on calendar-library values. This mapper
    overlays the versioned project rule engine so every public API consumer,
    including the LLM pipeline, sees the same per-pillar names and provenance.
    """
    details = dict(result.details)
    hits = evaluate_shensha(result.pillars)
    raw_pillars = details.get("pillars")
    enriched_pillars: list[dict[str, object]] = []
    if isinstance(raw_pillars, list):
        for raw in raw_pillars:
            if not isinstance(raw, dict):
                continue
            item = dict(cast(dict[str, object], raw))
            position = str(item.get("position", ""))
            item["shensha"] = [hit.name for hit in hits if hit.target_position == position]
            enriched_pillars.append(item)
    details["pillars"] = enriched_pillars
    details["shensha"] = [
        {
            "name": hit.name,
            "target": hit.target,
            "target_position": hit.target_position,
            "anchor": hit.anchor,
            "reference": hit.reference,
            "rule_id": hit.rule_id,
            "rule_version": hit.rule_version,
            "source_title": hit.source_title,
            "source_locator": hit.source_locator,
        }
        for hit in hits
    ]
    return details


def to_chart_result_dto(result: ChartResult) -> ChartResultDTO:
    pillars = [
        PillarDTO(
            position=p["position"],
            ganzhi=p["ganzhi"],
            stem=p["stem"],
            branch=p["branch"],
            nayin=p.get("nayin"),
            hidden_stems=p.get("hidden_stems"),
            ten_god_of_stem=p.get("ten_god_of_stem"),
        )
        for p in result.pillar_dicts()
    ]
    return ChartResultDTO(
        schema_version="chart-result-v1",
        chart_id=result.chart_id,
        calculation_status=result.calculation_status,
        calculation_profile_id=result.calculation_profile_id,
        normalized_time={
            "utc": result.normalized_utc.isoformat(),
            "calculation_time": result.calculation_time.isoformat(),
            "time_basis": result.time_basis,
        },
        calendar={
            "engine_versions": [
                {"engine": e.engine, "version": e.version, "took_ms": e.took_ms}
                for e in result.engine_versions
            ],
            "deterministic_details": _enriched_details(result),
        },
        pillars=pillars,
        day_master=result.day_master,
        facts=[
            FactDTO(
                fact_id=f.fact_id,
                fact_type=f.fact_type,
                value=f.value,
                rule_id=f.rule_id,
                inputs=list(f.inputs),
            )
            for f in result.facts
        ],
        engine_versions=[
            EngineVersionDTO(engine=e.engine, version=e.version, took_ms=e.took_ms)
            for e in result.engine_versions
        ],
        warnings=[
            WarningDTO(severity=w.severity, code=w.code, message=w.message) for w in result.warnings
        ],
        qiyun=result.qiyun,
        dayun=list(result.dayun) or None,
    )


def _detail_pillars(details: dict[str, object]) -> dict[str, dict[str, Any]]:
    raw = details.get("pillars")
    if not isinstance(raw, list):
        return {}
    return {
        str(item.get("position")): cast(dict[str, Any], item)
        for item in raw
        if isinstance(item, dict) and item.get("position")
    }


def to_chart_overview_view_dto(result: ChartResult) -> ChartOverviewViewDTO:
    fact_ids_by_value: dict[str, list[str]] = {}
    for fact in result.facts:
        fact_ids_by_value.setdefault(str(fact.value), []).append(fact.fact_id)
    details = _enriched_details(result)
    detail_by_position = _detail_pillars(details)
    pillars = []
    for p in result.pillar_dicts():
        detail = detail_by_position.get(str(p["position"]), {})
        pillars.append(
            PillarViewDTO(
                position=p["position"],
                stem=p["stem"],
                branch=p["branch"],
                ten_god=str(detail.get("major_star") or p.get("ten_god_of_stem") or "") or None,
                hidden_stems=cast(
                    list[dict[str, Any]],
                    detail.get("hidden_stems") or p.get("hidden_stems") or [],
                ),
                nayin=str(detail.get("nayin") or p.get("nayin") or "") or None,
                growth_stage=str(detail.get("growth_stage") or "") or None,
                fact_ids=fact_ids_by_value.get(p["ganzhi"], []),
            )
        )
    relationships = [
        {
            "type": relation.type,
            "label": _RELATION_LABELS.get(relation.type, relation.type),
            "participants": list(relation.branches),
            "element": _ELEMENT_LABELS.get(relation.element or "", relation.element),
            "rule_id": relation.rule_id,
        }
        for relation in evaluate_relations(result.pillars)
    ]
    five_elements_raw = details.get("five_elements")
    five_elements = (
        cast(list[dict[str, Any]], five_elements_raw)
        if isinstance(five_elements_raw, list)
        else []
    )
    return ChartOverviewViewDTO(
        chart_id=result.chart_id,
        display_name="命盘",
        status="calculated" if result.calculation_status == "passed" else "needs_review",
        pillars=pillars,
        assumptions=[
            {"label": "计算口径", "value": result.calculation_profile_id},
            {"label": "排盘时间（当地钟表）", "value": result.calculation_time.isoformat()},
            {"label": "UTC 标准时间", "value": result.normalized_utc.isoformat()},
            {"label": "时间口径", "value": result.time_basis},
        ],
        warnings=[{"severity": item.severity, "message": item.message} for item in result.warnings],
        relationships=relationships,
        five_elements=five_elements,
    )
