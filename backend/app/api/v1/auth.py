"""Minimal login and admin portal APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ...auth import (
    CurrentUser,
    authenticate,
    change_password,
    clear_session_cookie,
    create_session,
    create_user,
    list_users,
    require_admin,
    require_user,
    reset_password,
    set_session_cookie,
)
from ...persistence import connect

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=6)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str | None = Field(default=None, min_length=6)


def _public(user: CurrentUser) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role,
        "enabled": user.enabled,
        "must_change_password": user.must_change_password,
    }


@router.post("/auth/login")
def login(request: LoginRequest, response: Response) -> dict[str, object]:
    user = authenticate(request.username, request.password)
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    set_session_cookie(response, create_session(user.user_id))
    return _public(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, user: CurrentUser = Depends(require_user)) -> None:
    del user
    # FastAPI does not expose the cookie value through the dependency here; clearing
    # the browser cookie is sufficient for this local toy deployment.
    clear_session_cookie(response)


@router.get("/auth/me")
def me(user: CurrentUser = Depends(require_user)) -> dict[str, object]:
    return _public(user)


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(request: PasswordRequest, user: CurrentUser = Depends(require_user)) -> None:
    if request.password is None:
        raise ValueError("password is required")
    change_password(user.user_id, request.password)


@router.get("/admin/users")
def admin_users(admin: CurrentUser = Depends(require_admin)) -> list[dict[str, object]]:
    del admin
    return [_public(user) for user in list_users()]


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(
    request: UserCreateRequest, admin: CurrentUser = Depends(require_admin)
) -> dict[str, object]:
    del admin
    return _public(create_user(request.username, request.password))


@router.post("/admin/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def admin_reset_password(
    user_id: str, request: PasswordRequest, admin: CurrentUser = Depends(require_admin)
) -> None:
    del admin
    reset_password(user_id, request.password)


@router.get("/admin/users/{user_id}/data")
def admin_user_data(
    user_id: str, admin: CurrentUser = Depends(require_admin)
) -> dict[str, object]:
    del admin
    with connect() as conn:
        charts = [dict(row) for row in conn.execute(
            "SELECT chart_id, calculation_status, created_at, note FROM charts WHERE owner_id=? AND deleted=0 ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()]
        thread_rows = conn.execute(
            "SELECT thread_id, chart_id, title, scope, created_at, updated_at FROM chat_threads WHERE owner_id=? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        threads = []
        for row in thread_rows:
            thread = dict(row)
            messages = conn.execute(
                "SELECT role, content, payload_json, created_at FROM chat_messages WHERE thread_id=? ORDER BY created_at, rowid",
                (thread["thread_id"],),
            ).fetchall()
            thread["messages"] = [dict(message) for message in messages]
            threads.append(thread)
    return {"charts": charts, "threads": threads}
