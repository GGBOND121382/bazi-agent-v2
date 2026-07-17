"""Professional prompt, immutable context and reflection regressions."""
from __future__ import annotations

import json
from pathlib import Path

from app.api.dto import ChartResultDTO, EngineVersionDTO, FactDTO, PillarDTO, StructuredAnalysisDTO
from app.services.agent.context import build_analysis_context
from app.services.agent.professional import PROFESSIONAL_RUBRIC, reflection_requires_revision
from app.services.agent.prompts import INTERPRETER_SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[3]


def _chart() -> ChartResultDTO:
    return ChartResultDTO(
        chart_id="chart_professional",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={"calculation_time": "1999-06-29T12:00:00+08:00"},
        calendar={
            "deterministic_details": {
                "basic": {"ren_yuan_commander": "丁火用事"},
                "pillars": [{"position": "day", "ganzhi": "壬子"}],
                "five_elements": [{"element": "水", "total": 3}],
                "shensha": [{"name": "羊刃", "target_position": "day"}],
            }
        },
        pillars=[
            PillarDTO(position="year", ganzhi="己卯", stem="己", branch="卯", nayin="城头土"),
            PillarDTO(position="month", ganzhi="庚午", stem="庚", branch="午", nayin="路旁土"),
            PillarDTO(position="day", ganzhi="壬子", stem="壬", branch="子", nayin="桑柘木"),
            PillarDTO(position="hour", ganzhi="丙午", stem="丙", branch="午", nayin="天河水"),
        ],
        day_master="壬",
        facts=[FactDTO(fact_id="FACT-DAY", fact_type="pillar", value="壬子", rule_id="RULE-DAY", inputs=[])],
        qiyun={"start_years": 2, "start_months": 9, "start_days": 17},
        dayun=[{"ganzhi": "癸酉", "start_year": 2022, "end_year": 2031}],
        engine_versions=[EngineVersionDTO(engine="test", version="1", took_ms=0)],
        warnings=[],
    )


def test_prompt_contains_required_professional_dimensions() -> None:
    for term in (
        "旺相休囚死",
        "得令、得地、得势",
        "藏干与十神",
        "调候",
        "病药",
        "通关",
        "格局候选",
        "用神、相神、喜神、忌神、仇神",
        "纳音",
        "原局 → 当前大运 → 流年 → 流月 → 流日",
        "Reflection",
    ):
        assert term in INTERPRETER_SYSTEM_PROMPT
    assert "不得重新排盘" in INTERPRETER_SYSTEM_PROMPT
    assert "不得输出隐藏思维链" in INTERPRETER_SYSTEM_PROMPT


def test_context_contains_read_only_natal_and_temporal_facts() -> None:
    context = build_analysis_context(
        chart=_chart(),
        computed_relations=[{"fact_id": "RELATION-01", "type": "clash"}],
        computed_shensha=[{"name": "羊刃", "target_position": "day"}],
    )
    assert context["immutable"] is True
    assert context["fact_authority"] == "deterministic_engine_only"
    assert context["natal"]["pillars"][2]["ganzhi"] == "壬子"
    assert context["natal"]["relations"][0]["fact_id"] == "RELATION-01"
    assert context["temporal"]["dayun_table"][0]["ganzhi"] == "癸酉"
    assert context["model_boundary"]["must_not_recalculate_calendar_or_pillars"] is True


def test_reflection_requests_revision_when_missing_or_failed() -> None:
    base = {
        "analysis_id": "analysis_test",
        "chart_id": "chart_professional",
        "school": "engineering_policy",
        "claims": [],
        "limitations": [],
    }
    assert reflection_requires_revision(StructuredAnalysisDTO.model_validate(base)) is True
    failed = {**base, "reflection": {"status": "revise", "missing_dimensions": ["格局"]}}
    assert reflection_requires_revision(StructuredAnalysisDTO.model_validate(failed)) is True
    passed = {**base, "reflection": {"status": "pass", "checked_dimensions": ["格局"]}}
    assert reflection_requires_revision(StructuredAnalysisDTO.model_validate(passed)) is False


def test_eval_cases_cover_current_chart_and_scoring_rubric() -> None:
    payload = json.loads(
        (ROOT / "contracts/examples/professional_prompt_eval_cases.json").read_text(
            encoding="utf-8"
        )
    )
    assert sum(payload["rubric"].values()) == 100
    current = next(item for item in payload["cases"] if item["case_id"] == "female_19990629_noon")
    assert current["pillars"] == ["己卯", "庚午", "壬子", "丙午"]
    assert "reflection" in current["required_dimensions"]
    assert len(PROFESSIONAL_RUBRIC["dimensions"]) >= 10
