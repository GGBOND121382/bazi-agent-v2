"""Small local account system with approval-based registration."""
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
APPROVED = "approved"
PENDING = "pending"
REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: str
    username: str
    role: str
    enabled: bool
    approval_status: str
    must_change_password: bool
    created_at: str

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


def _validate_password(password: str) -> None:
    if len(password) < 6:
        raise ValueError("password must contain at least 6 characters")
    if len(password) > 128:
        raise ValueError("password is too long")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _row_to_user(row: object) -> CurrentUser:
    return CurrentUser(
        user_id=str(row["user_id"]),  # type: ignore[index]
        username=str(row["username"]),  # type: ignore[index]
        role=str(row["role"]),  # type: ignore[index]
        enabled=bool(row["enabled"]),  # type: ignore[index]
        approval_status=str(row["approval_status"]),  # type: ignore[index]
        must_change_password=bool(row["must_change_password"]),  # type: ignore[index]
        created_at=str(row["created_at"]),  # type: ignore[index]
    )


def ensure_initial_accounts() -> None:
    """Create the local admin and one approved demo user on a fresh database."""
    admin_name = os.environ.get("INITIAL_ADMIN_USERNAME", "admin").strip() or "admin"
    admin_password = os.environ.get("INITIAL_ADMIN_PASSWORD", "wsxqaz@123")
    demo_name = os.environ.get("INITIAL_DEMO_USERNAME", "user123").strip() or "user123"
    demo_password = os.environ.get("INITIAL_DEMO_PASSWORD", "123456")
    now = datetime.now(UTC).isoformat()
    with connect() as conn:
        admin = conn.execute("SELECT user_id FROM users WHERE username=?", (admin_name,)).fetchone()
        if admin is None:
            admin_id = f"user_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO users
                (user_id, username, password_hash, role, enabled, approval_status,
                 approved_at, approved_by, must_change_password, created_at)
                VALUES (?, ?, ?, 'admin', 1, 'approved', ?, ?, 1, ?)""",
                (admin_id, admin_name, _hash_password(admin_password), now, admin_id, now),
            )
        demo = conn.execute("SELECT user_id FROM users WHERE username=?", (demo_name,)).fetchone()
        if demo is None:
            conn.execute(
                """INSERT INTO users
                (user_id, username, password_hash, role, enabled, approval_status,
                 approved_at, approved_by, must_change_password, created_at)
                VALUES (?, ?, ?, 'user', 1, 'approved', ?, ?, 1, ?)""",
                (
                    f"user_{uuid.uuid4().hex[:12]}",
                    demo_name,
                    _hash_password(demo_password),
                    now,
                    "system",
                    now,
                ),
            )


def create_user(
    username: str,
    password: str,
    *,
    role: str = "user",
    approval_status: str = APPROVED,
    approved_by: str | None = None,
    must_change_password: bool = False,
) -> CurrentUser:
    username = username.strip()
    if not username or len(username) > 64:
        raise ValueError("invalid username")
    if role not in {"user", "admin"}:
        raise ValueError("invalid role")
    if approval_status not in {APPROVED, PENDING, REJECTED}:
        raise ValueError("invalid approval status")
    _validate_password(password)
    now = datetime.now(UTC).isoformat()
    enabled = approval_status == APPROVED
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    with connect() as conn:
        try:
            conn.execute(
                """INSERT INTO users
                (user_id, username, password_hash, role, enabled, approval_status,
                 approved_at, approved_by, must_change_password, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    username,
                    _hash_password(password),
                    role,
                    int(enabled),
                    approval_status,
                    now if enabled else None,
                    approved_by,
                    int(must_change_password),
                    now,
                ),
            )
        except Exception as exc:
            raise ValueError("username already exists") from exc
    return get_user(user_id)


def register_user(username: str, password: str) -> CurrentUser:
    return create_user(
        username,
        password,
        approval_status=PENDING,
        must_change_password=False,
    )


def get_user(user_id: str) -> CurrentUser:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("user not found")
    return _row_to_user(row)


def get_user_by_username(username: str) -> CurrentUser | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
    return _row_to_user(row) if row is not None else None


def list_users() -> list[CurrentUser]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return [_row_to_user(row) for row in rows]


def authenticate(username: str, password: str) -> tuple[CurrentUser | None, str | None]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
    if row is None or not _verify_password(password, str(row["password_hash"])):
        return None, "invalid_credentials"
    user = _row_to_user(row)
    if user.approval_status == PENDING:
        return None, "pending_approval"
    if user.approval_status == REJECTED:
        return None, "registration_rejected"
    if not user.enabled:
        return None, "account_disabled"
    return user, None


def approve_user(user_id: str, admin_id: str) -> CurrentUser:
    now = datetime.now(UTC).isoformat()
    with connect() as conn:
        result = conn.execute(
            """UPDATE users SET approval_status='approved', enabled=1,
            approved_at=?, approved_by=? WHERE user_id=? AND role!='admin'""",
            (now, admin_id, user_id),
        )
    if not result.rowcount:
        raise ValueError("user not found")
    return get_user(user_id)


def reject_user(user_id: str, admin_id: str) -> CurrentUser:
    with connect() as conn:
        result = conn.execute(
            """UPDATE users SET approval_status='rejected', enabled=0, approved_at=NULL,
            approved_by=? WHERE user_id=? AND role!='admin'""",
            (admin_id, user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    if not result.rowcount:
        raise ValueError("user not found")
    return get_user(user_id)


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
    return user if user.enabled and user.approval_status == APPROVED else None


def require_user(
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> CurrentUser:
    if os.environ.get("BAZI_AUTH_DISABLED", "false").casefold() == "true":
        return CurrentUser("anonymous", "anonymous", "user", True, APPROVED, False, "")
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


def reset_password(user_id: str, password: str = "123456") -> None:
    _validate_password(password)
    with connect() as conn:
        result = conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=1 WHERE user_id=?",
            (_hash_password(password), user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    if not result.rowcount:
        raise ValueError("user not found")


def change_password(user_id: str, current_password: str, new_password: str) -> None:
    _validate_password(new_password)
    with connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("user not found")
        if not _verify_password(current_password, str(row["password_hash"])):
            raise ValueError("current password is incorrect")
        conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=0 WHERE user_id=?",
            (_hash_password(new_password), user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
