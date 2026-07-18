"""HTTP routes for /v1/charts.

- POST /v1/charts          — create (Idempotency-Key required)
- GET  /v1/charts           — list current user's charts
- GET  /v1/charts/{id}      — get one
- DELETE /v1/charts/{id}    — delete (soft)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import ValidationError as PydanticValidationError

from ...auth import CurrentUser, require_user
from ...domain.errors import InvalidInputError
from ...services.chart_service import ChartService, get_default_service
from ...services.viewmodel_mapper import to_chart_overview_view_dto
from ..dto import ApiError, ChartOverviewViewDTO, ChartResultDTO, TemporalContextViewDTO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/charts", tags=["charts"])


def _chart_service() -> ChartService:
    return get_default_service()


def _authorize_chart(svc: ChartService, chart_id: str, user: CurrentUser) -> None:
    stored = svc.store.get(chart_id)
    if stored is None or stored.deleted:
        raise InvalidInputError(f"chart not found: {chart_id}")
    if not user.is_admin and stored.owner_id != user.user_id:
        raise HTTPException(status_code=403, detail="chart belongs to another user")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ChartResultDTO,
    responses={
        409: {"model": ApiError, "description": "Cross-engine conflict or needs user resolution"},
        422: {"model": ApiError, "description": "Invalid input"},
    },
)
def create_chart(
    request: dict[str, Any],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    svc: ChartService = Depends(_chart_service),
    user: CurrentUser = Depends(require_user),
) -> ChartResultDTO:
    if not idempotency_key:
        raise InvalidInputError("Idempotency-Key header is required")
    # Validate against the Pydantic model — strict mode rejects unknown fields.
    from ..dto import BirthRequest

    try:
        br = BirthRequest.model_validate(request)
    except PydanticValidationError as e:
        raise InvalidInputError(
            "birth request failed validation",
            safe_details={"errors": e.errors(include_url=False)},
        ) from e
    dto, _chart_id, _created = svc.create_chart(
        request=br, idempotency_key=f"{user.user_id}:{idempotency_key}", owner_id=user.user_id
    )
    return dto


@router.get("", response_model=list[ChartResultDTO])
def list_charts(
    svc: ChartService = Depends(_chart_service),
    user: CurrentUser = Depends(require_user),
) -> list[ChartResultDTO]:
    owner = "*" if user.is_admin else user.user_id
    return [svc.get_chart(cid) for cid in svc.list_charts(owner)]


@router.get("/{chart_id}", response_model=ChartResultDTO)
def get_chart(
    chart_id: str,
    svc: ChartService = Depends(_chart_service),
    user: CurrentUser = Depends(require_user),
) -> ChartResultDTO:
    _authorize_chart(svc, chart_id, user)
    return svc.get_chart(chart_id)


@router.get("/{chart_id}/overview-view", response_model=ChartOverviewViewDTO)
def get_chart_overview(
    chart_id: str,
    svc: ChartService = Depends(_chart_service),
    user: CurrentUser = Depends(require_user),
) -> ChartOverviewViewDTO:
    _authorize_chart(svc, chart_id, user)
    return to_chart_overview_view_dto(svc.get_chart_result(chart_id))


@router.get("/{chart_id}/temporal/{target_year}", response_model=TemporalContextViewDTO)
def get_temporal_context(
    chart_id: str,
    target_year: int,
    target_date: date | None = None,
    svc: ChartService = Depends(_chart_service),
    user: CurrentUser = Depends(require_user),
) -> TemporalContextViewDTO:
    _authorize_chart(svc, chart_id, user)
    return svc.get_temporal_context(chart_id, target_year, target_date)


@router.delete("/{chart_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chart(
    chart_id: str,
    svc: ChartService = Depends(_chart_service),
    user: CurrentUser = Depends(require_user),
) -> None:
    _authorize_chart(svc, chart_id, user)
    if not svc.delete_chart(chart_id):
        raise InvalidInputError(f"chart not found: {chart_id}")
