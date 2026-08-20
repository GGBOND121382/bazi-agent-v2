"""Thread-safe in-memory job/event/result repository for I2."""
from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from ..api.dto import JobEventDTO, StructuredAnalysisDTO

TERMINAL_STAGES = frozenset({"completed", "failed", "cancelled"})
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"calculating", "cancelled"}),
    "calculating": frozenset({"retrieving", "interpreting", "failed", "cancelled"}),
    "retrieving": frozenset({"interpreting", "failed", "cancelled"}),
    "interpreting": frozenset({"verifying", "failed", "cancelled"}),
    "verifying": frozenset({"revision_pending", "report_building", "failed", "cancelled"}),
    "revision_pending": frozenset({"interpreting", "failed", "cancelled"}),
    "report_building": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset({"queued"}),
    "cancelled": frozenset(),
}


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    job_id: str
    chart_id: str
    stage: str
    progress: int
    user_focus: tuple[str, ...]
    school: str
    created_at: datetime
    result_ref: str | None = None
    error_code: str | None = None
    cancel_requested: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "chart_id": self.chart_id,
            "stage": self.stage,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "result_ref": self.result_ref,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class ShareRecord:
    share_id: str
    report_id: str
    token_hash: str
    expires_at: datetime
    revoked: bool = False


class JobStateError(RuntimeError):
    pass


class InMemoryAnalysisStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, AnalysisJob] = {}
        self._events: dict[str, list[JobEventDTO]] = {}
        self._idempotency: dict[str, str] = {}
        self._reports: dict[str, dict[str, Any]] = {}
        self._analyses: dict[str, StructuredAnalysisDTO] = {}
        self._shares: dict[str, ShareRecord] = {}
        self._traces: dict[str, dict[str, Any]] = {}

    def create(
        self, *, chart_id: str, user_focus: tuple[str, ...], school: str, idempotency_key: str
    ) -> tuple[AnalysisJob, bool]:
        with self._lock:
            existing_id = self._idempotency.get(idempotency_key)
            if existing_id:
                return self._jobs[existing_id], False
            job = AnalysisJob(
                job_id=f"job_{uuid.uuid4().hex[:12]}",
                chart_id=chart_id,
                stage="queued",
                progress=0,
                user_focus=user_focus,
                school=school,
                created_at=datetime.now(UTC),
            )
            self._jobs[job.job_id] = job
            self._events[job.job_id] = []
            self._idempotency[idempotency_key] = job.job_id
            self._append_event(job, retryable=False)
            return job, True

    def get(self, job_id: str) -> AnalysisJob | None:
        with self._lock:
            return self._jobs.get(job_id)

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
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise JobStateError("job not found")
            if stage not in TRANSITIONS[current.stage]:
                raise JobStateError(f"invalid job transition: {current.stage} -> {stage}")
            updated = replace(
                current,
                stage=stage,
                progress=progress,
                result_ref=result_ref,
                error_code=error_code,
            )
            self._jobs[job_id] = updated
            self._append_event(updated, retryable=retryable, safe_details=safe_details)
            return updated

    def heartbeat(
        self,
        job_id: str,
        *,
        progress: int,
        safe_details: dict[str, Any] | None = None,
    ) -> AnalysisJob:
        """Persist a same-stage progress event without weakening transition rules."""
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise JobStateError("job not found")
            if current.stage in TERMINAL_STAGES:
                return current
            updated = replace(current, progress=max(current.progress, progress))
            self._jobs[job_id] = updated
            self._append_event(updated, retryable=True, safe_details=safe_details)
            return updated

    def request_cancel(self, job_id: str) -> AnalysisJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobStateError("job not found")
            if job.stage in TERMINAL_STAGES:
                raise JobStateError("job is not cancellable")
            updated = replace(job, cancel_requested=True)
            self._jobs[job_id] = updated
            return updated

    def events_after(self, job_id: str, last_event_id: str | None) -> tuple[JobEventDTO, ...]:
        with self._lock:
            events = self._events.get(job_id)
            if events is None:
                raise JobStateError("job not found")
            if last_event_id is None:
                return tuple(events)
            return tuple(event for event in events if int(event.event_id) > int(last_event_id))

    def save_result(
        self,
        analysis: StructuredAnalysisDTO,
        report_view: dict[str, Any],
        generation_trace: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._analyses[analysis.analysis_id] = analysis
            report_id = str(report_view["report_id"])
            self._reports[report_id] = report_view
            if generation_trace is not None:
                self._traces[report_id] = generation_trace

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._reports.get(report_id)

    def get_report_trace(self, report_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._traces.get(report_id)

    def get_analysis(self, analysis_id: str) -> StructuredAnalysisDTO | None:
        with self._lock:
            return self._analyses.get(analysis_id)

    def list_reports(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(self._reports.values())

    def create_share(self, report_id: str, expires_at: datetime) -> tuple[ShareRecord, str]:
        with self._lock:
            if report_id not in self._reports:
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
        with self._lock:
            record = self._shares.get(share_id)
            if record is None:
                raise JobStateError("share not found")
            updated = replace(record, revoked=True)
            self._shares[share_id] = updated
            return updated

    def _append_event(
        self,
        job: AnalysisJob,
        *,
        retryable: bool,
        safe_details: dict[str, Any] | None = None,
    ) -> None:
        events = self._events[job.job_id]
        events.append(
            JobEventDTO(
                event_id=str(len(events) + 1),
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
        )
