"""Professional analysis core using immutable deterministic chart context."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from ...adapters.llm.deepseek import ProviderResponse, StructuredOutputProvider
from ...api.dto import ChartResultDTO, ClaimDTO, StructuredAnalysisDTO, ValidationResultDTO
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
from .prompts import (
    INTERPRETER_PROMPT_VERSION,
    INTERPRETER_SYSTEM_PROMPT,
    LOCAL_REPAIR_PROMPT_VERSION,
    LOCAL_REPAIR_SYSTEM_PROMPT,
)
from .report import ReportAssembler
from .verifier import verify_analysis


class AnalysisPipelineError(RuntimeError):
    def __init__(self, message: str, *, safe_details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.safe_details = safe_details or {}


_RELATION_LABELS = {
    "stem_combination": "天干五合",
    "stem_clash": "天干相冲",
    "stem_control": "天干相克",
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
    "UNKNOWN_FACT": "fact_ids 只能使用 allowed_reference_ids.fact_ids 中的确定性事实 ID。",
    "UNKNOWN_RULE": "rule_ids 只能使用 allowed_reference_ids.rule_ids 中的确定性规则或 A/B 级证据 ID。",
    "UNKNOWN_EVIDENCE": "evidence_ids 只能使用 allowed_reference_ids.evidence_ids 中的已检索证据 ID。",
    "MISSING_INTERPRETIVE_SUPPORT": "为该 claim 补充 allowed_reference_ids 中真实存在的 rule_id/evidence_id；若无可用支撑，删除该 claim。",
    "NON_AUTHORITATIVE_RULE": "C 级案例只能作为 evidence_ids；rule_ids 只能引用确定性规则或 A/B 级证据。",
    "SCHOOL_MISMATCH": "analysis.school 必须逐字等于 analysis_profile.school；methodology_priority 不是 school 的可选值。",
    "CLAIM_SCHOOL_MISMATCH": "claim.school 应省略，或逐字等于 analysis_profile.school；不得填写 methodology_priority。",
    "POLICY_HIGH_RISK_ASSERTION": "改为条件、趋势和风险提示。",
    "MISSING_KINSHIP_ASSESSMENT": "补全父亲、母亲、兄弟姐妹、配偶婚恋、子女和家庭互动六项，逐项结合六亲星、宫位与岁运触发。",
    "MISSING_HEALTH_ASSESSMENT": "补全五行偏性、寒暖燥湿、传统脏腑象义、保护因素、大运变化和生活建议六项。",
    "INCOMPLETE_DAYUN_ASSESSMENT": "从出生至起运开始，并按 dayun_table 原顺序逐柱补全全部大运。",
}

_REPAIRABLE_FIELDS = frozenset(
    {
        "executive_summary",
        "reasoning_summary",
        "structure_assessment",
        "temporal_assessment",
        "kinship_assessment",
        "health_assessment",
        "dayun_assessment",
        "claims",
        "reflection",
        "limitations",
    }
)


def _repair_targets(
    analysis: StructuredAnalysisDTO, validation: ValidationResultDTO
) -> set[str]:
    targets: set[str] = set()
    for error in validation.errors:
        code = str(error.get("code", ""))
        if code == "MISSING_KINSHIP_ASSESSMENT":
            targets.add("kinship_assessment")
        elif code == "MISSING_HEALTH_ASSESSMENT":
            targets.add("health_assessment")
        elif code == "INCOMPLETE_DAYUN_ASSESSMENT":
            targets.add("dayun_assessment")
        elif error.get("claim_id") or code in {
            "UNKNOWN_FACT",
            "UNKNOWN_RULE",
            "UNKNOWN_EVIDENCE",
            "MISSING_INTERPRETIVE_SUPPORT",
            "NON_AUTHORITATIVE_RULE",
            "CLAIM_SCHOOL_MISMATCH",
            "POLICY_HIGH_RISK_ASSERTION",
        }:
            targets.add("claims")
        elif code == "SCHOOL_MISMATCH":
            # The immutable school field is repaired by a full rewrite because it is
            # intentionally not exposed as a patchable semantic section.
            return set()

    reflection = analysis.reflection
    if reflection is not None and reflection.status == "revise":
        reflection_text = " ".join(
            [
                *reflection.missing_dimensions,
                *reflection.contradictions,
                *reflection.revision_instructions,
            ]
        )
        keyword_targets = {
            "六亲": "kinship_assessment",
            "父母": "kinship_assessment",
            "婚恋": "kinship_assessment",
            "健康": "health_assessment",
            "脏腑": "health_assessment",
            "大运": "dayun_assessment",
            "岁运": "temporal_assessment",
            "格局": "structure_assessment",
            "喜用": "structure_assessment",
            "强弱": "structure_assessment",
            "摘要": "executive_summary",
            "推理": "reasoning_summary",
            "引用": "claims",
        }
        mapped_reflection_targets = {
            field_name
            for keyword, field_name in keyword_targets.items()
            if keyword in reflection_text
        }
        if reflection_text.strip() and not mapped_reflection_targets:
            return set()
        targets.update(mapped_reflection_targets)
        if targets:
            targets.add("reflection")
    return targets & _REPAIRABLE_FIELDS


def _local_repair_schema(
    analysis_schema: dict[str, Any], targets: set[str]
) -> dict[str, Any]:
    source_properties = analysis_schema.get("properties", {})
    replacement_properties = {
        name: source_properties[name]
        for name in sorted(targets)
        if isinstance(source_properties, dict) and name in source_properties
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "analysis-repair-v1",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "replacement_fields",
            "remove_claim_ids",
            "repair_summary",
        ],
        "properties": {
            "schema_version": {"const": "analysis-repair-v1"},
            "replacement_fields": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(replacement_properties),
                "properties": replacement_properties,
            },
            "remove_claim_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "repair_summary": {"type": "string"},
        },
    }


def _build_local_repair_payload(
    *,
    base_payload: dict[str, Any],
    analysis: StructuredAnalysisDTO,
    validation: ValidationResultDTO,
    targets: set[str],
) -> dict[str, Any]:
    candidate = analysis.model_dump(mode="json")
    return {
        "chart_id": base_payload["chart_id"],
        "analysis_context": base_payload["analysis_context"],
        "retrieval_context": base_payload["retrieval_context"],
        "retrieval_policy": base_payload["retrieval_policy"],
        "analysis_profile": base_payload["analysis_profile"],
        "allowed_reference_ids": base_payload["allowed_reference_ids"],
        "core_topic_contract": base_payload["core_topic_contract"],
        "user_focus": base_payload["user_focus"],
        "repair_targets": sorted(targets),
        "global_analysis_state": {
            "executive_summary": candidate.get("executive_summary"),
            "reasoning_summary": candidate.get("reasoning_summary", []),
            "structure_assessment": candidate.get("structure_assessment"),
            "temporal_assessment": candidate.get("temporal_assessment", []),
        },
        "candidate_analysis": candidate,
        "validation_errors": validation.errors,
        "required_revisions": validation.required_revisions,
        "revision_guidance": [
            _REVISION_GUIDANCE.get(code, code)
            for code in validation.required_revisions
        ],
        "reflection_feedback": reflection_feedback(analysis),
    }


def _apply_local_repair(
    *,
    analysis: StructuredAnalysisDTO,
    repair_payload: dict[str, Any],
    targets: set[str],
) -> dict[str, Any]:
    allowed_top_level = {
        "schema_version",
        "replacement_fields",
        "remove_claim_ids",
        "repair_summary",
    }
    if set(repair_payload) - allowed_top_level:
        raise AnalysisPipelineError(
            "provider added fields outside the local repair contract",
            safe_details={"required_revisions": ["LOCAL_REPAIR_SCOPE_VIOLATION"]},
        )
    if repair_payload.get("schema_version") != "analysis-repair-v1":
        raise AnalysisPipelineError(
            "provider output violates local repair schema",
            safe_details={"required_revisions": ["LOCAL_REPAIR_SCHEMA_INVALID"]},
        )
    replacements = repair_payload.get("replacement_fields")
    if not isinstance(replacements, dict) or not targets <= set(replacements):
        raise AnalysisPipelineError(
            "provider omitted requested local repair fields",
            safe_details={
                "required_revisions": ["LOCAL_REPAIR_FIELDS_MISSING"],
                "repair_targets": sorted(targets),
            },
        )
    if set(replacements) - targets:
        raise AnalysisPipelineError(
            "provider attempted to modify frozen report fields",
            safe_details={"required_revisions": ["LOCAL_REPAIR_SCOPE_VIOLATION"]},
        )
    merged = analysis.model_dump(mode="json")
    for field_name, value in replacements.items():
        merged[field_name] = value
    remove_ids_raw = repair_payload.get("remove_claim_ids", [])
    remove_ids = (
        {str(item) for item in remove_ids_raw}
        if isinstance(remove_ids_raw, list)
        else set()
    )
    if remove_ids:
        claims = merged.get("claims", [])
        if isinstance(claims, list):
            merged["claims"] = [
                claim
                for claim in claims
                if not isinstance(claim, dict)
                or str(claim.get("claim_id", "")) not in remove_ids
            ]
    return merged


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


def _discard_malformed_claims(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop individual untraceable claims without discarding an otherwise valid analysis."""
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return payload, []

    valid_claims: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw_claim in enumerate(claims):
        try:
            claim = ClaimDTO.model_validate(raw_claim)
        except ValueError as exc:
            claim_id = raw_claim.get("claim_id") if isinstance(raw_claim, dict) else None
            rejected.append(
                {
                    "code": "INVALID_CLAIM_SCHEMA",
                    "claim_id": str(claim_id) if claim_id else None,
                    "claim_index": index,
                    "detail": str(exc).splitlines()[0],
                }
            )
        else:
            valid_claims.append(claim.model_dump(mode="json"))

    # An analysis with no valid claims should go through the normal schema-failure
    # path instead of being silently accepted as an empty report.
    if not rejected or (claims and not valid_claims):
        return payload, rejected

    limitations = payload.get("limitations")
    cleaned_limitations = list(limitations) if isinstance(limitations, list) else []
    cleaned_limitations.append(
        f"{len(rejected)} model claim(s) were omitted because they were not traceable."
    )
    return {**payload, "claims": valid_claims, "limitations": cleaned_limitations}, rejected


