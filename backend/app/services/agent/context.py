"""Compact read-only deterministic context supplied to report interpretation models.

The complete chart snapshot remains available to the application and generation logs.
This module projects only the facts needed by the model, without duplicating natal,
temporal, provenance, or audit metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from ...api.dto import ChartResultDTO, TemporalContextViewDTO
from ...domain.pillars import Branch, FourPillars, Pillar, Stem
from ...domain.rules.temporal import describe_temporal_pillar
from ..chat_context import build_natal_core, compact_relation


def _nonempty(value: object) -> bool:
    return value not in (None, "", [], {})


def _compact_hidden_stems(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stem = str(item.get("stem", "")).strip()
        if not stem:
            continue
        compact = {"stem": stem}
        ten_god = str(item.get("ten_god", "")).strip()
        if ten_god:
            compact["ten_god"] = ten_god
        result.append(compact)
    return result


def _compact_shensha(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            position = ""
            variant = ""
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            position = str(item.get("target_position", item.get("position", ""))).strip()
            variant = str(item.get("variant", "")).strip()
        else:
            continue
        if not name:
            continue
        key = (name, position)
        if key in seen:
            continue
        seen.add(key)
        compact = {"name": name}
        if position:
            compact["position"] = position
        if variant and variant != "classical_or_common":
            compact["variant"] = variant
        result.append(compact)
    return result


def _compact_relation_with_ids(raw: Mapping[str, object]) -> dict[str, object]:
    result = compact_relation(raw)
    result.pop("label", None)
    positions = result.get("positions")
    if isinstance(positions, list):
        result["positions"] = [
            f"{item.get('position', '')}:{item.get('ganzhi', '')}".strip(":")
            if isinstance(item, dict)
            else str(item)
            for item in positions
        ]
    fact_id = raw.get("fact_id")
    if _nonempty(fact_id):
        result["fact_id"] = str(fact_id)
    return result


def _compact_relations(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [
        _compact_relation_with_ids(cast(dict[str, object], item))
        for item in raw
        if isinstance(item, dict)
    ]


def _compact_temporal_item(raw: Mapping[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {}
    for key in (
        "index",
        "start_year",
        "end_year",
        "start_age",
        "end_age",
        "year",
        "civil_target_year",
        "lichun_year",
        "age",
        "date",
        "lunar_date",
        "label",
        "jie_name",
        "start_datetime",
        "end_datetime",
        "month_ganzhi",
        "ganzhi",
        "stem",
        "branch",
        "stem_ten_god",
        "branch_ten_god",
        "growth_stage",
        "self_seat",
        "nayin",
        "xunkong",
        "xiaoyun",
        "fact_id",
    ):
        value = raw.get(key)
        if _nonempty(value):
            compact[key] = value

    hidden = _compact_hidden_stems(raw.get("hidden_stems"))
    if hidden:
        compact["hidden_stems"] = hidden
    shensha = _compact_shensha(raw.get("shensha"))
    if shensha:
        compact["shensha"] = shensha
    natal_relations = _compact_relations(raw.get("relations"))
    if natal_relations:
        compact["natal_interactions"] = natal_relations
    cross_layer = _compact_relations(raw.get("temporal_interactions"))
    if cross_layer:
        compact["cross_layer_interactions"] = cross_layer
    return compact


def _compact_qiyun(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key
        in {
            "direction",
            "start_years",
            "start_months",
            "start_days",
            "start_hours",
            "start_age_years",
            "start_datetime",
            "fact_id",
        }
        and _nonempty(value)
    }


def _deduplicated_fact_catalog(chart: ChartResultDTO) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for fact in chart.facts:
        if fact.fact_id in seen:
            continue
        seen.add(fact.fact_id)
        result.append(
            {
                "fact_id": fact.fact_id,
                "fact_type": fact.fact_type,
                "value": fact.value,
            }
        )
    return result


def _chart_pillars(chart: ChartResultDTO) -> FourPillars:
    by_position = {str(item.position): item for item in chart.pillars}

    def build(position: Literal["year", "month", "day", "hour"]) -> Pillar:
        item = by_position[position]
        return Pillar(Stem(item.stem), Branch(item.branch))

    return FourPillars(
        year=build("year"),
        month=build("month"),
        day=build("day"),
        hour=build("hour"),
    )


def _enriched_dayun_sequence(
    chart: ChartResultDTO, natal_core: Mapping[str, object]
) -> list[dict[str, object]]:
    basic = natal_core.get("basic")
    gender = str(basic.get("gender", "unspecified")) if isinstance(basic, dict) else "unspecified"
    natal = _chart_pillars(chart)
    result: list[dict[str, object]] = []
    for raw in chart.dayun or []:
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, object], raw)
        ganzhi = str(item.get("ganzhi", ""))
        if len(ganzhi) == 2:
            enriched = describe_temporal_pillar(
                natal,
                Pillar(Stem(ganzhi[0]), Branch(ganzhi[1])),
                scope="dayun",
                gender=gender,
            )
            item = {**item, **enriched}
        result.append(_compact_temporal_item(item))
    return result


def _missing_fields(chart: ChartResultDTO, natal_core: Mapping[str, object]) -> list[str]:
    basic = natal_core.get("basic")
    commander = basic.get("ren_yuan_commander") if isinstance(basic, dict) else None
    checks = {
        "pillar_details": natal_core.get("pillars"),
        "five_elements": natal_core.get("five_elements"),
        "ren_yuan_commander": commander,
        "shensha": natal_core.get("shensha"),
        "qiyun": chart.qiyun,
        "dayun": chart.dayun,
    }
    return [name for name, value in checks.items() if not _nonempty(value)]


def build_analysis_context(
    *,
    chart: ChartResultDTO,
    computed_relations: list[dict[str, Any]],
    computed_shensha: list[dict[str, Any]],
    temporal: TemporalContextViewDTO | None = None,
) -> dict[str, Any]:
    """Build a compact fact projection for a full professional report.

    The hierarchy is never truncated: natal, qiyun, and every deterministic dayun
    remain available.  What is removed is duplicate display/audit metadata.
    """
    seasonal_strength = temporal.seasonal_strength if temporal is not None else {}
    natal_core = build_natal_core(chart, seasonal_strength=seasonal_strength)
    # Prefer the caller-supplied deterministic catalog because it carries stable IDs.
    natal_core["natal_relations"] = [
        _compact_relation_with_ids(item) for item in computed_relations
    ]
    natal_core["shensha"] = _compact_shensha(computed_shensha)

    temporal_hierarchy: dict[str, object] = {
        "hierarchy": "natal>qiyun>dayun>liunian>liuyue>liuri",
        "qiyun": _compact_qiyun(chart.qiyun),
        "dayun_sequence": _enriched_dayun_sequence(chart, natal_core),
    }
    precomputed = [
        _compact_temporal_item(cast(dict[str, object], item))
        for item in (chart.temporal_context or [])
        if isinstance(item, dict)
    ]
    if precomputed:
        temporal_hierarchy["precomputed_context"] = precomputed
    if temporal is not None:
        if temporal.active_dayun:
            temporal_hierarchy["active_dayun"] = _compact_temporal_item(temporal.active_dayun)
        temporal_hierarchy["target_liunian"] = _compact_temporal_item(temporal.year)
        temporal_hierarchy["liuyue_sequence"] = [
            _compact_temporal_item(item) for item in temporal.months
        ]
        if temporal.selected_month:
            temporal_hierarchy["selected_liuyue"] = _compact_temporal_item(temporal.selected_month)
        if temporal.selected_day:
            temporal_hierarchy["selected_liuri"] = _compact_temporal_item(temporal.selected_day)

    return {
        "context_version": "bazi-analysis-context-v4-compact",
        "context_policy": "deterministic_read_only",
        "natal_core": natal_core,
        "fact_catalog": _deduplicated_fact_catalog(chart),
        "temporal_hierarchy": temporal_hierarchy,
        "missing_or_uncertain_fields": _missing_fields(chart, natal_core),
    }
