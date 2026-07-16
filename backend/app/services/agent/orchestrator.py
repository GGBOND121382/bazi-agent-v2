"""A2 synchronous core. I2 wraps this in a cancellable job/SSE surface."""
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
from .prompts import INTERPRETER_PROMPT_VERSION, INTERPRETER_SYSTEM_PROMPT
from .report import ReportAssembler
from .verifier import verify_analysis


class AnalysisPipelineError(RuntimeError):
    pass


_RELATION_LABELS = {
    "six_combination": "六合",
    "three_combination": "三合",
    "three_meeting": "三会",
    "clash": "六冲",
    "harm": "六害",
    "break": "相破",
    "punishment": "相刑",
}

_REVISION_GUIDANCE = {
    "UNKNOWN_FACT": "fact_ids 只能使用输入 chart_facts 或 computed_relations 中逐字一致的 fact_id；删除任何自行编造的 id。",
    "UNKNOWN_RULE": "rule_ids 只能使用输入 chart_facts、computed_relations 或 A/B 级 authoritative_evidence 中逐字一致的 rule_id/evidence_id。",
    "UNKNOWN_EVIDENCE": "evidence_ids 只能使用 retrieved_evidence 中逐字一致的 evidence_id；无可用证据时删除该 claim。",
    "ASSERTION_TOO_DETERMINISTIC": "每个 claim.statement 必须包含原文短语“在本规则体系下”或“传统命理”。",
    "FACTUAL_TOKEN_MISMATCH": "删除未被所引 fact_id、computed_relations 或 A/B rule_id 明确支持的干支字符。",
    "MISSING_INTERPRETIVE_SUPPORT": "每个 claim 至少引用一个有效 rule_id 或 evidence_id；没有依据的结论必须删除。",
    "NON_AUTHORITATIVE_RULE": "C 级材料只能放入 evidence_ids；rule_ids 只能使用命盘/关系规则或 A/B 级 chunk id。",
    "CASE_ANALOGY_NOT_QUALIFIED": "引用历史案例时明确写出“历史案例仅作类比，不代表当前用户必然发生同类结果”。",
    "CLAIM_SCHOOL_MISMATCH": "claim.school 必须与 analysis_profile.school 一致，或省略 claim.school。",
    "POLICY_HIGH_RISK_ASSERTION": "删除医疗、法律、投资等高风险确定性结论；不能通过改写为婉转表达来保留该结论。",
}


def _salvage_valid_claims(
    *,
    chart: ChartResultDTO,
    evidence: tuple[RetrievedEvidence, ...],
    analysis: StructuredAnalysisDTO,
    validation: ValidationResultDTO,
    configured_school: str,
    computed_relations: list[dict[str, Any]],
) -> tuple[StructuredAnalysisDTO, ValidationResultDTO]:
    """Drop only claim-scoped failures, then re-run the full deterministic gate.

    Global validation failures are never recoverable here. An empty analysis is
    also rejected, so this cannot turn a wholly invalid model response into a
    formal report.
    """
    if validation.status == "passed":
        return analysis, validation
    if any(not error.get("claim_id") for error in validation.errors):
        return analysis, validation
    rejected_claim_ids = {
        str(error["claim_id"])
        for error in validation.errors
        if error.get("claim_id")
    }
    remaining_claims = [
        claim for claim in analysis.claims if claim.claim_id not in rejected_claim_ids
    ]
    if not rejected_claim_ids or not remaining_claims:
        return analysis, validation
    codes = ", ".join(validation.required_revisions)
    salvaged = analysis.model_copy(
        update={
            "claims": remaining_claims,
            "limitations": [
                *analysis.limitations,
                f"已排除 {len(rejected_claim_ids)} 条未通过确定性校验的解释（{codes}）。",
            ],
        }
    )
    salvaged_validation = verify_analysis(
        chart=chart,
        evidence=evidence,
        analysis=salvaged,
        configured_school=configured_school,
        computed_relations=computed_relations,
    )
    return salvaged, salvaged_validation


