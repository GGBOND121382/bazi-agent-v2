"""Login, approval-based registration, password and admin APIs."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ...auth import (
    SESSION_COOKIE,
    CurrentUser,
    approve_user,
    authenticate,
    change_password,
    clear_session_cookie,
    create_session,
    create_user,
    delete_session,
    list_users,
    register_user,
    reject_user,
    require_admin,
    require_user,
    reset_password,
    set_session_cookie,
)
from ...persistence import connect

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(default="123456", min_length=6, max_length=128)


def _public(user: CurrentUser) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "enabled": user.enabled,
        "approval_status": user.approval_status,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: UserCreateRequest) -> dict[str, object]:
    try:
        return _public(register_user(request.username, request.password))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/auth/login")
def login(request: LoginRequest, response: Response) -> dict[str, object]:
    user, reason = authenticate(request.username, request.password)
    if user is None:
        messages = {
            "pending_approval": "registration is pending administrator approval",
            "registration_rejected": "registration was rejected",
            "account_disabled": "account is disabled",
        }
        code = status.HTTP_403_FORBIDDEN if reason in messages else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(status_code=code, detail=messages.get(reason, "invalid credentials"))
    set_session_cookie(response, create_session(user.user_id))
    return _public(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    delete_session(session)
    clear_session_cookie(response)


@router.get("/auth/me")
def me(user: CurrentUser = Depends(require_user)) -> dict[str, object]:
    return _public(user)


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(
    request: ChangePasswordRequest,
    response: Response,
    user: CurrentUser = Depends(require_user),
) -> None:
    try:
        change_password(user.user_id, request.current_password, request.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    clear_session_cookie(response)


@router.get("/admin/users")
def admin_users(admin: CurrentUser = Depends(require_admin)) -> list[dict[str, object]]:
    del admin
    return [_public(user) for user in list_users()]


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(
    request: UserCreateRequest, admin: CurrentUser = Depends(require_admin)
) -> dict[str, object]:
    try:
        return _public(
            create_user(
                request.username,
                request.password,
                approved_by=admin.user_id,
                must_change_password=True,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/admin/users/{user_id}/approve")
def admin_approve_user(
    user_id: str, admin: CurrentUser = Depends(require_admin)
) -> dict[str, object]:
    try:
        return _public(approve_user(user_id, admin.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/admin/users/{user_id}/reject")
def admin_reject_user(
    user_id: str, admin: CurrentUser = Depends(require_admin)
) -> dict[str, object]:
    try:
        return _public(reject_user(user_id, admin.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/admin/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def admin_reset_password(
    user_id: str, request: PasswordRequest, admin: CurrentUser = Depends(require_admin)
) -> None:
    del admin
    try:
        reset_password(user_id, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/admin/users/{user_id}/data")
def admin_user_data(
    user_id: str, admin: CurrentUser = Depends(require_admin)
) -> dict[str, object]:
    del admin
    with connect() as conn:
        charts = [
            dict(row)
            for row in conn.execute(
                """SELECT chart_id, calculation_status, created_at, note
                FROM charts WHERE owner_id=? AND deleted=0 ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
        ]
        reports = [
            dict(row)
            for row in conn.execute(
                """SELECT r.report_id, r.chart_id, r.created_at
                FROM reports r JOIN charts c ON c.chart_id=r.chart_id
                WHERE c.owner_id=? ORDER BY r.created_at DESC""",
                (user_id,),
            ).fetchall()
        ]
        thread_rows = conn.execute(
            """SELECT thread_id, chart_id, title, scope, created_at, updated_at
            FROM chat_threads WHERE owner_id=? ORDER BY updated_at DESC""",
            (user_id,),
        ).fetchall()
        threads = []
        for row in thread_rows:
            thread = dict(row)
            messages = conn.execute(
                """SELECT role, content, payload_json, created_at FROM chat_messages
                WHERE thread_id=? ORDER BY created_at, rowid""",
                (thread["thread_id"],),
            ).fetchall()
            thread["messages"] = [dict(message) for message in messages]
            threads.append(thread)
    return {"charts": charts, "reports": reports, "threads": threads}
