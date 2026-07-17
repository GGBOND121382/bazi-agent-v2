"""Professional analysis core using immutable deterministic chart context."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ...adapters.llm.deepseek import ProviderResponse, StructuredOutputProvider
from ...api.dto import ChartResultDTO, StructuredAnalysisDTO, ValidationResultDTO
from ...domain.pillars import Branch, FourPillars, Pillar, Stem
from ...domain.rules.relations import evaluate_relations
from ..rag.models import EvidenceRetriever, RetrievalChannel, RetrievalPlan, RetrievedEvidence
from .context import build_analysis_context
from .professional import (
    PROFESSIONAL_RUBRIC,
    balanced_queries,
    reflection_feedback,
    reflection_requires_revision,
)
from .prompts import INTERPRETER_PROMPT_VERSION, INTERPRETER_SYSTEM_PROMPT
from .report import ReportAssembler
from .verifier import verify_analysis


class AnalysisPipelineError(RuntimeError):
    pass


_RELATION_LABELS = {
    "stem_combination": "天干五合",
    "stem_clash": "天干相冲",
    "six_combination": "六合",
    "three_combination": "三合",
    "half_combination": "半合",
    "three_meeting": "三会",
    "half_meeting": "半会",
    "clash": "六冲",
    "harm": "六害",
    "break": "相破",
    "punishment": "相刑",
}
_REVISION_GUIDANCE = {
    "UNKNOWN_FACT": "fact_ids 只能使用确定性上下文中的事实 ID。",
    "UNKNOWN_RULE": "rule_ids 只能使用输入中的规则或 A/B 级证据 ID。",
    "UNKNOWN_EVIDENCE": "evidence_ids 只能使用 retrieved_evidence 中的 ID。",
    "MISSING_INTERPRETIVE_SUPPORT": "补充有效规则/证据；无依据时删除判断。",
    "NON_AUTHORITATIVE_RULE": "C 级案例只能作为 evidence_ids。",
    "CLAIM_SCHOOL_MISMATCH": "claim.school 与分析流派保持一致。",
    "POLICY_HIGH_RISK_ASSERTION": "改为条件、趋势和风险提示。",
}


def _relations(chart: ChartResultDTO) -> list[dict[str, Any]]:
    by_position = {item.position: item for item in chart.pillars}

    def pillar(position: Literal["year", "month", "day", "hour"]) -> Pillar:
        item = by_position[position]
        return Pillar(Stem(item.stem), Branch(item.branch))

    pillars = FourPillars(
        year=pillar("year"),
        month=pillar("month"),
        day=pillar("day"),
        hour=pillar("hour"),
    )
    return [
        {
            "fact_id": f"RELATION-{index:02d}",
            "type": relation.type,
            "branches": list(relation.branches),
            "element": relation.element,
            "rule_id": relation.rule_id,
            "support_query": ("天干" if relation.type.startswith("stem_") else "地支")
            + "".join(relation.branches)
            + _RELATION_LABELS.get(relation.type, relation.type),
        }
        for index, relation in enumerate(evaluate_relations(pillars), start=1)
    ]


def _shensha(chart: ChartResultDTO) -> list[dict[str, Any]]:
    details = chart.calendar.get("deterministic_details", {})
    raw = details.get("shensha", []) if isinstance(details, dict) else []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _serialize(item: RetrievedEvidence) -> dict[str, Any]:
    return {
        "evidence_id": item.chunk_id,
        "source_id": item.source_id,
        "content": item.content,
        "citation": item.citation,
        "channel": item.channel.value,
        "collection": item.collection,
        "trust_tier": item.trust_tier,
        "permissions": {
            "can_support_claim": item.can_support_claim,
            "can_support_case_analogy": item.can_support_case_analogy,
            "can_supply_explanation": item.can_supply_explanation,
        },
    }


def _salvage(
    *,
    chart: ChartResultDTO,
    evidence: tuple[RetrievedEvidence, ...],
    analysis: StructuredAnalysisDTO,
    validation: ValidationResultDTO,
    school: str,
    relations: list[dict[str, Any]],
) -> tuple[StructuredAnalysisDTO, ValidationResultDTO]:
    if validation.status == "passed":
        return analysis, validation
    if any(not error.get("claim_id") for error in validation.errors):
        return analysis, validation
    rejected = {str(e["claim_id"]) for e in validation.errors if e.get("claim_id")}
    remaining = [claim for claim in analysis.claims if claim.claim_id not in rejected]
    if not rejected or not remaining:
        return analysis, validation
    cleaned = analysis.model_copy(update={"claims": remaining})
    return cleaned, verify_analysis(
        chart=chart,
        evidence=evidence,
        analysis=cleaned,
        configured_school=school,
        computed_relations=relations,
    )


@dataclass(frozen=True, slots=True)
class AnalysisPipelineResult:
    analysis: StructuredAnalysisDTO
    validation: ValidationResultDTO
    evidence: tuple[RetrievedEvidence, ...]
    report: dict[str, Any] | None
    retrieval_trace_id: str
    model_id: str
    prompt_version: str


class AnalysisPipeline:
    def __init__(self, *, provider: StructuredOutputProvider, retriever: EvidenceRetriever) -> None:
        self.provider = provider
        self.retriever = retriever
        self.report_assembler = ReportAssembler()

    def run(
        self,
        *,
        chart: ChartResultDTO,
        user_focus: tuple[str, ...],
        school: str = "engineering_policy",
        on_stage: Callable[[str], None] | None = None,
        max_revisions: int = 2,
    ) -> AnalysisPipelineResult:
        if chart.calculation_status != "passed":
            raise AnalysisPipelineError("analysis requires calculation_status=passed")
        if not user_focus or len(user_focus) > 8:
            raise AnalysisPipelineError("user_focus must contain 1 to 8 topics")

        trace_id = f"retrieval_{uuid.uuid4().hex[:12]}"
        relations = _relations(chart)
        shensha = _shensha(chart)
        context = build_analysis_context(
            chart=chart,
            computed_relations=relations,
            computed_shensha=shensha,
        )
        plan = RetrievalPlan(
            queries=balanced_queries(chart, relations, shensha, user_focus),
            school=school,
            task_type="interpretation",
            top_k=20,
            case_top_k=4,
            explanation_top_k=6,
        )
        if on_stage:
            on_stage("retrieving")
        evidence = self.retriever.retrieve(plan)
        if not evidence:
            raise AnalysisPipelineError("approved evidence is required")

        schema_path = (
            Path(__file__).resolve().parents[4]
            / "contracts"
            / "schemas"
            / "analysis_output.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        grouped = {
            channel.value: [
                _serialize(item) for item in evidence if item.channel is channel
            ]
            for channel in RetrievalChannel
        }
        grouped["conflicting_evidence"] = []
        payload: dict[str, Any] = {
            "chart_id": chart.chart_id,
            "calculation_profile_id": chart.calculation_profile_id,
            "analysis_context": context,
            "retrieved_evidence": [_serialize(item) for item in evidence],
            "retrieval_context": grouped,
            "retrieval_policy": {
                "deterministic_engine_overrides_rag": True,
                "rule_claims_require_trust_tier": ["A", "B"],
                "c_tier_is_explanation_or_historical_analogy_only": True,
                "every_claim_requires_rule_or_evidence": True,
            },
            "analysis_profile": {
                "school": school,
                "primary_method": "ziping_structure_first",
                "supporting_methods": [
                    "seasonal_strength",
                    "tiao_hou",
                    "pattern",
                    "bing_yao",
                    "tong_guan",
                ],
                "nayin_role": "secondary_only",
                "shensha_role": "auxiliary_only",
            },
            "professional_rubric": PROFESSIONAL_RUBRIC,
            "user_focus": list(user_focus),
        }

        response: ProviderResponse | None = None
        analysis: StructuredAnalysisDTO | None = None
        validation: ValidationResultDTO | None = None
        for attempt in range(max_revisions + 1):
            if on_stage:
                on_stage("interpreting")
            response = self.provider.complete_json(
                system_prompt=INTERPRETER_SYSTEM_PROMPT,
                input_payload=payload,
                schema=schema,
                prompt_version=INTERPRETER_PROMPT_VERSION,
            )
            try:
                analysis = StructuredAnalysisDTO.model_validate(response.payload)
            except ValueError as exc:
                raise AnalysisPipelineError(
                    "provider output violates analysis schema"
                ) from exc
            if on_stage:
                on_stage("verifying")
            validation = verify_analysis(
                chart=chart,
                evidence=evidence,
                analysis=analysis,
                configured_school=school,
                computed_relations=relations,
            )
            reflection_failed = reflection_requires_revision(analysis)
            if (
                validation.status == "passed" and not reflection_failed
            ) or attempt == max_revisions:
                break
            if on_stage:
                on_stage("revision_pending")
            payload = {
                **payload,
                "previous_analysis": analysis.model_dump(mode="json"),
                "reflection_feedback": reflection_feedback(analysis),
                "required_revisions": validation.required_revisions,
                "validation_errors": validation.errors,
                "revision_guidance": [
                    _REVISION_GUIDANCE.get(code, code)
                    for code in validation.required_revisions
                ],
            }

        assert response is not None and analysis is not None and validation is not None
        analysis, validation = _salvage(
            chart=chart,
            evidence=evidence,
            analysis=analysis,
            validation=validation,
            school=school,
            relations=relations,
        )
        report = None
        if validation.status == "passed":
            if on_stage:
                on_stage("report_building")
            report = self.report_assembler.assemble(
                chart=chart,
                analysis=analysis,
                validation=validation,
                evidence=evidence,
                prompt_version=response.prompt_version,
                model_id=response.model_id,
                retrieval_trace_id=trace_id,
            )
        return AnalysisPipelineResult(
            analysis=analysis,
            validation=validation,
            evidence=evidence,
            report=report,
            retrieval_trace_id=trace_id,
            model_id=response.model_id,
            prompt_version=response.prompt_version,
        )