def _validate_provider_payload(
    payload: dict[str, Any],
) -> tuple[StructuredAnalysisDTO, list[dict[str, Any]]]:
    normalized_payload, schema_repairs = _discard_malformed_claims(payload)
    try:
        return StructuredAnalysisDTO.model_validate(normalized_payload), schema_repairs
    except ValueError as exc:
        raise AnalysisPipelineError(
            "provider output violates analysis schema",
            safe_details={
                "required_revisions": ["OUTPUT_SCHEMA_INVALID"],
                "validation_errors": schema_repairs
                or [{"code": "OUTPUT_SCHEMA_INVALID", "detail": str(exc).splitlines()[0]}],
            },
        ) from exc


def _walk_dicts(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        item = cast(dict[str, Any], value)
        yield item
        for child in item.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list | tuple):
        for child in value:
            yield from _walk_dicts(child)


def _reference_catalog(
    context: dict[str, Any], evidence: tuple[RetrievedEvidence, ...]
) -> dict[str, list[str]]:
    """Expose exactly the identifiers that the deterministic validator can accept."""
    fact_ids: set[str] = set()
    deterministic_rule_ids: set[str] = set()
    for item in _walk_dicts(context):
        fact_id = item.get("fact_id")
        rule_id = item.get("rule_id")
        if fact_id:
            fact_ids.add(str(fact_id))
        if rule_id:
            deterministic_rule_ids.add(str(rule_id))

    authoritative_evidence_ids = {
        item.chunk_id
        for item in evidence
        if item.can_support_claim and item.trust_tier in {"A", "B"}
    }
    return {
        "fact_ids": sorted(fact_ids),
        "rule_ids": sorted(deterministic_rule_ids | authoritative_evidence_ids),
        "evidence_ids": sorted(item.chunk_id for item in evidence),
    }


