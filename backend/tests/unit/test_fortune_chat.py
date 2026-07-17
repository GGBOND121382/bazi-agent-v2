"""Chart-aware follow-up dialogue tests."""
from datetime import date
from typing import Any

from app.adapters.llm import ProviderResponse
from app.api.dto import (
    ChartResultDTO,
    EngineVersionDTO,
    FactDTO,
    PillarDTO,
    TemporalContextViewDTO,
)
from app.services.chat import FortuneChatService
from app.services.rag.models import RetrievalChannel, RetrievalPlan, RetrievedEvidence


class _ChartService:
    def get_chart(self, chart_id: str) -> ChartResultDTO:
        return ChartResultDTO(
            chart_id=chart_id,
            calculation_status="passed",
            calculation_profile_id="ziping_standard_v1",
            normalized_time={"utc": "1995-12-22T08:00:00Z"},
            calendar={"deterministic_details": {"basic": {"ren_yuan_commander": "癸水用事"}}},
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
            engine_versions=[EngineVersionDTO(engine="test", version="1", took_ms=0)],
            warnings=[],
        )

    def get_temporal_context(
        self, chart_id: str, target_year: int, target_date: date | None = None
    ) -> TemporalContextViewDTO:
        del target_date
        return TemporalContextViewDTO(
            chart_id=chart_id,
            target_year=target_year,
            breadcrumb=[],
            dayuns=[],
            active_dayun={"ganzhi": "辛卯", "index": 3},
            year={
                "ganzhi": "丙午",
                "stem": "丙",
                "branch": "午",
                "fact_id": f"LIUNIAN-{target_year}",
                "rule_id": "LIUNIAN-CALENDAR-V1",
            },
            interactions=[
                {
                    "fact_id": "TREL-CHAT",
                    "type": "heaven_controls_earth_clashes",
                    "label": "天克地冲",
                    "participants": ["庚子", "甲午"],
                    "temporal_positions": ["dayun", "liunian"],
                    "rule_id": "PILLAR-TIANKEDICHONG-001",
                }
            ],
            interaction_summary={"high_attention_count": 1},
            months=[
                {
                    "index": index,
                    "label": f"节气月 {index}",
                    "ganzhi": "庚寅",
                    "stem": "庚",
                    "branch": "寅",
                    "fact_id": f"LIUYUE-{target_year}-{index:02d}",
                    "rule_id": "LIUYUE-JIEQI-V1",
                }
                for index in range(1, 13)
            ],
        )


class _Retriever:
    def __init__(self) -> None:
        self.plan: RetrievalPlan | None = None

    def retrieve(self, plan: RetrievalPlan) -> tuple[RetrievedEvidence, ...]:
        self.plan = plan
        return (
            RetrievedEvidence(
                chunk_id="RULE-A-CHAT",
                source_id="source-a",
                title="流年分析规则",
                content="结合原局、大运和流年判断阶段性倾向。",
                citation="source-a#rule",
                score=1.0,
                rank_reasons=("test",),
                channel=RetrievalChannel.AUTHORITATIVE_EVIDENCE,
                trust_tier="A",
            ),
        )


class _Provider:
    def __init__(self) -> None:
        self.input_payload: dict[str, Any] | None = None

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        self.input_payload = kwargs["input_payload"]
        return ProviderResponse(
            payload={
                "answer": "今年事业宜主动争取，但财务安排应保留余量。",
                "sections": [
                    {
                        "title": "事业与财运",
                        "content": "结合大运辛卯与流年丙午，先推进再复盘。",
                        "opportunities": ["主动承担可量化项目"],
                        "cautions": ["避免一次性扩大支出"],
                        "timing": ["按流月继续细查"],
                    }
                ],
                "citations": ["RULE-A-CHAT", "UNKNOWN"],
            },
            model_id="mock-chat",
            prompt_version=kwargs["prompt_version"],
        )


def test_fortune_chat_builds_deterministic_temporal_context_and_filters_citations() -> None:
    retriever = _Retriever()
    provider = _Provider()
    service = FortuneChatService(
        chart_service=_ChartService(),  # type: ignore[arg-type]
        retriever=retriever,
        provider_factory=lambda: provider,
    )
    result = service.answer(
        chart_id="chart-test",
        question="今年事业和财运怎么样？",
        scope="year",
        target_date=date(2026, 7, 17),
        history=({"role": "user", "content": "先看事业"},),
    )

    assert result["answer"]
    assert result["citations"] == [
        {
            "evidence_id": "RULE-A-CHAT",
            "title": "流年分析规则",
            "source_id": "source-a",
            "locator": "source-a#rule",
        }
    ]
    assert retriever.plan is not None
    assert any("流日财运事业感情" in query for query in retriever.plan.queries)
    assert provider.input_payload is not None
    assert provider.input_payload["natal_chart"]["deterministic_details"]["basic"][
        "ren_yuan_commander"
    ] == "癸水用事"
    assert provider.input_payload["temporal_context"]["dayun"]["ganzhi"] == "辛卯"
    assert provider.input_payload["temporal_context"]["temporal_interactions"][0]["type"] == "heaven_controls_earth_clashes"
    assert provider.input_payload["analysis_context"]["model_boundary"]["must_use_precomputed_temporal_relations"] is True
    assert provider.input_payload["conversation_history"] == [
        {"role": "user", "content": "先看事业"}
    ]
