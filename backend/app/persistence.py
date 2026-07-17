"""Small SQLite persistence layer for the local toy application.

The goal is intentionally modest: one durable database file, no external
services, and schema creation on startup.  The RAG SQLite database remains
read-only and separate from this runtime database.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_LOCK = threading.RLock()
_INITIALIZED: set[Path] = set()
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_local_config() -> None:
    config = _PROJECT_ROOT / "config.local.env"
    if not config.exists():
        return
    for raw_line in config.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_local_config()


def runtime_dir() -> Path:
    configured = Path(os.environ.get("BAZI_RUNTIME_DIR", "runtime")).expanduser()
    root = configured if configured.is_absolute() else _PROJECT_ROOT / configured
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    return root


def database_path() -> Path:
    return runtime_dir() / "bazi_agent.db"


def log_dir() -> Path:
    return runtime_dir() / "logs"


def connect() -> sqlite3.Connection:
    path = database_path()
    initialize(path)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialize(path: Path | None = None) -> None:
    resolved = path or database_path()
    with _LOCK:
        if resolved in _INITIALIZED and resolved.exists():
            return
        resolved.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(resolved)
        try:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS charts (
                    chart_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    calculation_status TEXT NOT NULL,
                    chart_blob BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS chart_idempotency (
                    idempotency_key TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL REFERENCES charts(chart_id)
                );
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    user_focus_json TEXT NOT NULL,
                    school TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    result_ref TEXT,
                    error_code TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT UNIQUE
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    job_id TEXT NOT NULL,
                    event_no INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY(job_id, event_no)
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    generation_trace_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_threads (
                    thread_id TEXT PRIMARY KEY,
                    chart_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL REFERENCES chat_threads(thread_id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_calls (
                    call_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    chart_id TEXT,
                    report_id TEXT,
                    thread_id TEXT,
                    call_type TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_charts_owner ON charts(owner_id, deleted);
                CREATE INDEX IF NOT EXISTS idx_threads_owner ON chat_threads(owner_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_llm_chart ON llm_calls(chart_id, created_at);
                """
            )
            conn.commit()
        finally:
            conn.close()
        _INITIALIZED.add(resolved)