def _substantive_items(items: list[dict[str, Any]]) -> int:
    keys = {"conclusion", "summary", "analysis", "statement", "title", "relation", "dimension", "stage"}
    return sum(
        1
        for item in items
        if any(str(item.get(key, "")).strip() for key in keys)
    )


def _enforce_core_topic_coverage(
    *,
    chart: ChartResultDTO,
    analysis: StructuredAnalysisDTO,
    validation: ValidationResultDTO,
) -> ValidationResultDTO:
    """Fail the report gate when the three core topics are materially incomplete.

    Prompt instructions alone are not sufficient for core product capabilities.  This
    check feeds omissions back into the existing revision loop and prevents a formally
    successful report from silently dropping 六亲、健康或任一步大运。
    """
    errors = list(validation.errors)
    if _substantive_items(analysis.kinship_assessment) < 6:
        errors.append(
            {
                "code": "MISSING_KINSHIP_ASSESSMENT",
                "detail": "kinship_assessment must contain six substantive relation groups",
            }
        )
    if _substantive_items(analysis.health_assessment) < 6:
        errors.append(
            {
                "code": "MISSING_HEALTH_ASSESSMENT",
                "detail": "health_assessment must contain six substantive dimensions",
            }
        )
    expected_dayun_items = 1 + len(chart.dayun or [])
    if _substantive_items(analysis.dayun_assessment) < expected_dayun_items:
        errors.append(
            {
                "code": "INCOMPLETE_DAYUN_ASSESSMENT",
                "detail": (
                    "dayun_assessment must cover birth-to-qiyun and every deterministic "
                    f"dayun item; expected at least {expected_dayun_items}"
                ),
            }
        )
    if len(errors) == len(validation.errors):
        return validation
    return validation.model_copy(
        update={
            "status": "failed",
            "errors": errors,
            "approved_claim_ids": [],
            "required_revisions": sorted(
                {str(error.get("code", "VALIDATION_ERROR")) for error in errors}
            ),
        }
    )


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
    generation_trace: dict[str, Any]


