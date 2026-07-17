"""R1 history, notes, print/export metadata, sharing, and settings."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict, Field

from ...auth import CurrentUser, require_user
from ...domain.errors import InvalidInputError
from ...domain.profile import load_profile
from ...jobs import AnalysisJobService, JobStateError, get_default_analysis_service
from ...services.chart_service import ChartService, get_default_service
from ..dto import UserPreferencesDTO

router = APIRouter(prefix="/api/v1", tags=["resources"])


class NoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(max_length=500)


class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str | None = None
    detail_level: str | None = None
    theme: str | None = None
    reduce_motion: bool | None = None


_preferences = UserPreferencesDTO(
    language="zh-CN", detail_level="concise", theme="system", reduce_motion=False
)


def _jobs() -> AnalysisJobService:
    return get_default_analysis_service()


def _charts() -> ChartService:
    return get_default_service()


@router.get("/history")
def history(
    charts: ChartService = Depends(_charts),
    jobs: AnalysisJobService = Depends(_jobs),
    user: CurrentUser = Depends(require_user),
) -> dict[str, Any]:
    chart_items = [
        {
            "chart_id": item.chart_id,
            "calculation_status": item.calculation_status,
            "created_at": item.created_at.isoformat(),
            "note": item.note,
        }
        for item in charts.store.list_for_owner("*" if user.is_admin else user.user_id)
    ]
    allowed_chart_ids = {item["chart_id"] for item in chart_items}
    report_items = [
        {
            "report_id": item["report_id"],
            "chart_id": item["chart_id"],
            "title": item["title"],
            "generated_at": item["generated_at"],
        }
        for item in jobs.store.list_reports()
        if item["chart_id"] in allowed_chart_ids
    ]
    return {"charts": chart_items, "reports": report_items}


@router.patch("/charts/{chart_id}/note", status_code=status.HTTP_204_NO_CONTENT)
def set_chart_note(
    chart_id: str,
    request: NoteRequest,
    charts: ChartService = Depends(_charts),
    user: CurrentUser = Depends(require_user),
) -> None:
    stored = charts.store.get(chart_id)
    if stored is None or (not user.is_admin and stored.owner_id != user.user_id):
        raise InvalidInputError("chart not found")
    charts.set_note(chart_id, request.note)


@router.post("/reports/{report_id}/exports", status_code=status.HTTP_202_ACCEPTED)
def create_export(
    report_id: str,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    jobs: AnalysisJobService = Depends(_jobs),
) -> dict[str, str]:
    if jobs.store.get_report(report_id) is None:
        raise InvalidInputError("report not found")
    return {
        "export_id": f"print_{idempotency_key[:32]}",
        "status": "print_ready",
        "print_route": f"/reports/{report_id}/print",
    }


@router.post("/reports/{report_id}/shares", status_code=status.HTTP_201_CREATED)
def create_share(
    report_id: str, request: ShareRequest, jobs: AnalysisJobService = Depends(_jobs)
) -> dict[str, Any]:
    if os.environ.get("ENABLE_REPORT_SHARING", "false").casefold() != "true":
        raise InvalidInputError("report sharing is disabled")
    expires_at = datetime.now(UTC) + timedelta(hours=request.expires_in_hours)
    try:
        record, token = jobs.store.create_share(report_id, expires_at)
    except JobStateError as exc:
        raise InvalidInputError("report not found") from exc
    return {
        "share_id": record.share_id,
        "share_token": token,
        "expires_at": record.expires_at.isoformat(),
    }


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(share_id: str, jobs: AnalysisJobService = Depends(_jobs)) -> None:
    try:
        jobs.store.revoke_share(share_id)
    except JobStateError as exc:
        raise InvalidInputError("share not found") from exc


@router.get("/settings/profile", response_model=UserPreferencesDTO)
def get_preferences() -> UserPreferencesDTO:
    return _preferences


@router.patch("/settings/profile", response_model=UserPreferencesDTO)
def update_preferences(request: PreferencesPatch) -> UserPreferencesDTO:
    global _preferences
    current = _preferences.model_dump()
    current.update(request.model_dump(exclude_none=True))
    try:
        _preferences = UserPreferencesDTO.model_validate(current)
    except ValueError as exc:
        raise InvalidInputError("invalid preference value") from exc
    return _preferences


@router.get("/settings/configuration")
def get_configuration() -> dict[str, Any]:
    profile = load_profile()
    return {
        "calculation_profile_id": profile.profile_id,
        "calculation_profile_read_only": True,
        "model_provider": "deepseek",
        "model_configuration_read_only": True,
        "sharing_enabled": os.environ.get("ENABLE_REPORT_SHARING", "false").casefold() == "true",
    }
