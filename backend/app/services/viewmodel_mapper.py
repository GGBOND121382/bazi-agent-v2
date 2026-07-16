"""Domain ChartResult → ChartResultDTO mapper.

The mapper is the only place where domain objects become wire-format DTOs.
Any change to this file should be matched by a corresponding update in
contracts/schemas/json_schema/chart_result.schema.json (or its view schemas).
"""
from __future__ import annotations

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


def to_chart_overview_view_dto(result: ChartResult) -> ChartOverviewViewDTO:
    fact_ids_by_value: dict[str, list[str]] = {}
    for fact in result.facts:
        fact_ids_by_value.setdefault(str(fact.value), []).append(fact.fact_id)
    pillars = [
        PillarViewDTO(
            position=p["position"],
            stem=p["stem"],
            branch=p["branch"],
            ten_god=p.get("ten_god_of_stem"),
            hidden_stems=p.get("hidden_stems") or [],
            nayin=p.get("nayin"),
            growth_stage=None,
            fact_ids=fact_ids_by_value.get(p["ganzhi"], []),
        )
        for p in result.pillar_dicts()
    ]
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
        relationships=[],
        five_elements=[],
    )
