import pytest
from fastapi import HTTPException

from app import auth


def _user(user_id: str, role: str = "user") -> auth.CurrentUser:
    return auth.CurrentUser(
        user_id=user_id,
        username=user_id,
        role=role,
        enabled=True,
        approval_status=auth.APPROVED,
        must_change_password=False,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_require_user_accepts_matching_expected_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BAZI_AUTH_DISABLED", raising=False)
    monkeypatch.setattr(auth, "user_from_session", lambda _token: _user("user-a"))

    resolved = auth.require_user("session-token", "user-a")

    assert resolved.user_id == "user-a"


def test_require_user_rejects_when_browser_cookie_switched_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BAZI_AUTH_DISABLED", raising=False)
    monkeypatch.setattr(auth, "user_from_session", lambda _token: _user("admin-a", "admin"))

    with pytest.raises(HTTPException) as exc_info:
        auth.require_user("session-token", "user-a")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "session identity changed; login again"


def test_auth_disabled_cannot_override_authenticated_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BAZI_AUTH_DISABLED", "true")
    monkeypatch.setattr(auth, "user_from_session", lambda _token: _user("user-a"))

    resolved = auth.require_user("session-token", "user-a")

    assert resolved.user_id == "user-a"
    assert resolved.username == "user-a"


def test_auth_disabled_still_checks_authenticated_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BAZI_AUTH_DISABLED", "true")
    monkeypatch.setattr(auth, "user_from_session", lambda _token: _user("admin-a", "admin"))

    with pytest.raises(HTTPException) as exc_info:
        auth.require_user("session-token", "user-a")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "session identity changed; login again"


def test_auth_disabled_keeps_legacy_anonymous_mode_only_without_browser_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BAZI_AUTH_DISABLED", "true")
    monkeypatch.setattr(auth, "user_from_session", lambda _token: None)

    resolved = auth.require_user(None, None)

    assert resolved.user_id == "anonymous"
    assert resolved.role == "user"