def _computed_relations(chart: ChartResultDTO) -> list[dict[str, Any]]:
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
            "support_query": "地支"
            + "".join(relation.branches)
            + _RELATION_LABELS.get(relation.type, relation.type),
        }
        for index, relation in enumerate(evaluate_relations(pillars), start=1)
    ]


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
        retrieval_trace_id = f"retrieval_{uuid.uuid4().hex[:12]}"
        computed_relations = _computed_relations(chart)
        stem_queries = tuple(
            dict.fromkeys(f"{chart.day_master}日主见{pillar.stem}" for pillar in chart.pillars)
        )
        branch_queries = tuple(
            dict.fromkeys(f"地支{pillar.branch}的藏干" for pillar in chart.pillars)
        )
        relation_queries = tuple(
            str(relation["support_query"]) for relation in computed_relations
        )
        chart_queries = stem_queries + branch_queries + relation_queries
        # Chart-derived terms come first so a long focus list cannot crowd the
        # authoritative A/B lookup out of the bounded FTS expression.
        plan = RetrievalPlan(queries=chart_queries + user_focus, school=school, top_k=8)
        if on_stage:
            on_stage("retrieving")
        evidence = self.retriever.retrieve(plan)
        if not evidence:
            raise AnalysisPipelineError("approved evidence is required")
        schema_path = Path(__file__).resolve().parents[4] / "contracts" / "schemas" / "analysis_output.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        def serialize_evidence(item: RetrievedEvidence) -> dict[str, Any]:
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

        grouped_evidence = {
            channel.value: [
                serialize_evidence(item) for item in evidence if item.channel is channel
            ]
            for channel in RetrievalChannel
        }
        grouped_evidence["conflicting_evidence"] = []
        input_payload: dict[str, Any] = {
                "chart_id": chart.chart_id,
                "calculation_profile_id": chart.calculation_profile_id,
                "chart_facts": [fact.model_dump(mode="json") for fact in chart.facts],
                "chart_structure": [
                    pillar.model_dump(mode="json") for pillar in chart.pillars
                ],
                "computed_relations": computed_relations,
                "retrieved_evidence": [serialize_evidence(item) for item in evidence],
                "retrieval_context": grouped_evidence,
                "retrieval_policy": {
                    "deterministic_engine_overrides_rag": True,
                    "rule_claims_require_trust_tier": ["A", "B"],
                    "c_tier_is_explanation_or_historical_analogy_only": True,
                    "every_claim_requires_rule_or_evidence": True,
                    "required_statement_qualifier": "在本规则体系下",
                },
                "analysis_profile": {"school": school},
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
                input_payload=input_payload,
                schema=schema,
                prompt_version=INTERPRETER_PROMPT_VERSION,
            )
            try:
                analysis = StructuredAnalysisDTO.model_validate(response.payload)
            except ValueError as exc:
                raise AnalysisPipelineError("provider output violates analysis schema") from exc
            if on_stage:
                on_stage("verifying")
            validation = verify_analysis(
                chart=chart,
                evidence=evidence,
                analysis=analysis,
                configured_school=school,
                computed_relations=computed_relations,
            )
            if validation.status == "passed" or attempt == max_revisions:
                break
            if on_stage:
                on_stage("revision_pending")
            input_payload = {
                **input_payload,
                "previous_analysis": analysis.model_dump(mode="json"),
                "required_revisions": validation.required_revisions,
                "validation_errors": validation.errors,
                "revision_guidance": [
                    _REVISION_GUIDANCE.get(code, code)
                    for code in validation.required_revisions
                ],
            }
        assert response is not None and analysis is not None and validation is not None
        analysis, validation = _salvage_valid_claims(
            chart=chart,
            evidence=evidence,
            analysis=analysis,
            validation=validation,
            configured_school=school,
            computed_relations=computed_relations,
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
                retrieval_trace_id=retrieval_trace_id,
            )
        return AnalysisPipelineResult(
            analysis=analysis,
            validation=validation,
            evidence=evidence,
            report=report,
            retrieval_trace_id=retrieval_trace_id,
            model_id=response.model_id,
            prompt_version=response.prompt_version,
        )
