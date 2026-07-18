"""Analysis job orchestration, cancellation, SSE persistence, and report mapping."""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from ..adapters.llm import DeepSeekProvider, ModelProviderError
from ..services.agent import AnalysisPipeline, AnalysisPipelineError
from ..services.chart_service import ChartService, get_default_service
from .sqlite_store import SQLiteAnalysisStore
from .state import TERMINAL_STAGES, AnalysisJob, InMemoryAnalysisStore, JobStateError

logger = logging.getLogger(__name__)


class JobCancelled(RuntimeError):
    pass


_PROGRESS = {
    "calculating": 10,
    "retrieving": 30,
    "interpreting": 55,
    "verifying": 75,
    "revision_pending": 78,
    "report_building": 90,
}


class AnalysisJobService:
    def __init__(
        self,
        *,
        chart_service: ChartService,
        pipeline_factory: Callable[[], AnalysisPipeline],
        store: InMemoryAnalysisStore | SQLiteAnalysisStore | None = None,
    ) -> None:
        self.chart_service = chart_service
        self.pipeline_factory = pipeline_factory
        self.store = store or InMemoryAnalysisStore()

    def start(
        self,
        *,
        chart_id: str,
        user_focus: tuple[str, ...],
        school: str,
        idempotency_key: str,
        run_async: bool = True,
    ) -> AnalysisJob:
        chart = self.chart_service.get_chart(chart_id)
        if chart.calculation_status != "passed":
            raise JobStateError("chart is not validated")
        job, created = self.store.create(
            chart_id=chart_id,
            user_focus=user_focus,
            school=school,
            idempotency_key=idempotency_key,
        )
        if created:
            if run_async:
                threading.Thread(target=self.process, args=(job.job_id,), daemon=True).start()
            else:
                self.process(job.job_id)
        return job

    def process(self, job_id: str) -> None:  # noqa: PLR0915
        job = self.require(job_id)
        try:
            self.store.transition(job_id, stage="calculating", progress=_PROGRESS["calculating"])
            chart = self.chart_service.get_chart(job.chart_id)

            def on_stage(stage: str) -> None:
                current = self.require(job_id)
                if current.cancel_requested:
                    raise JobCancelled
                self.store.transition(
                    job_id, stage=stage, progress=max(current.progress, _PROGRESS[stage])
                )

            last_model_event_at = 0.0
            last_model_progress = _PROGRESS["interpreting"]
            last_model_phase = ""

            def on_model_progress(event: dict[str, object]) -> None:
                nonlocal last_model_event_at, last_model_progress, last_model_phase
                current = self.require(job_id)
                if current.cancel_requested:
                    raise JobCancelled
                phase = str(event.get("phase", "reasoning"))
                reasoning_value = event.get("reasoning_chars", 0)
                content_value = event.get("content_chars", 0)
                reasoning_chars = reasoning_value if isinstance(reasoning_value, int) else 0
                content_chars = content_value if isinstance(content_value, int) else 0
                revision_call = current.progress >= _PROGRESS["revision_pending"]
                if revision_call:
                    if phase == "answering" or content_chars:
                        target = min(88, 84 + content_chars // 1200)
                    elif phase == "reasoning":
                        target = min(84, 79 + reasoning_chars // 900)
                    else:
                        target = max(last_model_progress, 78)
                elif phase == "answering" or content_chars:
                    target = min(73, 65 + content_chars // 1800)
                elif phase == "reasoning":
                    target = min(65, 56 + reasoning_chars // 1200)
                else:
                    target = max(last_model_progress, 55)
                target = max(current.progress, last_model_progress, target)
                now = time.monotonic()
                important = phase != last_model_phase or phase in {"retrying", "completed"}
                if not important and target == last_model_progress and now - last_model_event_at < 2.0:
                    return
                if current.stage != "interpreting":
                    return
                self.store.heartbeat(
                    job_id,
                    progress=target,
                    safe_details={
                        "provider_phase": phase,
                        "attempt": event.get("attempt"),
                        "reasoning_chars": reasoning_chars,
                        "content_chars": content_chars,
                    },
                )
                last_model_event_at = now
                last_model_progress = target
                last_model_phase = phase

            result = self.pipeline_factory().run(
                chart=chart,
                user_focus=job.user_focus,
                school=job.school,
                on_stage=on_stage,
                on_model_progress=on_model_progress,
                max_revisions=2,
            )
            if result.validation.status != "passed" or result.report is None:
                self.store.transition(
                    job_id,
                    stage="failed",
                    progress=self.require(job_id).progress,
                    retryable=False,
                    error_code="ANALYSIS_VALIDATION_FAILED",
                    safe_details={
                        "required_revisions": result.validation.required_revisions,
                        "validation_errors": result.validation.errors,
                    },
                )
                return
            report_view = _to_report_view(result.report)
            self.store.save_result(result.analysis, report_view, result.generation_trace)
            self.store.transition(
                job_id,
                stage="completed",
                progress=100,
                retryable=False,
                result_ref=str(report_view["report_id"]),
            )
        except JobCancelled:
            current = self.require(job_id)
            if current.stage not in TERMINAL_STAGES:
                self.store.transition(
                    job_id, stage="cancelled", progress=current.progress, retryable=False
                )
        except ModelProviderError as exc:
            logger.warning("analysis_model_failed job_id=%s code=%s", job_id, exc.error_code, exc_info=True)
            current = self.require(job_id)
            if current.stage not in TERMINAL_STAGES:
                self.store.transition(
                    job_id,
                    stage="failed",
                    progress=current.progress,
                    retryable=exc.retryable,
                    error_code=exc.error_code,
                    safe_details={"provider_error": exc.error_code},
                )
        except AnalysisPipelineError as exc:
            logger.warning("analysis_pipeline_failed job_id=%s", job_id, exc_info=True)
            current = self.require(job_id)
            if current.stage not in TERMINAL_STAGES:
                self.store.transition(
                    job_id,
                    stage="failed",
                    progress=current.progress,
                    retryable=False,
                    error_code="ANALYSIS_VALIDATION_FAILED",
                    safe_details=exc.safe_details,
                )
        except Exception:
            logger.exception("analysis_job_failed job_id=%s", job_id)
            current = self.require(job_id)
            if current.stage not in TERMINAL_STAGES:
                self.store.transition(
                    job_id,
                    stage="failed",
                    progress=current.progress,
                    retryable=True,
                    error_code="INTERNAL_ERROR",
                )

    def cancel(self, job_id: str) -> AnalysisJob:
        return self.store.request_cancel(job_id)

    def require(self, job_id: str) -> AnalysisJob:
        job = self.store.get(job_id)
        if job is None:
            raise JobStateError("job not found")
        return job


def _to_report_view(report: dict[str, object]) -> dict[str, object]:
    sections = report["sections"]
    assert isinstance(sections, list)
    blocks: list[dict[str, object]] = []
    toc: list[dict[str, object]] = []
    for section in sections:
        assert isinstance(section, dict)
        section_id = str(section["section_id"])
        toc.append({"anchor": section_id, "title": str(section["title"]), "level": 1})
        blocks.append(
            {
                "block_id": f"heading-{section_id}",
                "block_type": "heading",
                "anchor": section_id,
                "text": str(section["title"]),
                "level": 1,
            }
        )
        for item in section["content_blocks"]:
            assert isinstance(item, dict)
            blocks.append(
                {
                    "block_id": str(item["claim_id"]),
                    "block_type": "claim",
                    "title": str(item["topic"]),
                    "summary": str(item["statement"]),
                    "confidence": item["confidence"],
                    "fact_ids": item["fact_ids"],
                    "rule_ids": item["rule_ids"],
                    "evidence_ids": item["evidence_ids"],
                    "counterevidence": item["counterevidence"],
                }
            )
    metadata = report["metadata"]
    assumptions = report["calculation_assumptions"]
    assert isinstance(metadata, dict) and isinstance(assumptions, dict)
    return {
        "schema_version": "report-view-v1",
        "report_id": report["report_id"],
        "chart_id": report["chart_id"],
        "title": "结构化命理分析报告",
        "generated_at": metadata["generated_at"],
        "calculation_profile_label": assumptions["calculation_profile_id"],
        "toc": toc,
        "blocks": blocks,
        "citations": report["citations"],
        "limitations": report["limitations"],
    }


def default_pipeline() -> AnalysisPipeline:
    return AnalysisPipeline(provider=DeepSeekProvider())


_DEFAULT = AnalysisJobService(
    chart_service=get_default_service(),
    pipeline_factory=default_pipeline,
    store=SQLiteAnalysisStore(),
)


def get_default_analysis_service() -> AnalysisJobService:
    return _DEFAULT
