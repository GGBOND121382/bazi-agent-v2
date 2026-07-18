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
from app.adapters.llm.deepseek import DeepSeekProvider, ModelInvalidOutputError
from app.api.dto import (
    ChartResultDTO,
    EngineVersionDTO,
    FactDTO,
    PillarDTO,
    StructuredAnalysisDTO,
)
from app.services.agent import AnalysisPipeline, ReportAssembler, verify_analysis
from app.services.agent.professional_core import _local_repair_schema

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
        "evidence_ids": [],
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
        dayun_assessment=[{"stage": "出生至起运", "conclusion": "说明起运前阶段。"}],
        claims=[claim],
        limitations=[],
    )



class _MockProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.last_input: dict[str, Any] | None = None
        self.inputs: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        self.last_input = kwargs["input_payload"]
        self.inputs.append(kwargs["input_payload"])
        schema = kwargs["schema"]
        payload = self.payload
        if schema.get("$id") == "analysis-json-patch-v2":
            operations = []
            for path in kwargs["input_payload"]["allowed_paths"]:
                parts = [part for part in path.split("/") if part]
                value: Any = self.payload
                for part in parts:
                    value = value[int(part)] if isinstance(value, list) else value[part]
                operations.append({"op": "replace", "path": path, "value": value})
            payload = {
                "schema_version": "analysis-json-patch-v2",
                "operations": operations,
                "repair_summary": "mock repair",
            }
        return ProviderResponse(
            payload=payload,
            model_id="mock-structured-v1",
            prompt_version=kwargs["prompt_version"],
        )


