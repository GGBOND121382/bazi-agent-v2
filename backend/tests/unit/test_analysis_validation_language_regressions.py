"""Regression tests for deterministic-analysis validation false positives."""
from __future__ import annotations

import pytest

from app.api.dto import ChartResultDTO, EngineVersionDTO, PillarDTO, StructuredAnalysisDTO
from app.services.agent.professional_core import _substantive_items
from app.services.agent.verifier import _semantic_rule_errors


def _chart() -> ChartResultDTO:
    return ChartResultDTO(
        chart_id="chart_language_regression",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={},
        calendar={"deterministic_details": {"shensha": []}},
        pillars=[
            PillarDTO(position="year", ganzhi="甲子", stem="甲", branch="子"),
            PillarDTO(position="month", ganzhi="乙丑", stem="乙", branch="丑"),
            PillarDTO(position="day", ganzhi="丁卯", stem="丁", branch="卯"),
            PillarDTO(position="hour", ganzhi="戊辰", stem="戊", branch="辰"),
        ],
        day_master="丁",
        facts=[],
        qiyun=None,
        dayun=None,
        temporal_context=None,
        engine_versions=[EngineVersionDTO(engine="test", version="1", took_ms=0)],
        warnings=[],
    )


def _analysis_with_text(text: str) -> StructuredAnalysisDTO:
    return StructuredAnalysisDTO(
        analysis_id="analysis_language_regression",
        chart_id="chart_language_regression",
        school="engineering_policy",
        executive_summary=text,
        claims=[],
        limitations=[],
    )


def test_health_area_assessment_contract_counts_substantive_content() -> None:
    items = [
        {"area": area, "assessment": "结合原局偏性与岁运变化作条件性分析。"}
        for area in ["五行偏性", "寒暖燥湿", "传统脏腑象义", "保护因素", "大运变化", "生活建议"]
    ]
    assert _substantive_items(items) == 6


def test_health_area_label_alone_does_not_count_as_substantive_content() -> None:
    items = [{"area": area, "assessment": ""} for area in ["甲", "乙", "丙", "丁", "戊", "己"]]
    assert _substantive_items(items) == 0


@pytest.mark.parametrize(
    "text",
    [
        "乙木生申月，先看月令与司令。",
        "甲木生子月，应结合寒暖燥湿判断。",
        "丙火生申月，不能只按五行数量判断。",
        "庚金生巳月，需结合得令得地得势。",
        "壬水生午月，旺衰仍需综合判断。",
    ],
)
def test_birth_month_wording_is_not_treated_as_element_generation(text: str) -> None:
    errors, _ = _semantic_rule_errors(_chart(), _analysis_with_text(text))
    assert "INVALID_ELEMENT_RELATION" not in {item["code"] for item in errors}


def test_genuine_invalid_element_generation_is_still_rejected() -> None:
    errors, _ = _semantic_rule_errors(_chart(), _analysis_with_text("乙木生申金。"))
    assert "INVALID_ELEMENT_RELATION" in {item["code"] for item in errors}
