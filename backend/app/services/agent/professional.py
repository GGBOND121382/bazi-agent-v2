"""Professional analysis planning and reflection helpers."""
from __future__ import annotations

from typing import Any

from ...api.dto import ChartResultDTO, StructuredAnalysisDTO

PROFESSIONAL_RUBRIC: dict[str, Any] = {
    "dimensions": [
        "month_command_and_wang_xiang_xiu_qiu_si",
        "day_master_strength_with_support_and_counterevidence",
        "hidden_stems_roots_exposure_and_ten_gods",
        "climate_adjustment_and_element_flow",
        "stem_branch_relations_and_transformation_conditions",
        "pattern_candidates_success_failure_and_rescue",
        "useful_assistant_favorable_unfavorable_enemy_gods",
        "nayin_as_secondary_check",
        "shensha_weighted_by_structure_and_position",
        "dayun_liunian_liuyue_liuri_hierarchy",
        "user_focus_with_timing_and_conditions",
    ],
    "minimum_expectations": {
        "reasoning_summary_steps": 8,
        "include_counterevidence": True,
        "distinguish_fact_and_interpretation": True,
        "never_recalculate_chart": True,
        "never_treat_seen_combination_as_transformed": True,
        "never_select_useful_god_by_missing_element_only": True,
        "never_let_shensha_override_structure": True,
    },
}


def balanced_queries(
    chart: ChartResultDTO,
    relations: list[dict[str, Any]],
    shensha: list[dict[str, Any]],
    user_focus: tuple[str, ...],
) -> tuple[str, ...]:
    month = next(item for item in chart.pillars if item.position == "month")
    core = (
        f"{chart.day_master}日主生{month.branch}月 旺相休囚死 得令得地得势",
        f"{chart.day_master}日主 藏干透干通根 十神清杂",
        f"{chart.day_master}日主 调候扶抑病药通关 用神相神喜忌",
        f"{month.ganzhi}月令 格局成败破格救应 从格排除条件",
        "天干地支合会冲刑害破 成局化气争合妒合条件",
        "大运流年流月流日 十神喜用 应期层级",
        "纳音五行在子平命理中的辅助用法",
    )
    relation_queries = tuple(str(item["support_query"]) for item in relations[:8])
    names = tuple(
        dict.fromkeys(
            str(item.get("name", "")).strip()
            for item in shensha
            if str(item.get("name", "")).strip()
        )
    )
    shensha_queries = tuple(f"{name} 柱位 喜忌 查法" for name in names[:6])
    # User intent is first so strict citation validation cannot be starved by
    # broad structural or auxiliary-marker queries.
    return tuple(dict.fromkeys(user_focus + core + relation_queries + shensha_queries))


def reflection_requires_revision(analysis: StructuredAnalysisDTO) -> bool:
    if analysis.reflection is None:
        return True
    return analysis.reflection.status == "revise"


def reflection_feedback(analysis: StructuredAnalysisDTO) -> dict[str, Any]:
    if analysis.reflection is not None:
        return analysis.reflection.model_dump(mode="json")
    return {
        "status": "revise",
        "missing_dimensions": ["reflection_self_check"],
        "revision_instructions": ["按 professional_rubric 完成专业覆盖与自检后重写。"],
    }