class AnalysisPipeline:
    def __init__(self, *, provider: StructuredOutputProvider, retriever: EvidenceRetriever) -> None:
        self.provider = provider
        self.retriever = retriever
        self.report_assembler = ReportAssembler()

    def run(  # noqa: PLR0915
        self,
        *,
        chart: ChartResultDTO,
        user_focus: tuple[str, ...],
        school: str = "engineering_policy",
        on_stage: Callable[[str], None] | None = None,
        on_model_progress: Callable[[dict[str, Any]], None] | None = None,
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
        allowed_reference_ids = _reference_catalog(context, evidence)
        payload: dict[str, Any] = {
            "chart_id": chart.chart_id,
            "calculation_profile_id": chart.calculation_profile_id,
            "analysis_context": context,
            "retrieval_context": grouped,
            "retrieval_policy": {
                "deterministic_engine_overrides_rag": True,
                "rule_claims_require_trust_tier": ["A", "B"],
                "c_tier_is_explanation_or_historical_analogy_only": True,
                "every_claim_requires_rule_or_evidence": True,
            },
            "analysis_profile": {
                "school": school,
                "methodology_priority": "ziping_structure_first",
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
            "output_contract": {
                "analysis_school_must_equal": school,
                "claim_school": f"omit or exactly equal {school}",
                "methodology_priority_is_not_school": True,
                "unsupported_claim_action": "add a legal rule/evidence reference or delete the claim",
            },
            "allowed_reference_ids": allowed_reference_ids,
            "professional_rubric": PROFESSIONAL_RUBRIC,
            "user_focus": list(user_focus),
            "core_topic_contract": {
                "kinship_assessment": {
                    "required_relations": ["father", "mother", "siblings", "spouse_relationship", "children", "family_dynamics"],
                    "method": "ten_god_mapping + palace + exposure_roots + favorability + temporal_trigger",
                },
                "health_assessment": {
                    "required_dimensions": ["element_bias", "cold_heat_dry_wet", "traditional_organs", "protective_factors", "dayun_changes", "lifestyle_advice"],
                    "medical_boundary": "traditional tendency, not medical diagnosis",
                },
                "dayun_assessment": {
                    "required_scope": "birth_to_qiyun_then_every_item_in_analysis_context.temporal.dayun_table",
                    "themes_per_period": ["structure", "career", "wealth", "relationship_kinship", "health", "transition_to_next"],
                },
            },
        }

        response: ProviderResponse | None = None
        primary_response: ProviderResponse | None = None
        analysis: StructuredAnalysisDTO | None = None
        validation: ValidationResultDTO | None = None
        attempts: list[dict[str, Any]] = []
        candidate_payload: dict[str, Any] | None = None
        request_kind = "full_analysis"
        request_payload = payload
        request_schema = schema
        request_system_prompt = INTERPRETER_SYSTEM_PROMPT
        request_prompt_version = INTERPRETER_PROMPT_VERSION
        repair_targets: set[str] = set()

        for attempt in range(max_revisions + 1):
            if on_stage:
                on_stage("interpreting")
            response = self.provider.complete_json(
                system_prompt=request_system_prompt,
                input_payload=request_payload,
                schema=request_schema,
                prompt_version=request_prompt_version,
                on_stream_event=on_model_progress,
            )
            if primary_response is None:
                primary_response = response
            if request_kind == "local_repair":
                assert analysis is not None
                candidate_payload = _apply_local_repair(
                    analysis=analysis,
                    repair_payload=response.payload,
                    targets=repair_targets,
                )
            else:
                candidate_payload = response.payload

            analysis, schema_repairs = _validate_provider_payload(candidate_payload)
            if on_stage:
                on_stage("verifying")
            validation = verify_analysis(
                chart=chart,
                evidence=evidence,
                analysis=analysis,
                configured_school=school,
                computed_relations=relations,
            )
            validation = _enforce_core_topic_coverage(
                chart=chart, analysis=analysis, validation=validation
            )
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "request_kind": request_kind,
                    "system_prompt": request_system_prompt,
                    "prompt_version": request_prompt_version,
                    "input_payload": request_payload,
                    "model_output": response.payload,
                    "candidate_analysis_after_attempt": candidate_payload,
                    "provider_reasoning_content": response.reasoning_content,
                    "provider_usage": response.usage,
                    "provider_finish_reason": response.finish_reason,
                    "provider_streamed": response.streamed,
                    "provider_transport_attempts": response.transport_attempts,
                    "provider_timings": response.timings,
                    "schema_repairs": schema_repairs,
                    "validation": validation.model_dump(mode="json"),
                    "reflection": analysis.reflection.model_dump(mode="json")
                    if analysis.reflection is not None
                    else None,
                }
            )
            reflection_failed = reflection_requires_revision(analysis)
            if (validation.status == "passed" and not reflection_failed) or attempt == max_revisions:
                break
            if on_stage:
                on_stage("revision_pending")

            repair_targets = _repair_targets(analysis, validation)
            if repair_targets:
                request_kind = "local_repair"
                request_payload = _build_local_repair_payload(
                    base_payload=payload,
                    analysis=analysis,
                    validation=validation,
                    targets=repair_targets,
                )
                request_schema = _local_repair_schema(schema, repair_targets)
                request_system_prompt = LOCAL_REPAIR_SYSTEM_PROMPT
                request_prompt_version = LOCAL_REPAIR_PROMPT_VERSION
            else:
                # Rare cross-cutting failures still use a coherent full rewrite.  The
                # initial call remains a single global analysis; this fallback exists
                # only when the validator cannot safely isolate a section.
                request_kind = "full_revision"
                request_payload = {
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
                request_schema = schema
                request_system_prompt = INTERPRETER_SYSTEM_PROMPT
                request_prompt_version = INTERPRETER_PROMPT_VERSION

        assert (
            response is not None
            and primary_response is not None
            and analysis is not None
            and validation is not None
        )
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
                prompt_version=primary_response.prompt_version,
                model_id=primary_response.model_id,
                retrieval_trace_id=trace_id,
            )
        generation_trace = {
            "trace_type": "report_analysis",
            "retrieval_trace_id": trace_id,
            "prompt_version": primary_response.prompt_version,
            "model_id": primary_response.model_id,
            "system_prompt": INTERPRETER_SYSTEM_PROMPT,
            "retrieval_plan": {
                "queries": list(plan.queries),
                "school": plan.school,
                "task_type": plan.task_type,
            },
            "retrieved_evidence": [_serialize(item) for item in evidence],
            "attempts": attempts,
            "final_analysis": analysis.model_dump(mode="json"),
            "final_validation": validation.model_dump(mode="json"),
        }
        return AnalysisPipelineResult(
            analysis=analysis,
            validation=validation,
            evidence=evidence,
            report=report,
            retrieval_trace_id=trace_id,
            model_id=primary_response.model_id,
            prompt_version=primary_response.prompt_version,
            generation_trace=generation_trace,
        )
