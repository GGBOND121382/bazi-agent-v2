"""Chart-aware follow-up dialogue tests."""
from datetime import date
from typing import Any

import pytest

from app.adapters.llm import ProviderResponse
from app.api.dto import (
    ChartResultDTO,
    EngineVersionDTO,
    FactDTO,
    PillarDTO,
    TemporalContextViewDTO,
)
from app.services.chat import FortuneChatService, _default_chat_provider


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
                "temporal_interactions": [
                    {
                        "fact_id": "TREL-CHAT",
                        "type": "heaven_controls_earth_clashes",
                        "label": "天克地冲",
                        "participants": ["庚子", "甲午"],
                        "temporal_positions": ["dayun", "liunian"],
                        "rule_id": "PILLAR-TIANKEDICHONG-001",
                    }
                ],
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


class _Provider:
    def __init__(self) -> None:
        self.input_payload: dict[str, Any] | None = None
        self.system_prompt = ""

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        self.input_payload = kwargs["input_payload"]
        self.system_prompt = kwargs["system_prompt"]
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
    provider = _Provider()
    service = FortuneChatService(
        chart_service=_ChartService(),  # type: ignore[arg-type]
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
    assert result["citations"] == []
    assert provider.input_payload is not None
    context = provider.input_payload["analysis_context"]
    assert context["context_policy"] == "deterministic_read_only"
    assert context["natal_core"]["basic"]["ren_yuan_commander"] == "癸水用事"
    hierarchy = context["temporal_hierarchy"]
    assert hierarchy["active_dayun"]["ganzhi"] == "辛卯"
    assert hierarchy["target_liunian"]["cross_layer_interactions"][0]["type"] == "heaven_controls_earth_clashes"
    assert len(hierarchy["monthly_windows"]) == 12
    assert "target_liuri" not in hierarchy
    assert "natal_chart" not in provider.input_payload
    assert "temporal_context" not in provider.input_payload
    assert "answer_policy" not in provider.input_payload
    assert "evidence" not in provider.input_payload
    assert result["generation_trace"]["rag_enabled"] is False
    assert provider.input_payload["conversation_history"] == [
        {"role": "user", "content": "先看事业"}
    ]
    assert "scope=year" in provider.system_prompt
    assert "事业学业" in provider.system_prompt


def test_default_chat_provider_keeps_streaming_and_enables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider = _default_chat_provider()
    assert provider._thinking_enabled is True
