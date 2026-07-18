"""Regressions for deterministic temporal references and no-RAG validation."""
from __future__ import annotations

from typing import Any

from app.adapters.llm import ProviderResponse
from app.api.dto import ChartResultDTO, EngineVersionDTO, FactDTO, PillarDTO, StructuredAnalysisDTO
from app.services.agent import AnalysisPipeline, verify_analysis
from app.services.agent.context import build_analysis_context
from app.services.agent.professional_core import _enforce_core_topic_coverage, _relations


def _chart() -> ChartResultDTO:
    return ChartResultDTO(
        chart_id="chart_temporal_validation",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={"utc": "1995-12-22T07:00:00Z"},
        calendar={
            "deterministic_details": {
                "basic": {"gender": "male"},
                "pillars": [
                    {
                        "position": "year",
                        "ganzhi": "乙亥",
                        "stem": "乙",
                        "branch": "亥",
                        "major_star": "偏印",
                        "hidden_stems": [
                            {"stem": "壬", "ten_god": "正官"},
                            {"stem": "甲", "ten_god": "正印"},
                        ],
                    },
                    {
                        "position": "month",
                        "ganzhi": "戊子",
                        "stem": "戊",
                        "branch": "子",
                        "major_star": "伤官",
                        "hidden_stems": [{"stem": "癸", "ten_god": "七杀"}],
                    },
                    {
                        "position": "day",
                        "ganzhi": "丁亥",
                        "stem": "丁",
                        "branch": "亥",
                        "major_star": "日主",
                        "hidden_stems": [
                            {"stem": "壬", "ten_god": "正官"},
                            {"stem": "甲", "ten_god": "正印"},
                        ],
                    },
                    {
                        "position": "hour",
                        "ganzhi": "戊申",
                        "stem": "戊",
                        "branch": "申",
                        "major_star": "伤官",
                        "hidden_stems": [
                            {"stem": "庚", "ten_god": "正财"},
                            {"stem": "壬", "ten_god": "正官"},
                            {"stem": "戊", "ten_god": "伤官"},
                        ],
                    },
                ],
            }
        },
        pillars=[
            PillarDTO(position="year", ganzhi="乙亥", stem="乙", branch="亥"),
            PillarDTO(position="month", ganzhi="戊子", stem="戊", branch="子"),
            PillarDTO(position="day", ganzhi="丁亥", stem="丁", branch="亥"),
            PillarDTO(position="hour", ganzhi="戊申", stem="戊", branch="申"),
        ],
        day_master="丁",
        facts=[
            FactDTO(
                fact_id="FACT-DM-1",
                fact_type="day_master",
                value="丁",
                rule_id="RULE-DAY-MASTER",
                inputs=["丁"],
            )
        ],
        qiyun={
            "direction": "forward",
            "start_years": 5,
            "rule_id": "QIYUN-LUNAR-PYTHON-SECT2-V2",
        },
        dayun=[
            {
                "index": 3,
                "start_year": 2020,
                "end_year": 2029,
                "start_age": 26,
                "end_age": 35,
                "ganzhi": "乙酉",
                "fact_id": "DAYUN-3",
                "rule_id": "DAYUN-LUNAR-PYTHON-V2",
            }
        ],
        temporal_context=[
            {
                "ganzhi": "丙午",
                "year": 2026,
                "fact_id": "LIUNIAN-2026",
                "rule_id": "LIUNIAN-LICHUN-V2",
            }
        ],
        engine_versions=[EngineVersionDTO(engine="test", version="1", took_ms=0)],
        warnings=[],
    )


