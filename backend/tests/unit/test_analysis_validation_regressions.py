"""Regressions for school metadata and deterministic temporal references."""
from __future__ import annotations

from typing import Any

from app.adapters.llm import ProviderResponse
from app.api.dto import ChartResultDTO, EngineVersionDTO, FactDTO, PillarDTO, StructuredAnalysisDTO
from app.services.rag.models import RetrievalChannel, RetrievalPlan, RetrievedEvidence

from app.services.agent import AnalysisPipeline, verify_analysis


def _chart() -> ChartResultDTO:
    return ChartResultDTO(
        chart_id="chart_temporal_validation",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={"utc": "1995-12-22T07:00:00Z"},
        calendar={},
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
            "reflection": {"status": "pass", "checked_dimensions": ["大运"]},
            "limitations": [],
        }
    )


class _Retriever:
    def retrieve(self, plan: RetrievalPlan) -> tuple[RetrievedEvidence, ...]:
        del plan
        return (
            RetrievedEvidence(
                chunk_id="RULE-A-TEMPORAL",
                source_id="source-temporal",
                title="岁运分析规则",
                content="岁运判断应结合原局和当前大运。",
                citation="source-temporal#rule",
                score=1.0,
                rank_reasons=("test",),
                channel=RetrievalChannel.AUTHORITATIVE_EVIDENCE,
                trust_tier="A",
                can_support_claim=True,
            ),
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
            assert payload["analysis_profile"]["methodology_priority"] == "ziping_structure_first"
            assert "primary_method" not in payload["analysis_profile"]
            assert payload["output_contract"]["analysis_school_must_equal"] == "engineering_policy"
            assert "DAYUN-3" in payload["allowed_reference_ids"]["fact_ids"]
            assert "DAYUN-LUNAR-PYTHON-V2" in payload["allowed_reference_ids"]["rule_ids"]
            guidance = " ".join(payload["revision_guidance"])
            assert "analysis.school 必须逐字等于" in guidance
            assert "claim.school 应省略" in guidance
            analysis = _analysis()
        return ProviderResponse(
            payload=analysis.model_dump(mode="json"),
            model_id="mock-school-repair",
            prompt_version=kwargs["prompt_version"],
        )


def test_verifier_accepts_model_visible_dayun_and_temporal_ids() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis(),
        configured_school="engineering_policy",
    )
    assert result.status == "passed"
    codes = {error["code"] for error in result.errors}
    assert "UNKNOWN_FACT" not in codes
    assert "UNKNOWN_RULE" not in codes
    assert "NON_AUTHORITATIVE_RULE" not in codes
    assert not any(
        warning["code"] == "UNREFERENCED_GANZHI_TOKEN" for warning in result.warnings
    )


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
    assert {"UNKNOWN_FACT", "UNKNOWN_RULE", "NON_AUTHORITATIVE_RULE"} <= codes


def test_missing_interpretive_support_remains_a_hard_failure() -> None:
    result = verify_analysis(
        chart=_chart(),
        evidence=(),
        analysis=_analysis(rule_ids=[], evidence_ids=[]),
        configured_school="engineering_policy",
    )
    assert result.status == "failed"
    assert "MISSING_INTERPRETIVE_SUPPORT" in {
        error["code"] for error in result.errors
    }


def test_pipeline_repairs_school_method_confusion_with_executable_guidance() -> None:
    provider = _SchoolRepairProvider()
    result = AnalysisPipeline(provider=provider, retriever=_Retriever()).run(
        chart=_chart(),
        user_focus=("事业财运",),
        max_revisions=2,
    )
    assert len(provider.calls) == 2
    assert result.validation.status == "passed"
    assert result.analysis.school == "engineering_policy"
    assert result.analysis.claims[0].school is None
    assert result.report is not None
