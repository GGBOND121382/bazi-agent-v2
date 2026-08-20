"""SQLite-backed analysis/job repository for the local toy deployment."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from ..api.dto import JobEventDTO, StructuredAnalysisDTO
from ..logging_setup import append_llm_trace
from ..persistence import connect
from .state import TRANSITIONS, AnalysisJob, JobStateError, ShareRecord


class SQLiteAnalysisStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._shares: dict[str, ShareRecord] = {}

    @staticmethod
    def _job(row: Any) -> AnalysisJob:
        return AnalysisJob(
            job_id=str(row["job_id"]),
            chart_id=str(row["chart_id"]),
            stage=str(row["stage"]),
            progress=int(row["progress"]),
            user_focus=tuple(json.loads(str(row["user_focus_json"]))),
            school=str(row["school"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            result_ref=str(row["result_ref"]) if row["result_ref"] is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
            cancel_requested=bool(row["cancel_requested"]),
        )

    def create(
        self, *, chart_id: str, user_focus: tuple[str, ...], school: str, idempotency_key: str
    ) -> tuple[AnalysisJob, bool]:
        with self._lock, connect() as conn:
            existing = conn.execute(
                "SELECT * FROM analysis_jobs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return self._job(existing), False
            job = AnalysisJob(
                job_id=f"job_{uuid.uuid4().hex[:12]}",
                chart_id=chart_id,
                stage="queued",
                progress=0,
                user_focus=user_focus,
                school=school,
                created_at=datetime.now(UTC),
            )
            conn.execute(
                """INSERT INTO analysis_jobs
                (job_id, chart_id, stage, progress, user_focus_json, school, created_at,
                 cancel_requested, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (
                    job.job_id,
                    chart_id,
                    job.stage,
                    job.progress,
                    json.dumps(user_focus, ensure_ascii=False),
                    school,
                    job.created_at.isoformat(),
                    idempotency_key,
                ),
            )
            self._append_event(conn, job, retryable=False)
            return job, True

    def get(self, job_id: str) -> AnalysisJob | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job(row) if row is not None else None

    def transition(
        self,
        job_id: str,
        *,
        stage: str,
        progress: int,
        retryable: bool = True,
        result_ref: str | None = None,
        error_code: str | None = None,
        safe_details: dict[str, Any] | None = None,
    ) -> AnalysisJob:
        with self._lock, connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise JobStateError("job not found")
            current = self._job(row)
            if stage not in TRANSITIONS[current.stage]:
                raise JobStateError(f"invalid job transition: {current.stage} -> {stage}")
            updated = replace(
                current,
                stage=stage,
                progress=progress,
                result_ref=result_ref,
                error_code=error_code,
            )
            conn.execute(
                """UPDATE analysis_jobs SET stage=?, progress=?, result_ref=?, error_code=?
                WHERE job_id=?""",
                (stage, progress, result_ref, error_code, job_id),
            )
            self._append_event(conn, updated, retryable=retryable, safe_details=safe_details)
            return updated

    def heartbeat(
        self,
        job_id: str,
        *,
        progress: int,
        safe_details: dict[str, Any] | None = None,
    ) -> AnalysisJob:
        """Persist a same-stage progress event for long streaming model calls."""
        with self._lock, connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise JobStateError("job not found")
            current = self._job(row)
            if current.stage in {"completed", "failed", "cancelled"}:
                return current
            updated = replace(current, progress=max(current.progress, progress))
            conn.execute(
                "UPDATE analysis_jobs SET progress=? WHERE job_id=?",
                (updated.progress, job_id),
            )
            self._append_event(conn, updated, retryable=True, safe_details=safe_details)
            return updated

    def request_cancel(self, job_id: str) -> AnalysisJob:
        with self._lock, connect() as conn:
            row = conn.execute("SELECT * FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise JobStateError("job not found")
            current = self._job(row)
            if current.stage in {"completed", "failed", "cancelled"}:
                raise JobStateError("job is not cancellable")
            conn.execute("UPDATE analysis_jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
        return replace(current, cancel_requested=True)

    def events_after(self, job_id: str, last_event_id: str | None) -> tuple[JobEventDTO, ...]:
        start = int(last_event_id or 0)
        with connect() as conn:
            rows = conn.execute(
                "SELECT event_json FROM job_events WHERE job_id=? AND event_no>? ORDER BY event_no",
                (job_id, start),
            ).fetchall()
            exists = conn.execute(
                "SELECT 1 FROM analysis_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if exists is None:
            raise JobStateError("job not found")
        return tuple(JobEventDTO.model_validate_json(str(row["event_json"])) for row in rows)

    def save_result(
        self,
        analysis: StructuredAnalysisDTO,
        report_view: dict[str, Any],
        generation_trace: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO analyses(analysis_id, chart_id, analysis_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    analysis.analysis_id,
                    analysis.chart_id,
                    analysis.model_dump_json(),
                    now,
                ),
            )
            conn.execute(
                """INSERT OR REPLACE INTO reports
                (report_id, chart_id, report_json, generation_trace_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    str(report_view["report_id"]),
                    str(report_view["chart_id"]),
                    json.dumps(report_view, ensure_ascii=False, default=str),
                    json.dumps(generation_trace, ensure_ascii=False, default=str)
                    if generation_trace
                    else None,
                    now,
                ),
            )
            if generation_trace:
                owner_row = conn.execute(
                    "SELECT owner_id FROM charts WHERE chart_id=?",
                    (str(report_view["chart_id"]),),
                ).fetchone()
                owner_id = str(owner_row["owner_id"]) if owner_row else "anonymous"
                call_id = f"llm_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO llm_calls
                    (call_id, owner_id, chart_id, report_id, call_type, prompt_version,
                     model_id, trace_json, created_at)
                    VALUES (?, ?, ?, ?, 'report_analysis', ?, ?, ?, ?)""",
                    (
                        call_id,
                        owner_id,
                        str(report_view["chart_id"]),
                        str(report_view["report_id"]),
                        str(generation_trace.get("prompt_version", "")),
                        str(generation_trace.get("model_id", "")),
                        json.dumps(generation_trace, ensure_ascii=False, default=str),
                        now,
                    ),
                )
                append_llm_trace({"call_id": call_id, "owner_id": owner_id, **generation_trace})

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute("SELECT report_json FROM reports WHERE report_id=?", (report_id,)).fetchone()
        return json.loads(str(row["report_json"])) if row else None

    def get_report_trace(self, report_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT generation_trace_json FROM reports WHERE report_id=?", (report_id,)
            ).fetchone()
        if row is None or row["generation_trace_json"] is None:
            return None
        parsed = json.loads(str(row["generation_trace_json"]))
        return parsed if isinstance(parsed, dict) else None

    def get_analysis(self, analysis_id: str) -> StructuredAnalysisDTO | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT analysis_json FROM analyses WHERE analysis_id=?", (analysis_id,)
            ).fetchone()
        return StructuredAnalysisDTO.model_validate_json(str(row["analysis_json"])) if row else None

    def list_reports(self) -> tuple[dict[str, Any], ...]:
        with connect() as conn:
            rows = conn.execute("SELECT report_json FROM reports ORDER BY created_at DESC").fetchall()
        return tuple(json.loads(str(row["report_json"])) for row in rows)

    def create_share(self, report_id: str, expires_at: datetime) -> tuple[ShareRecord, str]:
        if self.get_report(report_id) is None:
            raise JobStateError("report not found")
        token = secrets.token_urlsafe(32)
        record = ShareRecord(
            share_id=f"share_{uuid.uuid4().hex[:12]}",
            report_id=report_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=expires_at,
        )
        self._shares[record.share_id] = record
        return record, token

    def get_share(self, share_id: str) -> ShareRecord | None:
        return self._shares.get(share_id)

    def revoke_share(self, share_id: str) -> ShareRecord:
        record = self._shares.get(share_id)
        if record is None:
            raise JobStateError("share not found")
        updated = replace(record, revoked=True)
        self._shares[share_id] = updated
        return updated

    @staticmethod
    def _append_event(
        conn: Any,
        job: AnalysisJob,
        *,
        retryable: bool,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        row = conn.execute(
            "SELECT COALESCE(MAX(event_no), 0) AS n FROM job_events WHERE job_id=?", (job.job_id,)
        ).fetchone()
        event_no = int(row["n"]) + 1
        event = JobEventDTO(
            event_id=str(event_no),
            job_id=job.job_id,
            stage=job.stage,
            progress=job.progress,
            message_key=f"job.{job.stage}",
            occurred_at=datetime.now(UTC),
            retryable=retryable,
            safe_details=safe_details,
            result_ref=job.result_ref,
            error_code=job.error_code,
        )
        conn.execute(
            "INSERT INTO job_events(job_id, event_no, event_json) VALUES (?, ?, ?)",
            (job.job_id, event_no, event.model_dump_json()),
        )