def _analysis(
    *,
    school: str = "engineering_policy",
    claim_school: str | None = None,
    fact_ids: list[str] | None = None,
    rule_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
) -> StructuredAnalysisDTO:
    return StructuredAnalysisDTO.model_validate(
        {
            "analysis_id": "analysis_temporal_validation",
            "chart_id": "chart_temporal_validation",
            "school": school,
            "kinship_assessment": [
                {"relation": name, "conclusion": "结合六亲星、宫位和岁运分析。"}
                for name in ["父亲", "母亲", "兄弟姐妹", "配偶婚恋", "子女", "家庭互动"]
            ],
            "health_assessment": [
                {"dimension": name, "conclusion": "结合原局偏性和岁运变化分析。"}
                for name in ["五行偏性", "寒暖燥湿", "传统脏腑", "保护因素", "大运变化", "生活建议"]
            ],
            "dayun_assessment": [
                {"stage": "出生至起运", "conclusion": "说明起运前阶段。"},
                {
                    "stage": "乙酉大运（2020—2029）",
                    "fact_ids": ["DAYUN-3"],
                    "conclusion": "结构、事业、财运、感情六亲、健康及承接均按条件分析。",
                },
            ],
            "claims": [
                {
                    "claim_id": "C001",
                    "topic": "大运",
                    "statement": "乙酉大运是当前阶段分析所引用的确定性时间事实。",
                    "fact_ids": fact_ids or ["DAYUN-3"],
                    "rule_ids": rule_ids if rule_ids is not None else ["DAYUN-LUNAR-PYTHON-V2"],
                    "evidence_ids": evidence_ids or [],
                    "counterevidence": [],
                    "confidence": 0.7,
                    "temporal_scope": "dayun",
                    "school": claim_school,
                }
            ],
            "limitations": [],
        }
    )


class _SchoolRepairProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        payload = kwargs["input_payload"]
        self.calls.append(payload)
        if len(self.calls) == 1:
            analysis = _analysis(
                school="ziping_structure_first",
                claim_school="ziping_structure_first",
            )
        else:
            assert payload["analysis_profile"]["school"] == "engineering_policy"
            assert "evidence_ids empty" in payload["output_contract"]["claim_references"]
            assert "retrieval_context" not in payload
            analysis = _analysis()
        return ProviderResponse(
            payload=analysis.model_dump(mode="json"),
            model_id="mock-school-repair",
            prompt_version=kwargs["prompt_version"],
        )


def test_verifier_accepts_model_visible_dayun_and_temporal_ids() -> None:
    result = verify_analysis(
        chart=_chart(), evidence=(), analysis=_analysis(), configured_school="engineering_policy"
    )
    assert result.status == "passed"


def test_verifier_still_rejects_unknown_temporal_ids() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis(
            fact_ids=["DAYUN-404"],
            rule_ids=["DAYUN-INVENTED-V9"],
        ),
        configured_school="engineering_policy",
    )
    codes = {error["code"] for error in result.errors}
    assert result.status == "failed"
    assert {"UNKNOWN_FACT", "UNKNOWN_RULE"} <= codes


def test_missing_interpretive_support_is_allowed_without_rag() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis(rule_ids=[], evidence_ids=[]),
        configured_school="engineering_policy",
    )
    assert result.status == "passed"


def test_pipeline_repairs_school_method_confusion_without_rag() -> None:
    provider = _SchoolRepairProvider()
    result = AnalysisPipeline(provider=provider).run(
        chart=_chart(),
        user_focus=("事业财运",),
        max_revisions=2,
    )
    assert len(provider.calls) == 2
    assert result.validation.status == "passed"
    assert result.analysis.school == "engineering_policy"
    assert result.analysis.claims[0].school is None
    assert result.report is not None


def _analysis_with_text(text: str) -> StructuredAnalysisDTO:
    payload = _analysis().model_dump(mode="json")
    payload["executive_summary"] = text
    return StructuredAnalysisDTO.model_validate(payload)


def test_verifier_accepts_mutual_punishment_and_branch_break_from_core_tables() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("原局见子卯相刑，同时卯午相破。"),
        configured_school="engineering_policy",
    )
    assert result.status == "passed"
    assert "INVALID_BRANCH_RELATION" not in {item["code"] for item in result.errors}


def test_verifier_accepts_half_combination_and_warns_on_generic_combination_wording() -> None:
    explicit = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("申子半合水，亥卯半合木。"),
        configured_school="engineering_policy",
    )
    assert explicit.status == "passed"
    assert "INVALID_BRANCH_RELATION" not in {item["code"] for item in explicit.errors}

    generic = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("申子合水，亥卯合木。"),
        configured_school="engineering_policy",
    )
    assert generic.status == "passed"
    assert "AMBIGUOUS_BRANCH_COMBINATION_TERM" in {
        item["code"] for item in generic.warnings
    }


