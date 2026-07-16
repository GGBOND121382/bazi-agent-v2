"""A2 provider boundary, deterministic verification, and report gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from app.adapters.llm import ProviderConfigurationError, ProviderResponse
from app.adapters.llm.deepseek import DeepSeekProvider
from app.api.dto import (
    ChartResultDTO,
    EngineVersionDTO,
    FactDTO,
    PillarDTO,
    StructuredAnalysisDTO,
)
from app.services.agent import AnalysisPipeline, ReportAssembler, verify_analysis
from app.services.rag import CorpusGovernance, DatasetV2Retriever, HybridRetriever, SourceCatalog
from app.services.rag.models import RetrievalChannel, RetrievedEvidence
from app.services.rag.seed import import_approved_seed

ROOT = Path(__file__).resolve().parents[3]


def _chart(*, status: str = "passed") -> ChartResultDTO:
    return ChartResultDTO(
        chart_id="chart_test",
        calculation_status=status,
        calculation_profile_id="ziping_standard_v1",
        normalized_time={"utc": "2026-01-01T00:00:00Z"},
        calendar={},
        pillars=[
            PillarDTO(position="year", ganzhi="甲子", stem="甲", branch="子"),
            PillarDTO(position="month", ganzhi="丙寅", stem="丙", branch="寅"),
            PillarDTO(position="day", ganzhi="戊辰", stem="戊", branch="辰"),
            PillarDTO(position="hour", ganzhi="庚午", stem="庚", branch="午"),
        ],
        day_master="戊",
        facts=[
            FactDTO(
                fact_id="FACT-TRACE",
                fact_type="policy",
                value="解释应保持可追溯",
                rule_id="RULE-SEED-009",
                inputs=[],
            )
        ],
        engine_versions=[EngineVersionDTO(engine="test", version="1", took_ms=0)],
        warnings=[],
    )


def _analysis(**claim_overrides: Any) -> StructuredAnalysisDTO:
    claim = {
        "claim_id": "CLAIM-1",
        "topic": "evidence",
        "statement": "在本规则体系下，解释应保持可追溯。",
        "fact_ids": ["FACT-TRACE"],
        "rule_ids": ["RULE-SEED-009"],
        "evidence_ids": ["RULE-SEED-009"],
        "counterevidence": [],
        "confidence": 0.7,
        "temporal_scope": "natal",
        "school": "engineering_policy",
        **claim_overrides,
    }
    return StructuredAnalysisDTO(
        analysis_id="analysis_test",
        chart_id="chart_test",
        school="engineering_policy",
        claims=[claim],
        limitations=[],
    )


def _evidence():
    governance = CorpusGovernance(
        SourceCatalog.load(ROOT / "contracts" / "rag_seed" / "source_catalog.json")
    )
    import_approved_seed(governance, ROOT / "contracts" / "rag_seed" / "rules_seed.jsonl")
    return HybridRetriever(governance.approved_chunks())


class _MockProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.last_input: dict[str, Any] | None = None

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        self.last_input = kwargs["input_payload"]
        return ProviderResponse(
            payload=self.payload,
            model_id="mock-structured-v1",
            prompt_version=kwargs["prompt_version"],
        )


class _DatasetAwareProvider:
    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        context = kwargs["input_payload"]["retrieval_context"]
        authority = context["authoritative_evidence"][0]
        payload = _analysis(
            rule_ids=[authority["evidence_id"]],
            evidence_ids=[authority["evidence_id"]],
        ).model_dump(mode="json")
        return ProviderResponse(
            payload=payload,
            model_id="mock-dataset-aware-v1",
            prompt_version=kwargs["prompt_version"],
        )


@pytest.mark.rag
def test_deepseek_fails_closed_without_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError, match="required"):
        DeepSeekProvider()


@pytest.mark.rag
def test_verifier_rejects_hallucinated_ids_and_high_risk_assertions() -> None:
    evidence = _evidence().retrieve(
        __import__("app.services.rag", fromlist=["RetrievalPlan"]).RetrievalPlan(
            queries=("引用必须可追溯",), school="engineering_policy"
        )
    )
    analysis = _analysis(
        statement="一定患病并保证盈利。",
        fact_ids=["FACT-MISSING"],
        evidence_ids=["EVIDENCE-MISSING"],
    )
    result = verify_analysis(
        chart=_chart(),
        evidence=evidence,
        analysis=analysis,
        configured_school="engineering_policy",
    )
    assert result.status == "failed"
    codes = {error["code"] for error in result.errors}
    assert {"UNKNOWN_FACT", "UNKNOWN_EVIDENCE", "POLICY_HIGH_RISK_ASSERTION"} <= codes
    assert result.approved_claim_ids == []


@pytest.mark.rag
def test_verifier_rejects_c_tier_case_as_authoritative_rule() -> None:
    case = RetrievedEvidence(
        chunk_id="CASE-C-1",
        source_id="case-source",
        title="historical case",
        content="historical example",
        citation="case-source#CASE-C-1",
        score=1.0,
        rank_reasons=("test",),
        channel=RetrievalChannel.SIMILAR_CASES,
        collection="benchmark_case_qa",
        trust_tier="C",
        can_support_claim=False,
        can_support_case_analogy=True,
    )
    analysis = _analysis(rule_ids=["CASE-C-1"], evidence_ids=["CASE-C-1"])
    result = verify_analysis(
        chart=_chart(),
        evidence=(case,),
        analysis=analysis,
        configured_school="engineering_policy",
    )
    codes = {error["code"] for error in result.errors}
    assert "NON_AUTHORITATIVE_RULE" in codes
    assert "CASE_ANALOGY_NOT_QUALIFIED" not in codes


@pytest.mark.rag
def test_verifier_accepts_tokens_supported_by_an_authoritative_rule() -> None:
    authority = RetrievedEvidence(
        chunk_id="RULE-A-1",
        source_id="core-source",
        title="authoritative rule",
        content="丁火在本规则表中作为示例字符。",
        citation="core-source#RULE-A-1",
        score=1.0,
        rank_reasons=("test",),
    )
    analysis = _analysis(
        statement="在本规则体系下，丁火属于已引用规则内容。",
        rule_ids=["RULE-A-1"],
        evidence_ids=[],
    )
    result = verify_analysis(
        chart=_chart(),
        evidence=(authority,),
        analysis=analysis,
        configured_school="engineering_policy",
    )
    assert result.status == "passed"


@pytest.mark.rag
def test_pipeline_builds_schema_valid_report_from_passed_analysis_only() -> None:
    provider = _MockProvider(_analysis().model_dump(mode="json"))
    pipeline = AnalysisPipeline(provider=provider, retriever=_evidence())
    result = pipeline.run(chart=_chart(), user_focus=("引用必须可追溯",))
    assert result.validation.status == "passed"
    assert result.report is not None
    assert result.report["metadata"]["model_id"] == "mock-structured-v1"
    assert "normalized_time" not in (provider.last_input or {})
    assert "retrieval_context" in (provider.last_input or {})
    assert (provider.last_input or {})["retrieval_policy"][
        "deterministic_engine_overrides_rag"
    ] is True

    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "report.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(result.report, schema)


@pytest.mark.rag
def test_pipeline_runs_end_to_end_with_production_dataset_channels() -> None:
    pipeline = AnalysisPipeline(
        provider=_DatasetAwareProvider(),
        retriever=DatasetV2Retriever(ROOT / "data" / "bazi_rag_dataset_v2_1"),
    )
    result = pipeline.run(chart=_chart(), user_focus=("财运",))
    assert result.validation.status == "passed"
    assert result.report is not None
    assert any(item.can_support_claim for item in result.evidence)
    assert any(item.can_supply_explanation for item in result.evidence)


@pytest.mark.rag
def test_failed_validation_never_produces_formal_report() -> None:
    provider = _MockProvider(_analysis(evidence_ids=["invented-evidence"]).model_dump(mode="json"))
    result = AnalysisPipeline(provider=provider, retriever=_evidence()).run(
        chart=_chart(), user_focus=("引用必须可追溯",)
    )
    assert result.validation.status == "failed"
    assert result.report is None
    assert "validation_errors" in (provider.last_input or {})


@pytest.mark.rag
def test_pipeline_salvages_only_claims_that_pass_the_deterministic_gate() -> None:
    valid = _analysis().model_dump(mode="json")
    invalid = {
        **valid["claims"][0],
        "claim_id": "CLAIM-INVALID",
        "evidence_ids": ["invented-evidence"],
    }
    valid["claims"] = [*valid["claims"], invalid]
    result = AnalysisPipeline(
        provider=_MockProvider(valid), retriever=_evidence()
    ).run(
        chart=_chart(),
        user_focus=("引用必须可追溯",),
        max_revisions=0,
    )

    assert result.validation.status == "passed"
    assert result.report is not None
    assert [claim.claim_id for claim in result.analysis.claims] == ["CLAIM-1"]
    assert not any("已排除" in item for item in result.analysis.limitations)
    report_claim_ids = {
        block["claim_id"]
        for section in result.report["sections"]
        for block in section["content_blocks"]
    }
    assert report_claim_ids == {"CLAIM-1"}


@pytest.mark.rag
def test_report_assembler_rejects_failed_validation() -> None:
    analysis = _analysis()
    validation = verify_analysis(
        chart=_chart(status="failed"),
        evidence=(),
        analysis=analysis,
        configured_school="engineering_policy",
    )
    with pytest.raises(ValueError, match="passed"):
        ReportAssembler().assemble(
            chart=_chart(),
            analysis=analysis,
            validation=validation,
            evidence=(),
            prompt_version="test",
            model_id="mock",
            retrieval_trace_id="trace",
        )