class _LocalRepairProvider:
    def __init__(self) -> None:
        self.request_kinds: list[str] = []
        self.inputs: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        schema = kwargs["schema"]
        self.inputs.append(kwargs["input_payload"])
        if schema.get("$id") == "analysis-json-patch-v2":
            self.request_kinds.append("local_repair")
            path = kwargs["input_payload"]["allowed_paths"][0]
            payload = {
                "schema_version": "analysis-json-patch-v2",
                "operations": [
                    {
                        "op": "replace",
                        "path": path,
                        "value": [
                            {"relation": name, "conclusion": "局部补全并保持原全局判断。"}
                            for name in [
                                "父亲",
                                "母亲",
                                "兄弟姐妹",
                                "配偶婚恋",
                                "子女",
                                "家庭互动",
                            ]
                        ],
                    }
                ],
                "repair_summary": "只补全六亲章节",
            }
        else:
            self.request_kinds.append("full_analysis")
            payload = _analysis().model_dump(mode="json")
            payload["kinship_assessment"] = []
        return ProviderResponse(
            payload=payload,
            model_id="mock-local-repair-v2",
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
    body = "".join(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks)
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
            {"choices": [{"delta": {"content": '{"status":'}, "finish_reason": "length"}]},
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


def test_deepseek_streams_structured_content_with_thinking_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return _sse_response(
            {"choices": [{"delta": {"content": '{"answer":"ok"}'}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"completion_tokens": 4}},
        )

    provider = DeepSeekProvider(
        thinking_enabled=False,
        max_transport_attempts=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_sink=lambda _trace: None,
    )
    response = provider.complete_json(
        system_prompt="chat",
        input_payload={},
        schema={"type": "object"},
        prompt_version="chat-test-v1",
    )

    assert response.streamed is True
    assert response.payload == {"answer": "ok"}
    assert request_bodies[0]["stream"] is True
    assert request_bodies[0]["thinking"] == {"type": "disabled"}
    assert request_bodies[0]["temperature"] == 0
    assert "reasoning_effort" not in request_bodies[0]


def test_deepseek_recovers_schema_valid_terminal_json_from_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    traces: list[dict[str, Any]] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return _sse_response(
            {
                "choices": [
                    {
                        "delta": {
                            "reasoning_content": (
                                "先分析命盘，过程中的对象 {不是最终结果}。\n"
                                '```json\n{"answer":"recovered"}\n```'
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    provider = DeepSeekProvider(
        max_transport_attempts=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_sink=traces.append,
    )
    response = provider.complete_json(
        system_prompt="chat",
        input_payload={},
        schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string", "minLength": 1}},
        },
        prompt_version="chat-reasoning-fallback-v1",
    )

    assert response.payload == {"answer": "recovered"}
    assert response.output_source == "reasoning_fallback"
    assert response.transport_attempts == 1
    assert traces[0]["status"] == "succeeded"
    assert traces[0]["response"]["content"] == ""
    assert traces[0]["response"]["output_source"] == "reasoning_fallback"


def test_deepseek_retries_output_that_fails_required_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("app.adapters.llm.deepseek.time.sleep", lambda _seconds: None)
    calls = 0
    traces: list[dict[str, Any]] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        answer = "" if calls == 1 else "retried"
        return _sse_response(
            {
                "choices": [
                    {
                        "delta": {"content": json.dumps({"answer": answer})},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    provider = DeepSeekProvider(
        max_transport_attempts=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_sink=traces.append,
    )
    response = provider.complete_json(
        system_prompt="chat",
        input_payload={},
        schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string", "minLength": 1}},
        },
        prompt_version="chat-schema-retry-v1",
    )

    assert calls == 2
    assert response.payload == {"answer": "retried"}
    assert response.output_source == "content"
    assert response.transport_attempts == 2
    assert [trace["status"] for trace in traces] == ["failed", "succeeded"]
    assert traces[0]["error"]["type"] == "ModelInvalidOutputError"


def test_deepseek_preserves_invalid_output_error_after_retries_are_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return _sse_response(
            {
                "choices": [
                    {"delta": {"content": '{"answer":""}'}, "finish_reason": "stop"}
                ]
            },
        )

    provider = DeepSeekProvider(
        max_transport_attempts=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace_sink=lambda _trace: None,
    )
    with pytest.raises(ModelInvalidOutputError):
        provider.complete_json(
            system_prompt="chat",
            input_payload={},
            schema={
                "type": "object",
                "required": ["answer"],
                "properties": {"answer": {"type": "string", "minLength": 1}},
            },
            prompt_version="chat-schema-failure-v1",
        )


@pytest.mark.rag
def test_verifier_rejects_hallucinated_ids_and_high_risk_assertions() -> None:
    analysis = _analysis(
        statement="一定患病并保证盈利。",
        fact_ids=["FACT-MISSING"],
        evidence_ids=["EVIDENCE-MISSING"],
    )
    result = verify_analysis(
        chart=_chart(), evidence=(), analysis=analysis, configured_school="engineering_policy"
    )
    assert result.status == "failed"
    codes = {error["code"] for error in result.errors}
    assert {"UNKNOWN_FACT", "EVIDENCE_DISABLED", "POLICY_HIGH_RISK_ASSERTION"} <= codes


@pytest.mark.rag
def test_verifier_does_not_require_interpretive_rag_support() -> None:
    analysis = _analysis(rule_ids=[], evidence_ids=[])
    result = verify_analysis(
        chart=_chart(), evidence=(), analysis=analysis, configured_school="engineering_policy"
    )
    assert result.status == "passed"


@pytest.mark.rag
def test_rule_validator_rejects_wrong_ten_god_hidden_stem_and_element_direction() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["executive_summary"] = "戊日主见甲为正财；辛藏于午；土克木。"
    analysis = StructuredAnalysisDTO.model_validate(payload)
    result = verify_analysis(
        chart=_chart(), evidence=(), analysis=analysis, configured_school="engineering_policy"
    )
    codes = {error["code"] for error in result.errors}
    assert {"TEN_GOD_MISMATCH", "INVALID_HIDDEN_STEM", "INVALID_ELEMENT_RELATION"} <= codes
    assert all(error.get("path") for error in result.errors if error["code"] in codes)


@pytest.mark.rag
def test_pipeline_builds_report_without_rag_and_keeps_prompt_and_raw_output() -> None:
    provider = _MockProvider(_analysis().model_dump(mode="json"))
    result = AnalysisPipeline(provider=provider).run(
        chart=_chart(), user_focus=("引用必须可追溯",), max_revisions=0
    )
    assert result.validation.status == "passed"
    assert result.report is not None
    assert result.evidence == ()
    assert "retrieval_context" not in (provider.last_input or {})
    assert "retrieval_policy" not in (provider.last_input or {})
    assert result.generation_trace["rag_enabled"] is False
    attempt = result.generation_trace["attempts"][0]
    assert attempt["input_payload"] == provider.last_input
    assert attempt["output_schema"]["$id"] == "analysis-output-v1"
    assert attempt["model_output"]
    assert "allowed_reference_ids" not in (provider.last_input or {})
    assert result.analysis.reflection is not None
    assert result.analysis.reflection.status == "pass"

    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "report.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(result.report, schema)


@pytest.mark.rag
def test_pipeline_repairs_only_the_missing_core_section_with_minimal_context() -> None:
    provider = _LocalRepairProvider()
    result = AnalysisPipeline(provider=provider).run(
        chart=_chart(), user_focus=("六亲",), max_revisions=1
    )
    assert result.validation.status == "passed"
    assert provider.request_kinds == ["full_analysis", "local_repair"]
    repair_input = provider.inputs[1]
    assert repair_input["allowed_paths"] == ["/kinship_assessment"]
    assert set(repair_input) == {
        "chart_id",
        "analysis_profile",
        "user_focus",
        "repair_mode",
        "allowed_paths",
        "current_blocks",
        "global_analysis_state",
        "consistency_neighbors",
        "relevant_context",
        "validation_errors",
        "revision_guidance",
    }
    assert "dayun_sequence" not in repair_input["relevant_context"].get("temporal_hierarchy", {})
    full_size = len(json.dumps(provider.inputs[0], ensure_ascii=False))
    repair_size = len(json.dumps(repair_input, ensure_ascii=False))
    assert repair_size < 5000
    assert repair_size < full_size * 1.1


def test_local_repair_schema_binds_replace_value_to_target_subschema() -> None:
    analysis_schema = json.loads(
        (ROOT / "contracts" / "schemas" / "analysis_output.schema.json").read_text(
            encoding="utf-8"
        )
    )
    repair_schema = _local_repair_schema({"/kinship_assessment"}, analysis_schema)
    variants = repair_schema["properties"]["operations"]["items"]["oneOf"]
    replace = next(item for item in variants if item["properties"]["op"] == {"const": "replace"})
    assert replace["properties"]["path"] == {"const": "/kinship_assessment"}
    value_schema = replace["properties"]["value"]
    assert value_schema == analysis_schema["properties"]["kinship_assessment"]
    assert value_schema["items"]["required"] == [
        "relationship",
        "evaluation",
        "fact_refs",
    ]


@pytest.mark.rag
def test_pipeline_discards_one_malformed_claim_and_normalizes_evidence_ids() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["claims"][0]["rule_ids"] = ["legacy-rule-id"]
    payload["claims"][0]["evidence_ids"] = ["legacy-rag-id"]
    payload["claims"].append(
        {**payload["claims"][0], "claim_id": "CLAIM-UNTRACEABLE", "fact_ids": []}
    )
    result = AnalysisPipeline(provider=_MockProvider(payload)).run(
        chart=_chart(), user_focus=("综合",), max_revisions=0
    )
    assert result.validation.status == "passed"
    assert [claim.claim_id for claim in result.analysis.claims] == ["CLAIM-1"]
    assert result.analysis.claims[0].rule_ids == []
    assert result.analysis.claims[0].evidence_ids == []
    repairs = result.generation_trace["attempts"][0]["schema_repairs"]
    assert {item["code"] for item in repairs} == {
        "DEFAULTED_EMPTY_CLAIM_REFERENCES",
        "INVALID_CLAIM_SCHEMA",
    }


@pytest.mark.rag
def test_pipeline_supplements_missing_deterministic_dayun_with_fallback_marker() -> None:
    payload = _analysis().model_dump(mode="json")
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
    result = AnalysisPipeline(provider=_MockProvider(payload)).run(
        chart=chart, user_focus=("大运",), max_revisions=0
    )
    assert result.validation.status == "passed"
    fallback = next(item for item in result.analysis.dayun_assessment if item.get("gan_zhi") == "丁亥")
    assert fallback["coverage_status"] == "deterministic_fallback"
    assert fallback["interpretation_status"] == "missing"


@pytest.mark.rag
def test_programmatic_reflection_diagnostics_are_not_revalidated_as_report_text() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["reflection"] = {
        "status": "revise",
        "contradictions": ["土克木的五行方向不成立"],
        "revision_instructions": ["修复原错误：土克木"],
    }
    analysis = StructuredAnalysisDTO.model_validate(payload)
    result = verify_analysis(
        chart=_chart(), evidence=(), analysis=analysis, configured_school="engineering_policy"
    )
    assert result.status == "passed"


@pytest.mark.rag
def test_failed_semantic_validation_never_produces_formal_report() -> None:
    payload = _analysis().model_dump(mode="json")
    payload["kinship_assessment"][0]["conclusion"] = "父星辛金藏于午。"
    result = AnalysisPipeline(provider=_MockProvider(payload)).run(
        chart=_chart(), user_focus=("六亲",), max_revisions=0
    )
    assert result.validation.status == "failed"
    assert result.report is None
    assert result.analysis.reflection is not None
    assert result.analysis.reflection.status == "revise"


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
                {"relation": name, "conclusion": "结合六亲星、宫位与岁运分析。"}
                for name in ["父亲", "母亲", "兄弟姐妹", "配偶婚恋", "子女", "家庭互动"]
            ],
            "health_assessment": [
                {"dimension": name, "conclusion": "结合五行偏性、调候与岁运变化分析。"}
                for name in ["五行偏性", "寒暖燥湿", "传统脏腑", "保护因素", "大运变化", "生活建议"]
            ],
            "dayun_assessment": [
                {
                    "stage": "出生至起运",
                    "conclusion": "说明起运前阶段与后续大运承接。",
                    "fact_ids": ["FACT-TRACE"],
                    "rule_ids": ["RULE-SEED-009"],
                    "evidence_ids": [],
                }
            ],
        }
    )
    result = AnalysisPipeline(provider=_MockProvider(payload)).run(
        chart=_chart(), user_focus=("综合",), max_revisions=0
    )
    assert result.report is not None
    section_ids = {section["section_id"] for section in result.report["sections"]}
    assert {"kinship", "health", "dayun-lifecycle"} <= section_ids