def test_verifier_accepts_model_visible_enriched_dayun_relation_fact_ids() -> None:
    chart = _chart()
    relations = _relations(chart)
    context = build_analysis_context(
        chart=chart,
        computed_relations=relations,
        computed_shensha=[],
    )
    sequence = context["temporal_hierarchy"]["dayun_sequence"]
    relation_id = sequence[0]["natal_interactions"][0]["fact_id"]
    payload = _analysis().model_dump(mode="json")
    payload["claims"][0]["fact_ids"] = [relation_id]
    payload["claims"][0]["rule_ids"] = []
    result = verify_analysis(
        chart=chart,
        evidence=(),
        analysis=StructuredAnalysisDTO.model_validate(payload),
        configured_school="engineering_policy",
        computed_relations=relations,
    )
    assert result.status == "passed"
    assert "UNKNOWN_FACT" not in {item["code"] for item in result.errors}


def test_health_assessment_structured_fields_count_as_substantive() -> None:
    chart = _chart()
    payload = _analysis().model_dump(mode="json")
    payload["health_assessment"] = [
        {
            "system": name,
            "strength": "有保护因素。",
            "risk": "存在传统五行偏性。",
            "protection": "岁运得助时缓解。",
            "advice": "保持规律生活。",
        }
        for name in ["肾", "心", "脾胃", "呼吸", "筋骨", "情绪"]
    ]
    analysis = StructuredAnalysisDTO.model_validate(payload)
    validation = verify_analysis(
        chart=chart,
        evidence=(),
        analysis=analysis,
        configured_school="engineering_policy",
        computed_relations=_relations(chart),
    )
    validation = _enforce_core_topic_coverage(
        chart=chart, analysis=analysis, validation=validation
    )
    assert "MISSING_HEALTH_ASSESSMENT" not in {
        item["code"] for item in validation.errors
    }


def test_verifier_relation_catalog_accepts_engine_supported_relations() -> None:
    text = (
        "甲己合，甲庚冲；子丑六合，子午冲，子未害，子酉破，子卯刑，午午自刑；"
        "申子半合，申辰拱合，午亥暗合；亥子半会，亥丑拱会；"
        "申子辰三合，亥子丑三会，寅巳申三刑；"
        "甲子与戊午天克地冲，甲子与己丑天合地合，甲子与甲子伏吟，甲子与庚午反吟；"
        "戊子盖头，丁亥截脚。"
    )
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text(text),
        configured_school="engineering_policy",
    )
    assert result.status == "passed", result.errors


def test_verifier_relation_catalog_rejects_outer_pairs_mislabeled_as_half_relations() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("申辰半合，亥丑半会，子辰六合，申子辰三会，甲乙合。"),
        configured_school="engineering_policy",
    )
    codes = {item["code"] for item in result.errors}
    assert "INVALID_BRANCH_RELATION" in codes
    assert "INVALID_BRANCH_GROUP_RELATION" in codes
    assert "INVALID_STEM_RELATION" in codes


def test_verifier_checks_every_branch_and_stem_in_compound_hidden_stem_claims() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("辛金藏于戌未之中；申中藏庚壬戊辛。"),
        configured_school="engineering_policy",
    )
    hidden_errors = [
        item for item in result.errors if item["code"] == "INVALID_HIDDEN_STEM"
    ]
    assert any("未" in item["detail"] and "辛" in item["detail"] for item in hidden_errors)
    assert any("申" in item["detail"] and "辛" in item["detail"] for item in hidden_errors)


def test_verifier_checks_passive_five_element_control_direction() -> None:
    valid = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("戊土被乙木克制。"),
        configured_school="engineering_policy",
    )
    assert "INVALID_ELEMENT_RELATION" not in {item["code"] for item in valid.errors}

    invalid = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis_with_text("乙木被戊土克制。"),
        configured_school="engineering_policy",
    )
    assert "INVALID_ELEMENT_RELATION" in {item["code"] for item in invalid.errors}
