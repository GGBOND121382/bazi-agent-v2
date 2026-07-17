"""Analysis jobs, follow-up chat, SSE replay, cancellation, and report reads."""
from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ...auth import CurrentUser, require_user
from ...domain.errors import InvalidInputError
from ...jobs import AnalysisJobService, JobStateError, get_default_analysis_service
from ...jobs.state import TERMINAL_STAGES
from ...persistence import connect
from ...services.chat import FortuneChatService, get_default_chat_service
from ..dto import ReportViewDTO, StructuredAnalysisDTO

router = APIRouter(prefix="/api/v1", tags=["analyses"])


class AnalysisStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_focus: list[str] = Field(min_length=1, max_length=8)
    school: str = "engineering_policy"


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class FortuneChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    scope: Literal["general", "dayun", "lifecycle", "year", "month", "day"] = "general"
    target_date: date = Field(default_factory=date.today)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    school: str = "engineering_policy"
    thread_id: str | None = None
    target_dayun_index: int | None = Field(default=None, ge=0, le=20)


def _analysis_service() -> AnalysisJobService:
    return get_default_analysis_service()


def _chat_service() -> FortuneChatService:
    return get_default_chat_service()


def _authorize_chart(chart_id: str, user: CurrentUser, chart_service: Any) -> None:
    stored = chart_service.store.get(chart_id)
    if stored is None or stored.deleted:
        raise InvalidInputError("chart not found")
    if not user.is_admin and stored.owner_id != user.user_id:
        raise HTTPException(status_code=403, detail="chart belongs to another user")


def _authorize_report(report_id: str, user: CurrentUser) -> None:
    if user.user_id == "anonymous":
        return
    with connect() as conn:
        row = conn.execute(
            """SELECT c.owner_id FROM reports r JOIN charts c ON c.chart_id=r.chart_id
            WHERE r.report_id=?""",
            (report_id,),
        ).fetchone()
    if row is None:
        raise InvalidInputError("report not found")
    if not user.is_admin and str(row["owner_id"]) != user.user_id:
        raise HTTPException(status_code=403, detail="report belongs to another user")


@router.post("/charts/{chart_id}/analyses", status_code=status.HTTP_202_ACCEPTED)
def start_analysis(
    chart_id: str,
    request: AnalysisStartRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    service: AnalysisJobService = Depends(_analysis_service),
    user: CurrentUser = Depends(require_user),
) -> dict[str, object]:
    _authorize_chart(chart_id, user, service.chart_service)
    try:
        job = service.start(
            chart_id=chart_id,
            user_focus=tuple(request.user_focus),
            school=request.school,
            idempotency_key=idempotency_key,
        )
    except JobStateError as exc:
        raise InvalidInputError(str(exc)) from exc
    return job.public_dict()


@router.post("/charts/{chart_id}/chat")
def chat_about_chart(
    chart_id: str,
    request: FortuneChatRequest,
    service: FortuneChatService = Depends(_chat_service),
    user: CurrentUser = Depends(require_user),
) -> dict[str, object]:
    """Answer chart-aware natal/dayun/year/month/day questions synchronously."""
    _authorize_chart(chart_id, user, service.chart_service)
    try:
        return service.answer(
            chart_id=chart_id,
            question=request.question,
            scope=request.scope,
            target_date=request.target_date,
            history=tuple(item.model_dump() for item in request.history),
            school=request.school,
            owner_id=user.user_id,
            thread_id=request.thread_id,
            target_dayun_index=request.target_dayun_index,
        )
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str, service: AnalysisJobService = Depends(_analysis_service)
) -> dict[str, object]:
    try:
        return service.require(job_id).public_dict()
    except JobStateError as exc:
        raise InvalidInputError("job not found") from exc


