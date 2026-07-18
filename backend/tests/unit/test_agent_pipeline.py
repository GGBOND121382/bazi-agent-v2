"""A2 provider boundary, deterministic verification, and report gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import pytest

from app.adapters.llm import (
    ModelOutputTruncatedError,
    ProviderConfigurationError,
    ProviderResponse,
)
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
        kinship_assessment=[
            {"relation": name, "conclusion": "结合六亲星、宫位和岁运分析。"}
            for name in ["父亲", "母亲", "兄弟姐妹", "配偶婚恋", "子女", "家庭互动"]
        ],
        health_assessment=[
            {"dimension": name, "conclusion": "结合原局偏性和岁运变化分析。"}
            for name in ["五行偏性", "寒暖燥湿", "传统脏腑", "保护因素", "大运变化", "生活建议"]
        ],
        dayun_assessment=[
            {"stage": "出生至起运", "conclusion": "说明起运前阶段。"}
        ],
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
        schema = kwargs["schema"]
        payload = self.payload
        if schema.get("$id") == "analysis-repair-v1":
            targets = kwargs["input_payload"]["repair_targets"]
            payload = {
                "schema_version": "analysis-repair-v1",
                "replacement_fields": {name: self.payload[name] for name in targets},
                "remove_claim_ids": [],
                "repair_summary": "mock repair",
            }
        return ProviderResponse(
            payload=payload,
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


class _LocalRepairProvider:
    def __init__(self) -> None:
        self.request_kinds: list[str] = []

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        schema = kwargs["schema"]
        if schema.get("$id") == "analysis-repair-v1":
            self.request_kinds.append("local_repair")
            payload = {
                "schema_version": "analysis-repair-v1",
                "replacement_fields": {
                    "kinship_assessment": [
                        {"relation": name, "conclusion": "局部补全并保持原全局判断。"}
                        for name in [
                            "父亲",
                            "母亲",
                            "兄弟姐妹",
                            "配偶婚恋",
                            "子女",
                            "家庭互动",
                        ]
                    ]
                },
                "remove_claim_ids": [],
                "repair_summary": "只补全六亲章节",
            }
        else:
            self.request_kinds.append("full_analysis")
            payload = _analysis().model_dump(mode="json")
            payload["kinship_assessment"] = []
        return ProviderResponse(
            payload=payload,
            model_id="mock-local-repair-v1",
            prompt_version=kwargs["prompt_version"],
        )


@pytest.mark.rag
def test_deepseek_fails_closed_without_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError, match="required"):
        DeepSeekProvider()


@pytest.mark.rag
def test_deepseek_uses_streaming_thinking_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = DeepSeekProvider()

    assert provider._model_id == "deepseek-v4-pro"
    assert provider._thinking_enabled is True
    assert provider._timeout.connect == 15.0
    assert provider._timeout.read == 90.0
    assert provider._total_timeout_seconds == 600.0


@pytest.mark.rag
def _sse_response(*chunks: dict[str, Any], done: bool = True) -> httpx.Response:
    body = "".join(
        f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks
    )
    if done:
        body += "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def test_deepseek_retries_a_dropped_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    calls = 0
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        request_bodies.append(json.loads(request.content))
        if calls == 1:
            raise httpx.ReadError("incomplete chunked read", request=request)
        return _sse_response(
            {"choices": [{"delta": {"reasoning_content": "先整体判断"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": '{"status":"ok"}'}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        )

    events: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    provider = DeepSeekProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_sink=traces.append,
    )
    response = provider.complete_json(
        system_prompt="trace-system-prompt",
        input_payload={"chart_id": "chart_test"},
        schema={"type": "object"},
        prompt_version="test-v1",
        on_stream_event=events.append,
    )

    assert calls == 2
    assert request_bodies[-1]["model"] == "deepseek-v4-pro"
    assert request_bodies[-1]["stream"] is True
    assert request_bodies[-1]["thinking"] == {"type": "enabled"}
    assert request_bodies[-1]["reasoning_effort"] == "high"
    assert "temperature" not in request_bodies[-1]
    assert response.payload == {"status": "ok"}
    assert response.reasoning_content == "先整体判断"
    assert response.usage["prompt_tokens"] == 10
    assert response.streamed is True
    assert response.transport_attempts == 2
    assert any(event["phase"] == "retrying" for event in events)
    assert [trace["status"] for trace in traces] == ["failed", "succeeded"]
    assert traces[0]["error"]["type"] == "ReadError"
    assert traces[1]["request"]["system_prompt"] == "trace-system-prompt"
    assert traces[1]["request"]["input_payload"] == {"chart_id": "chart_test"}
    assert traces[1]["request"]["required_schema"] == {"type": "object"}
    assert traces[1]["response"]["parsed_payload"] == {"status": "ok"}
    assert traces[1]["response"]["reasoning_content"] == response.reasoning_content
    assert "test-key" not in json.dumps(traces, ensure_ascii=False)


def test_deepseek_rejects_truncated_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    traces: list[dict[str, Any]] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return _sse_response(
            {"choices": [{"delta": {"reasoning_content": "partial-reasoning"}}]},
            {"choices": [{"delta": {"content": '{"status":'}, "finish_reason": "length"}]}
        )

    provider = DeepSeekProvider(
        max_transport_attempts=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_sink=traces.append,
    )
    with pytest.raises(ModelOutputTruncatedError):
        provider.complete_json(
            system_prompt="test",
            input_payload={},
            schema={"type": "object"},
            prompt_version="test-v1",
        )
    assert traces[0]["status"] == "failed"
    assert traces[0]["response"]["reasoning_content"] == "partial-reasoning"
    assert traces[0]["response"]["content"] == '{"status":'
    assert traces[0]["error"]["type"] == "ModelOutputTruncatedError"


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
    assert "retrieved_evidence" not in (provider.last_input or {})
    assert (provider.last_input or {})["retrieval_policy"][
        "deterministic_engine_overrides_rag"
    ] is True

    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "report.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(result.report, schema)


@pytest.mark.rag
def test_pipeline_repairs_only_the_missing_core_section() -> None:
    provider = _LocalRepairProvider()
    result = AnalysisPipeline(provider=provider, retriever=_evidence()).run(
        chart=_chart(), user_focus=("引用必须可追溯",), max_revisions=1
    )

    assert result.validation.status == "passed"
    assert result.report is not None
    assert provider.request_kinds == ["full_analysis", "local_repair"]
    assert len(result.analysis.kinship_assessment) == 6
    assert len(result.analysis.health_assessment) == 6
    assert result.analysis.claims[0].claim_id == "CLAIM-1"
    assert [item["request_kind"] for item in result.generation_trace["attempts"]] == [
        "full_analysis",
        "local_repair",
    ]
    repair_input = result.generation_trace["attempts"][1]["input_payload"]
    assert repair_input["repair_targets"] == ["kinship_assessment"]
    assert "retrieved_evidence" not in repair_input


@pytest.mark.rag
def test_pipeline_discards_one_malformed_claim_instead_of_failing_the_job() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["claims"].append(
        {
            **payload["claims"][0],
            "claim_id": "CLAIM-UNTRACEABLE",
            "fact_ids": [],
        }
    )

    result = AnalysisPipeline(
        provider=_MockProvider(payload), retriever=_evidence()
    ).run(chart=_chart(), user_focus=("引用必须可追溯",), max_revisions=0)

    assert result.validation.status == "passed"
    assert result.report is not None
    assert [claim.claim_id for claim in result.analysis.claims] == ["CLAIM-1"]
    assert result.generation_trace["attempts"][0]["schema_repairs"][0]["code"] == (
        "INVALID_CLAIM_SCHEMA"
    )


@pytest.mark.rag
def test_pipeline_defaults_omitted_empty_evidence_ids_without_inventing_citations() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["claims"][0].pop("evidence_ids")

    result = AnalysisPipeline(
        provider=_MockProvider(payload), retriever=_evidence()
    ).run(chart=_chart(), user_focus=("引用必须可追溯",), max_revisions=0)

    assert result.validation.status == "passed"
    assert result.analysis.claims[0].evidence_ids == []
    repair = result.generation_trace["attempts"][0]["schema_repairs"][0]
    assert repair["code"] == "DEFAULTED_EMPTY_CLAIM_REFERENCES"
    assert repair["fields"] == ["evidence_ids"]


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
        if str(block["claim_id"]).startswith("CLAIM-")
    }
    assert report_claim_ids == {"CLAIM-1"}


@pytest.mark.rag
def test_pipeline_salvages_bad_claim_and_lists_missing_deterministic_dayun() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["dayun_assessment"][0]["conclusion"] += " 2000 年后仍须逐步核对。"
    payload["claims"].append(
        {
            **payload["claims"][0],
            "claim_id": "CLAIM-INVALID-DAYUN",
            "fact_ids": ["FACT-NOT-REAL"],
            "rule_ids": [],
            "evidence_ids": [],
        }
    )
    chart = _chart().model_copy(
        update={
            "dayun": [
                {
                    "index": 1,
                    "start_year": 2000,
                    "end_year": 2009,
                    "ganzhi": "丁亥",
                    "fact_id": "DAYUN-1",
                    "rule_id": "DAYUN-LUNAR-PYTHON-V2",
                }
            ]
        }
    )

    result = AnalysisPipeline(
        provider=_MockProvider(payload), retriever=_evidence()
    ).run(chart=chart, user_focus=("引用必须可追溯",), max_revisions=0)

    assert result.validation.status == "passed"
    assert result.report is not None
    assert [claim.claim_id for claim in result.analysis.claims] == ["CLAIM-1"]
    assert any("丁亥" in str(item.get("stage")) for item in result.analysis.dayun_assessment)
    assert any("确定性排盘信息" in item for item in result.analysis.limitations)


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


@pytest.mark.rag
def test_report_contains_dedicated_kinship_health_and_lifecycle_dayun_sections() -> None:
    payload = _analysis().model_dump(mode="json")
    payload.update(
        {
            "kinship_assessment": [
                {
                    "relation": name,
                    "conclusion": "结合六亲星、宫位与岁运分析。",
                    "fact_ids": ["FACT-TRACE"],
                    "rule_ids": ["RULE-SEED-009"],
                    "evidence_ids": ["RULE-SEED-009"],
                }
                for name in ["父亲", "母亲", "兄弟姐妹", "配偶婚恋", "子女", "家庭互动"]
            ],
            "health_assessment": [
                {
                    "dimension": name,
                    "conclusion": "区分长期偏性、保护因素与大运触发。",
                    "fact_ids": ["FACT-TRACE"],
                    "rule_ids": ["RULE-SEED-009"],
                    "evidence_ids": ["RULE-SEED-009"],
                }
                for name in ["五行偏性", "寒暖燥湿", "传统脏腑", "保护因素", "大运变化", "生活建议"]
            ],
            "dayun_assessment": [
                {
                    "title": "出生至起运",
                    "conclusion": "说明起运前阶段与后续大运承接。",
                    "fact_ids": ["FACT-TRACE"],
                    "rule_ids": ["RULE-SEED-009"],
                    "evidence_ids": ["RULE-SEED-009"],
                }
            ],
        }
    )
    result = AnalysisPipeline(provider=_MockProvider(payload), retriever=_evidence()).run(
        chart=_chart(), user_focus=("引用必须可追溯",)
    )
    assert result.report is not None
    section_ids = {section["section_id"] for section in result.report["sections"]}
    assert {"kinship", "health", "dayun-lifecycle"} <= section_ids
    assert result.generation_trace["attempts"]
