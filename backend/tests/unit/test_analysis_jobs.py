"""I2 job state, revision, replay and result persistence tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.adapters.llm import ModelTimeoutError, ProviderResponse
from app.api.dto import BirthRequest
from app.jobs import AnalysisJobService, InMemoryAnalysisStore, JobStateError
from app.services.agent import AnalysisPipeline
from app.services.chart_service import ChartService
from app.services.rag import CorpusGovernance, HybridRetriever, SourceCatalog
from app.services.rag.seed import import_approved_seed

ROOT = Path(__file__).resolve().parents[3]


class MockProvider:
    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        callback = kwargs.get("on_stream_event")
        if callback:
            callback({"phase": "request_started", "attempt": 1})
            callback({"phase": "reasoning", "attempt": 1, "reasoning_chars": 2400})
            callback(
                {
                    "phase": "answering",
                    "attempt": 1,
                    "reasoning_chars": 2400,
                    "content_chars": 3600,
                }
            )
        evidence_id = kwargs["input_payload"]["retrieval_context"]["authoritative_evidence"][0]["evidence_id"]
        payload = {
            "schema_version": "analysis-output-v1",
            "analysis_id": "analysis_job_test",
            "chart_id": kwargs["input_payload"]["chart_id"],
            "school": "engineering_policy",
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
                *[
                    {"stage": str(item.get("ganzhi", "大运")), "conclusion": "逐柱分析该步大运。"}
                    for item in kwargs["input_payload"]["analysis_context"]["temporal"]["dayun_table"]
                ],
            ],
            "claims": [
                {
                    "claim_id": "claim_job_test",
                    "topic": "引用",
                    "statement": "在本规则体系下，解释倾向保持可追溯。",
                    "fact_ids": ["FACT-Y-1"],
                    "rule_ids": [evidence_id],
                    "evidence_ids": [evidence_id],
                    "counterevidence": [],
                    "confidence": 0.7,
                    "temporal_scope": "natal",
                    "school": "engineering_policy",
                }
            ],
            "limitations": ["传统文化解释存在不确定性。"],
        }
        if callback:
            callback(
                {
                    "phase": "completed",
                    "attempt": 1,
                    "reasoning_chars": 2400,
                    "content_chars": 3600,
                }
            )
        return ProviderResponse(payload=payload, model_id="mock", prompt_version="test-v1")


def _chart_service() -> tuple[ChartService, str]:
    service = ChartService()
    request = BirthRequest.model_validate(
        {
            "gender": "male",
            "birth_datetime_local": "1990-06-15T12:00:00",
            "timezone": "Asia/Shanghai",
            "birthplace": {"country": "CN", "city": "Shanghai"},
            "calculation_profile_id": "ziping_standard_v1",
        }
    )
    _, chart_id, _ = service.create_chart(request=request, idempotency_key="chart-job-test")
    return service, chart_id


def _pipeline() -> AnalysisPipeline:
    governance = CorpusGovernance(
        SourceCatalog.load(ROOT / "contracts" / "rag_seed" / "source_catalog.json")
    )
    import_approved_seed(governance, ROOT / "contracts" / "rag_seed" / "rules_seed.jsonl")
    return AnalysisPipeline(
        provider=MockProvider(), retriever=HybridRetriever(governance.approved_chunks())
    )




class TimeoutProvider:
    def complete_json(self, **_kwargs: Any) -> ProviderResponse:
        raise ModelTimeoutError("test timeout")


def _timeout_pipeline() -> AnalysisPipeline:
    governance = CorpusGovernance(
        SourceCatalog.load(ROOT / "contracts" / "rag_seed" / "source_catalog.json")
    )
    import_approved_seed(governance, ROOT / "contracts" / "rag_seed" / "rules_seed.jsonl")
    return AnalysisPipeline(
        provider=TimeoutProvider(), retriever=HybridRetriever(governance.approved_chunks())
    )


def test_job_completes_and_sse_replay_is_monotonic() -> None:
    charts, chart_id = _chart_service()
    service = AnalysisJobService(
        chart_service=charts, pipeline_factory=_pipeline, store=InMemoryAnalysisStore()
    )
    initial = service.start(
        chart_id=chart_id,
        user_focus=("引用必须可追溯",),
        school="engineering_policy",
        idempotency_key="job-idem",
        run_async=False,
    )
    completed = service.require(initial.job_id)
    assert completed.stage == "completed"
    assert completed.result_ref
    events = service.store.events_after(initial.job_id, None)
    assert [int(event.event_id) for event in events] == list(range(1, len(events) + 1))
    assert {event.stage for event in events} >= {
        "queued", "calculating", "retrieving", "interpreting", "verifying", "report_building", "completed"
    }
    interpreting_events = [event for event in events if event.stage == "interpreting"]
    assert len(interpreting_events) >= 3
    assert any(
        event.safe_details and event.safe_details.get("provider_phase") == "reasoning"
        for event in interpreting_events
    )
    assert [event.progress for event in events] == sorted(event.progress for event in events)
    assert service.store.events_after(initial.job_id, "3")[0].event_id == "4"
    report = service.store.get_report(completed.result_ref)
    assert report and report["schema_version"] == "report-view-v1"

    same = service.start(
        chart_id=chart_id,
        user_focus=("different",),
        school="engineering_policy",
        idempotency_key="job-idem",
        run_async=False,
    )
    assert same.job_id == initial.job_id


def test_model_timeout_is_not_reported_as_internal_error() -> None:
    charts, chart_id = _chart_service()
    service = AnalysisJobService(
        chart_service=charts,
        pipeline_factory=_timeout_pipeline,
        store=InMemoryAnalysisStore(),
    )
    initial = service.start(
        chart_id=chart_id,
        user_focus=("引用必须可追溯",),
        school="engineering_policy",
        idempotency_key="job-timeout",
        run_async=False,
    )
    failed = service.require(initial.job_id)
    assert failed.stage == "failed"
    assert failed.error_code == "MODEL_TIMEOUT"
    assert service.store.events_after(initial.job_id, None)[-1].retryable is True


def test_invalid_transition_and_terminal_cancel_are_rejected() -> None:
    store = InMemoryAnalysisStore()
    job, _ = store.create(
        chart_id="chart", user_focus=("x",), school="engineering_policy", idempotency_key="k"
    )
    with pytest.raises(JobStateError, match="invalid"):
        store.transition(job.job_id, stage="completed", progress=100)
    store.transition(
        job.job_id,
        stage="calculating",
        progress=10,
        safe_details={"diagnostic_codes": ["TEST_CODE"]},
    )
    assert store.events_after(job.job_id, None)[-1].safe_details == {
        "diagnostic_codes": ["TEST_CODE"]
    }
    store.transition(job.job_id, stage="cancelled", progress=10, retryable=False)
    with pytest.raises(JobStateError, match="not cancellable"):
        store.request_cancel(job.job_id)