@router.get("/jobs/{job_id}/events")
def stream_job_events(
    job_id: str,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    last_event_id_query: str | None = Query(default=None, alias="last_event_id"),
    service: AnalysisJobService = Depends(_analysis_service),
) -> StreamingResponse:
    last_event_id = last_event_id_header or last_event_id_query
    try:
        service.require(job_id)
    except JobStateError as exc:
        raise InvalidInputError("job not found") from exc

    def events() -> Iterator[str]:
        cursor = last_event_id
        idle_ticks = 0
        while True:
            new_events = service.store.events_after(job_id, cursor)
            for event in new_events:
                cursor = event.event_id
                payload = json.dumps(
                    event.model_dump(mode="json", exclude_none=True),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"id: {event.event_id}\nevent: job\ndata: {payload}\n\n"
            current = service.require(job_id)
            if current.stage in TERMINAL_STAGES and not service.store.events_after(job_id, cursor):
                break
            idle_ticks += 1
            if idle_ticks % 100 == 0:
                yield ": heartbeat\n\n"
            time.sleep(0.1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_job(
    job_id: str, service: AnalysisJobService = Depends(_analysis_service)
) -> dict[str, object]:
    try:
        return service.cancel(job_id).public_dict()
    except JobStateError as exc:
        raise InvalidInputError(str(exc)) from exc


@router.get("/analyses/{analysis_id}", response_model=StructuredAnalysisDTO)
def get_analysis(
    analysis_id: str, service: AnalysisJobService = Depends(_analysis_service)
) -> StructuredAnalysisDTO:
    analysis = service.store.get_analysis(analysis_id)
    if analysis is None:
        raise InvalidInputError("analysis not found")
    return analysis


@router.get("/reports/{report_id}", response_model=ReportViewDTO)
def get_report(
    report_id: str,
    service: AnalysisJobService = Depends(_analysis_service),
    user: CurrentUser = Depends(require_user),
) -> ReportViewDTO:
    _authorize_report(report_id, user)
    report = service.store.get_report(report_id)
    if report is None:
        raise InvalidInputError("report not found")
    return ReportViewDTO.model_validate(report)


@router.get("/reports/{report_id}/generation-trace")
def get_report_generation_trace(
    report_id: str,
    service: AnalysisJobService = Depends(_analysis_service),
    user: CurrentUser = Depends(require_user),
) -> dict[str, object]:
    _authorize_report(report_id, user)
    trace = service.store.get_report_trace(report_id)
    if trace is None:
        raise InvalidInputError("generation trace not found")
    return trace


@router.get("/charts/{chart_id}/chat/threads")
def list_chat_threads(
    chart_id: str, user: CurrentUser = Depends(require_user)
) -> list[dict[str, object]]:
    _authorize_chart(chart_id, user, get_default_chat_service().chart_service)
    with connect() as conn:
        rows = conn.execute(
            """SELECT thread_id, chart_id, title, scope, created_at, updated_at
            FROM chat_threads WHERE chart_id=? AND owner_id=? ORDER BY updated_at DESC""",
            (chart_id, user.user_id),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/chat/threads/{thread_id}")
def read_chat_thread(
    thread_id: str, user: CurrentUser = Depends(require_user)
) -> dict[str, object]:
    with connect() as conn:
        thread = conn.execute(
            "SELECT * FROM chat_threads WHERE thread_id=?", (thread_id,)
        ).fetchone()
        if thread is None:
            raise InvalidInputError("chat thread not found")
        if not user.is_admin and str(thread["owner_id"]) != user.user_id:
            raise HTTPException(status_code=403, detail="thread belongs to another user")
        rows = conn.execute(
            "SELECT role, content, payload_json, created_at FROM chat_messages WHERE thread_id=? ORDER BY created_at, rowid",
            (thread_id,),
        ).fetchall()
    messages = []
    for row in rows:
        payload = json.loads(str(row["payload_json"])) if row["payload_json"] else None
        messages.append({
            "role": row["role"],
            "content": row["content"],
            "payload": payload,
            "created_at": row["created_at"],
        })
    return {"thread": dict(thread), "messages": messages}
