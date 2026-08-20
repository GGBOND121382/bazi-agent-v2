"""Chart-aware follow-up dialogue for year/month/day fortune questions."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, Literal, cast

from ..adapters.llm import DeepSeekProvider
from ..adapters.llm.deepseek import StructuredOutputProvider
from ..logging_setup import append_llm_trace
from ..persistence import connect
from .agent.prompts import FORTUNE_CHAT_PROMPT_VERSION, build_fortune_chat_system_prompt
from .chart_service import ChartService, get_default_service
from .chat_context import build_model_context, compact_history, detect_chat_topics

ChatScope = Literal["general", "dayun", "lifecycle", "year", "month", "day"]


def _default_chat_provider() -> StructuredOutputProvider:
    # Fortune analysis benefits materially from reasoning.  The provider keeps
    # the public answer separate and has a schema-checked recovery path for the
    # occasional DeepSeek JSON response that lands at the end of reasoning.
    return DeepSeekProvider(thinking_enabled=True)

_CHAT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "reasoning_summary", "sections", "citations"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "reasoning_summary": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dimension", "conclusion"],
                "properties": {
                    "dimension": {"type": "string"},
                    "conclusion": {"type": "string"},
                    "basis": {"type": "array", "items": {"type": "string"}},
                    "counterpoints": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
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



class FortuneChatService:
    def __init__(
        self,
        *,
        chart_service: ChartService,
        provider_factory: Callable[[], StructuredOutputProvider] = _default_chat_provider,
    ) -> None:
        self.chart_service = chart_service
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
        owner_id: str = "anonymous",
        thread_id: str | None = None,
        target_dayun_index: int | None = None,
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
        selected_dayun = active_dayun
        if target_dayun_index is not None:
            selected_dayun = next(
                (item for item in temporal.dayuns if int(item.get("index", -1)) == target_dayun_index),
                active_dayun,
            )
        topics = detect_chat_topics(question)
        natal_payload = {
            "day_master": chart.day_master,
            "pillars": [item.model_dump(mode="json") for item in chart.pillars],
            "facts": [item.model_dump(mode="json") for item in chart.facts],
            "deterministic_details": deterministic_details,
        }
        temporal_payload = {
            "qiyun": temporal.qiyun,
            "dayun_table": temporal.dayuns,
            "dayun": selected_dayun,
            "selected_dayun": selected_dayun,
            "active_dayun": active_dayun,
            "liunian": temporal.year,
            "liuyue_table": temporal.months,
            "selected_liuyue": temporal.selected_month,
            "selected_liuri": selected_day,
            "temporal_interactions": temporal.interactions,
            "interaction_summary": temporal.interaction_summary,
            "target_pillars": target_pillars,
            "seasonal_strength": temporal.seasonal_strength,
        }
        analysis_context = build_model_context(
            chart,
            temporal,
            scope=scope,
            topics=topics,
            selected_dayun=selected_dayun,
        )
        query_payload: dict[str, object] = {
            "question": question,
            "scope": scope,
            "topics": list(topics),
            "target_date": target_date.isoformat(),
        }
        if target_dayun_index is not None:
            query_payload["target_dayun_index"] = target_dayun_index
        payload: dict[str, Any] = {
            "query": query_payload,
            "analysis_context": analysis_context,
            "output_profile": "fortune-chat-json-v2",
        }
        compacted_history = compact_history(history)
        if compacted_history:
            payload["conversation_history"] = compacted_history
        system_prompt = build_fortune_chat_system_prompt(scope=scope, topics=topics)
        response = self.provider_factory().complete_json(
            system_prompt=system_prompt,
            input_payload=payload,
            schema=_CHAT_SCHEMA,
            prompt_version=FORTUNE_CHAT_PROMPT_VERSION,
        )
        raw_answer = response.payload.get("answer")
        answer = str(raw_answer).strip() if raw_answer is not None else ""
        if not answer:
            raise ValueError("provider returned an empty chat answer")
        raw_reasoning = response.payload.get("reasoning_summary", [])
        reasoning_summary = (
            [cast(dict[str, object], item) for item in raw_reasoning if isinstance(item, dict)]
            if isinstance(raw_reasoning, list)
            else []
        )
        raw_sections = response.payload.get("sections", [])
        sections = (
            [
                cast(dict[str, object], item)
                for item in raw_sections
                if isinstance(item, dict) and str(item.get("content", "")).strip()
            ]
            if isinstance(raw_sections, list)
            else []
        )
        citations: list[dict[str, object]] = []
        trace: dict[str, Any] = {
            "trace_type": "fortune_chat",
            "system_prompt": system_prompt,
            "prompt_version": response.prompt_version,
            "model_id": response.model_id,
            "input_payload": payload,
            "rag_enabled": False,
            "deterministic_snapshot": {
                "natal": natal_payload,
                "temporal": temporal_payload,
            },
            "model_output": response.payload,
            "provider_reasoning_content": response.reasoning_content,
            "provider_usage": response.usage,
            "provider_finish_reason": response.finish_reason,
            "provider_streamed": response.streamed,
            "provider_transport_attempts": response.transport_attempts,
            "provider_output_source": response.output_source,
            "provider_timings": response.timings,
        }
        resolved_thread_id = self._save_conversation(
            owner_id=owner_id,
            chart_id=chart_id,
            scope=scope,
            question=question,
            answer=answer,
            response_payload={
                "reasoning_summary": reasoning_summary,
                "sections": sections,
                "citations": citations,
                "deterministic_context": temporal_payload,
                "generation_trace": trace,
            },
            trace=trace,
            thread_id=thread_id,
            model_id=response.model_id,
            prompt_version=response.prompt_version,
        )
        return {
            "answer": answer,
            "reasoning_summary": reasoning_summary,
            "sections": sections,
            "citations": citations,
            "scope": scope,
            "target_date": target_date.isoformat(),
            "target_dayun_index": target_dayun_index,
            "deterministic_context": temporal_payload,
            "model_id": response.model_id,
            "prompt_version": response.prompt_version,
            "thread_id": resolved_thread_id,
            "generation_trace": trace,
        }

    @staticmethod
    def _save_conversation(
        *,
        owner_id: str,
        chart_id: str,
        scope: str,
        question: str,
        answer: str,
        response_payload: dict[str, object],
        trace: dict[str, object],
        thread_id: str | None,
        model_id: str,
        prompt_version: str,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        resolved = thread_id or f"thread_{uuid.uuid4().hex[:12]}"
        with connect() as conn:
            existing = conn.execute(
                "SELECT thread_id FROM chat_threads WHERE thread_id=? AND owner_id=?",
                (resolved, owner_id),
            ).fetchone()
            if existing is None:
                title = question.strip().replace("\n", " ")[:36] or "命理问答"
                conn.execute(
                    """INSERT INTO chat_threads
                    (thread_id, chart_id, owner_id, title, scope, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (resolved, chart_id, owner_id, title, scope, now, now),
                )
            else:
                conn.execute(
                    "UPDATE chat_threads SET scope=?, updated_at=? WHERE thread_id=?",
                    (scope, now, resolved),
                )
            conn.execute(
                "INSERT INTO chat_messages(message_id, thread_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
                (f"msg_{uuid.uuid4().hex[:12]}", resolved, question, now),
            )
            conn.execute(
                """INSERT INTO chat_messages
                (message_id, thread_id, role, content, payload_json, created_at)
                VALUES (?, ?, 'assistant', ?, ?, ?)""",
                (
                    f"msg_{uuid.uuid4().hex[:12]}",
                    resolved,
                    answer,
                    json.dumps(response_payload, ensure_ascii=False, default=str),
                    now,
                ),
            )
            call_id = f"llm_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO llm_calls
                (call_id, owner_id, chart_id, thread_id, call_type, prompt_version, model_id, trace_json, created_at)
                VALUES (?, ?, ?, ?, 'fortune_chat', ?, ?, ?, ?)""",
                (
                    call_id,
                    owner_id,
                    chart_id,
                    resolved,
                    prompt_version,
                    model_id,
                    json.dumps(trace, ensure_ascii=False, default=str),
                    now,
                ),
            )
        append_llm_trace({"call_id": call_id, "owner_id": owner_id, "thread_id": resolved, **trace})
        return resolved


_DEFAULT_CHAT_SERVICE: FortuneChatService | None = None


def get_default_chat_service() -> FortuneChatService:
    global _DEFAULT_CHAT_SERVICE
    if _DEFAULT_CHAT_SERVICE is None:
        _DEFAULT_CHAT_SERVICE = FortuneChatService(
            chart_service=get_default_service(),
        )
    return _DEFAULT_CHAT_SERVICE
