"""Minimal cookie-session authentication for the local toy application."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Response, status

from .persistence import connect

SESSION_COOKIE = "bazi_session"


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: str
    username: str
    role: str
    enabled: bool
    must_change_password: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    resolved_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), resolved_salt, 180_000)
    return f"pbkdf2_sha256${resolved_salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, expected_hex = encoded.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    actual = _hash_password(password, salt=bytes.fromhex(salt_hex)).split("$", 2)[2]
    return hmac.compare_digest(actual, expected_hex)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_initial_admin() -> None:
    username = os.environ.get("INITIAL_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "123456")
    with connect() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        if row is not None:
            return
        conn.execute(
            """INSERT INTO users
            (user_id, username, password_hash, role, enabled, must_change_password, created_at)
            VALUES (?, ?, ?, 'admin', 1, 1, ?)""",
            (
                f"user_{uuid.uuid4().hex[:12]}",
                username,
                _hash_password(password),
                datetime.now(UTC).isoformat(),
            ),
        )


def create_user(username: str, password: str | None = None, role: str = "user") -> CurrentUser:
    username = username.strip()
    if not username or len(username) > 64:
        raise ValueError("invalid username")
    if role not in {"user", "admin"}:
        raise ValueError("invalid role")
    resolved_password = password or os.environ.get("DEFAULT_USER_PASSWORD", "123456")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    with connect() as conn:
        try:
            conn.execute(
                """INSERT INTO users
                (user_id, username, password_hash, role, enabled, must_change_password, created_at)
                VALUES (?, ?, ?, ?, 1, 1, ?)""",
                (
                    user_id,
                    username,
                    _hash_password(resolved_password),
                    role,
                    datetime.now(UTC).isoformat(),
                ),
            )
        except Exception as exc:
            raise ValueError("username already exists") from exc
    return get_user(user_id)


def get_user(user_id: str) -> CurrentUser:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("user not found")
    return CurrentUser(
        user_id=str(row["user_id"]),
        username=str(row["username"]),
        role=str(row["role"]),
        enabled=bool(row["enabled"]),
        must_change_password=bool(row["must_change_password"]),
    )


def list_users() -> list[CurrentUser]:
    with connect() as conn:
        rows = conn.execute("SELECT user_id FROM users ORDER BY created_at").fetchall()
    return [get_user(str(row["user_id"])) for row in rows]


def authenticate(username: str, password: str) -> CurrentUser | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
    if row is None or not bool(row["enabled"]):
        return None
    if not _verify_password(password, str(row["password_hash"])):
        return None
    return get_user(str(row["user_id"]))


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, now.isoformat(), (now + timedelta(days=30)).isoformat()),
        )
    return token


def delete_session(token: str | None) -> None:
    if not token:
        return
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def user_from_session(token: str | None) -> CurrentUser | None:
    if not token:
        return None
    now = datetime.now(UTC)
    with connect() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token_hash=?", (_token_hash(token),)
        ).fetchone()
        if row is None:
            return None
        if datetime.fromisoformat(str(row["expires_at"])) <= now:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
            return None
    try:
        user = get_user(str(row["user_id"]))
    except ValueError:
        return None
    return user if user.enabled else None


def require_user(
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> CurrentUser:
    if os.environ.get("BAZI_AUTH_DISABLED", "false").casefold() == "true":
        return CurrentUser("anonymous", "anonymous", "user", True, False)
    user = user_from_session(session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return user


def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return user


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def reset_password(user_id: str, password: str | None = None) -> None:
    resolved = password or os.environ.get("DEFAULT_USER_PASSWORD", "123456")
    with connect() as conn:
        result = conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=1 WHERE user_id=?",
            (_hash_password(resolved), user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    if not result.rowcount:
        raise ValueError("user not found")


def change_password(user_id: str, password: str) -> None:
    if len(password) < 6:
        raise ValueError("password must contain at least 6 characters")
    with connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=0 WHERE user_id=?",
            (_hash_password(password), user_id),
        )
