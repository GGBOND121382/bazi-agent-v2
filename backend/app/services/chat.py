"""Chart-aware follow-up dialogue for year/month/day fortune questions."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any, Literal, cast

from ..adapters.llm import DeepSeekProvider
from ..adapters.llm.deepseek import StructuredOutputProvider
from .agent.prompts import FORTUNE_CHAT_PROMPT_VERSION, FORTUNE_CHAT_SYSTEM_PROMPT
from .chart_service import ChartService, get_default_service
from .rag import DatasetV2Retriever, EvidenceRetriever, RetrievalPlan, RetrievedEvidence

ChatScope = Literal["general", "year", "month", "day"]

_CHAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "sections", "citations"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "content"],
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "opportunities": {"type": "array", "items": {"type": "string"}},
                    "cautions": {"type": "array", "items": {"type": "string"}},
                    "timing": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "citations": {"type": "array", "items": {"type": "string"}},
    },
}



def _serialize_evidence(item: RetrievedEvidence) -> dict[str, object]:
    return {
        "evidence_id": item.chunk_id,
        "source_id": item.source_id,
        "title": item.title,
        "content": item.content,
        "citation": item.citation,
        "channel": item.channel.value,
        "trust_tier": item.trust_tier,
    }


class FortuneChatService:
    def __init__(
        self,
        *,
        chart_service: ChartService,
        retriever: EvidenceRetriever,
        provider_factory: Callable[[], StructuredOutputProvider] = DeepSeekProvider,
    ) -> None:
        self.chart_service = chart_service
        self.retriever = retriever
        self.provider_factory = provider_factory

    def answer(
        self,
        *,
        chart_id: str,
        question: str,
        scope: ChatScope,
        target_date: date,
        history: tuple[dict[str, str], ...] = (),
        school: str = "engineering_policy",
    ) -> dict[str, object]:
        chart = self.chart_service.get_chart(chart_id)
        temporal = self.chart_service.get_temporal_context(
            chart_id, target_date.year, target_date
        )
        selected_day = temporal.selected_day or {}
        target_pillars = {
            "year": str(temporal.year.get("ganzhi", "")),
            "month": str(selected_day.get("month_ganzhi", "")),
            "day": str(selected_day.get("ganzhi", "")),
        }
        deterministic_details = chart.calendar.get("deterministic_details", {})
        active_dayun = temporal.active_dayun or {}
        queries = tuple(
            dict.fromkeys(
                item
                for item in (
                    question.strip(),
                    f"{chart.day_master}日主{scope}运势",
                    f"{target_pillars['year']}流年{target_pillars['month']}流月",
                    f"{target_pillars['day']}流日财运事业感情",
                    f"大运{active_dayun.get('ganzhi', '')}与原局作用",
                )
                if item.strip()
            )
        )
        evidence = self.retriever.retrieve(
            RetrievalPlan(
                queries=queries,
                school=school,
                task_type="interpretation",
                top_k=10,
                case_top_k=3,
                explanation_top_k=4,
            )
        )
        evidence_payload = [_serialize_evidence(item) for item in evidence]
        payload: dict[str, Any] = {
            "chart_id": chart_id,
            "question": question,
            "scope": scope,
            "target_date": target_date.isoformat(),
            "natal_chart": {
                "day_master": chart.day_master,
                "pillars": [item.model_dump(mode="json") for item in chart.pillars],
                "facts": [item.model_dump(mode="json") for item in chart.facts],
                "deterministic_details": deterministic_details,
            },
            "temporal_context": {
                "dayun": active_dayun,
                "liunian": temporal.year,
                "liuyue_table": temporal.months,
                "selected_day": selected_day,
                "target_pillars": target_pillars,
            },
            "retrieved_evidence": evidence_payload,
            "conversation_history": list(history[-8:]),
            "answer_policy": {
                "give_conclusion_first": True,
                "cover_opportunities_obstacles_timing_and_advice": True,
                "allow_school_based_strength_pattern_and_useful_element_judgments": True,
                "avoid_repetitive_audit_disclaimers": True,
            },
        }
        response = self.provider_factory().complete_json(
            system_prompt=FORTUNE_CHAT_SYSTEM_PROMPT,
            input_payload=payload,
            schema=_CHAT_SCHEMA,
            prompt_version=FORTUNE_CHAT_PROMPT_VERSION,
        )
        raw_answer = response.payload.get("answer")
        answer = str(raw_answer).strip() if raw_answer is not None else ""
        if not answer:
            raise ValueError("provider returned an empty chat answer")
        raw_sections = response.payload.get("sections", [])
        sections = [
            cast(dict[str, object], item)
            for item in raw_sections
            if isinstance(item, dict) and str(item.get("content", "")).strip()
        ] if isinstance(raw_sections, list) else []
        known_evidence = {item.chunk_id: item for item in evidence}
        raw_citations = response.payload.get("citations", [])
        citation_ids = [
            str(item)
            for item in raw_citations
            if isinstance(raw_citations, list) and str(item) in known_evidence
        ]
        citations = [
            {
                "evidence_id": evidence_id,
                "title": known_evidence[evidence_id].title,
                "source_id": known_evidence[evidence_id].source_id,
                "locator": known_evidence[evidence_id].citation,
            }
            for evidence_id in dict.fromkeys(citation_ids)
        ]
        return {
            "answer": answer,
            "sections": sections,
            "citations": citations,
            "scope": scope,
            "target_date": target_date.isoformat(),
            "deterministic_context": {
                "dayun": active_dayun,
                "year": temporal.year,
                "selected_day": selected_day,
                "target_pillars": target_pillars,
            },
            "model_id": response.model_id,
            "prompt_version": response.prompt_version,
        }


_DEFAULT_CHAT_SERVICE: FortuneChatService | None = None


def get_default_chat_service() -> FortuneChatService:
    global _DEFAULT_CHAT_SERVICE
    if _DEFAULT_CHAT_SERVICE is None:
        _DEFAULT_CHAT_SERVICE = FortuneChatService(
            chart_service=get_default_service(),
            retriever=DatasetV2Retriever(),
        )
    return _DEFAULT_CHAT_SERVICE
