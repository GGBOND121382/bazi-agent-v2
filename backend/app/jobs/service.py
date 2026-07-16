"""Analysis job orchestration, cancellation, SSE persistence, and report mapping."""
from __future__ import annotations

import threading
from collections.abc import Callable

from ..adapters.llm import DeepSeekProvider
from ..services.agent import AnalysisPipeline
from ..services.chart_service import ChartService, get_default_service
from ..services.rag import DatasetV2Retriever
from .state import TERMINAL_STAGES, AnalysisJob, InMemoryAnalysisStore, JobStateError


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
        store: InMemoryAnalysisStore | None = None,
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

    def process(self, job_id: str) -> None:
        job = self.require(job_id)
        try:
            self.store.transition(job_id, stage="calculating", progress=_PROGRESS["calculating"])
            chart = self.chart_service.get_chart(job.chart_id)

            def on_stage(stage: str) -> None:
                current = self.require(job_id)
                if current.cancel_requested:
                    raise JobCancelled
                self.store.transition(job_id, stage=stage, progress=_PROGRESS[stage])

            result = self.pipeline_factory().run(
                chart=chart,
                user_focus=job.user_focus,
                school=job.school,
                on_stage=on_stage,
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
            self.store.save_result(result.analysis, report_view)
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
        except Exception:
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
    return AnalysisPipeline(provider=DeepSeekProvider(), retriever=DatasetV2Retriever())


_DEFAULT = AnalysisJobService(
    chart_service=get_default_service(),
    pipeline_factory=default_pipeline,
)


def get_default_analysis_service() -> AnalysisJobService:
    return _DEFAULT
