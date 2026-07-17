"""Deterministic reference validator for model-produced structured analyses.

The gate protects chart/evidence identifiers and truly unsafe absolute claims.
Interpretive judgments such as 旺衰、格局、喜忌 are deliberately not treated as
calculation errors; they are model/RAG conclusions and may carry uncertainty.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from typing import Any, cast

from ...api.dto import ChartResultDTO, FactDTO, StructuredAnalysisDTO, ValidationResultDTO
from ..rag.models import RetrievedEvidence

_RISK = re.compile(
    r"(?:必然|注定|保证|百分之百)(?:死亡|患病|离婚|破产|发财|盈利)|"
    r"(?:替代医生|无需就医|停止治疗)|(?:保证盈利|稳赚不赔)",
    re.IGNORECASE,
)
_GANZHI = frozenset("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")


def _error(code: str, claim_id: str, detail: str) -> dict[str, Any]:
    return {"code": code, "claim_id": claim_id, "detail": detail}


def _deterministic_shensha(chart: ChartResultDTO) -> tuple[dict[str, Any], ...]:
    details = chart.calendar.get("deterministic_details", {})
    if not isinstance(details, dict):
        return ()
    raw = details.get("shensha", [])
    if not isinstance(raw, list):
        return ()
    return tuple(cast(dict[str, Any], item) for item in raw if isinstance(item, dict))


def _referenced_text(
    *,
    fact_ids: Iterable[str],
    rule_ids: Iterable[str],
    evidence_ids: Iterable[str],
    fact_index: dict[str, FactDTO],
    relation_fact_index: dict[str, dict[str, Any]],
    shensha_rule_index: dict[str, list[dict[str, Any]]],
    evidence_index: dict[str, RetrievedEvidence],
) -> str:
    parts = [
        json.dumps(fact_index[fact_id].value, ensure_ascii=False, default=str)
        for fact_id in fact_ids
        if fact_id in fact_index
    ]
    parts.extend(
        json.dumps(relation_fact_index[fact_id], ensure_ascii=False, default=str)
        for fact_id in fact_ids
        if fact_id in relation_fact_index
    )
    parts.extend(
        json.dumps(item, ensure_ascii=False, default=str)
        for rule_id in rule_ids
        for item in shensha_rule_index.get(rule_id, [])
    )
    parts.extend(
        evidence_index[evidence_id].content
        for evidence_id in set(rule_ids) | set(evidence_ids)
        if evidence_id in evidence_index
    )
    return " ".join(parts)


def verify_analysis(
    *,
    chart: ChartResultDTO,
    evidence: Iterable[RetrievedEvidence],
    analysis: StructuredAnalysisDTO,
    configured_school: str,
    computed_relations: Iterable[dict[str, Any]] = (),
) -> ValidationResultDTO:
    relation_items = tuple(computed_relations)
    shensha_items = _deterministic_shensha(chart)
    shensha_rule_index: dict[str, list[dict[str, Any]]] = {}
    for item in shensha_items:
        rule_id = str(item.get("rule_id", ""))
        if rule_id:
            shensha_rule_index.setdefault(rule_id, []).append(item)

    fact_index = {fact.fact_id: fact for fact in chart.facts}
    relation_fact_index = {
        str(item["fact_id"]): item for item in relation_items if "fact_id" in item
    }
    evidence_index = {item.chunk_id: item for item in evidence}
    chart_rules = (
        {fact.rule_id for fact in chart.facts}
        | {str(item["rule_id"]) for item in relation_items if "rule_id" in item}
        | set(shensha_rule_index)
    )
    known_rules = chart_rules | set(evidence_index)
    authoritative_rules = chart_rules | {
        item.chunk_id
        for item in evidence_index.values()
        if item.can_support_claim and item.trust_tier in {"A", "B"}
    }
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    approved: list[str] = []

    if chart.calculation_status != "passed":
        errors.append({"code": "CHART_NOT_VALIDATED", "detail": "chart status must be passed"})
    if analysis.chart_id != chart.chart_id:
        errors.append({"code": "CHART_ID_MISMATCH", "detail": "analysis references another chart"})
    if analysis.school != configured_school:
        errors.append({"code": "SCHOOL_MISMATCH", "detail": "analysis school is not configured"})

    for claim in analysis.claims:
        before = len(errors)
        known_fact_ids = set(fact_index) | set(relation_fact_index)
        missing_facts = sorted(set(claim.fact_ids) - known_fact_ids)
        missing_rules = sorted(set(claim.rule_ids) - known_rules)
        non_authoritative_rules = sorted(set(claim.rule_ids) - authoritative_rules)
        missing_evidence = sorted(set(claim.evidence_ids) - set(evidence_index))
        if missing_facts:
            errors.append(_error("UNKNOWN_FACT", claim.claim_id, ",".join(missing_facts)))
        if missing_rules:
            errors.append(_error("UNKNOWN_RULE", claim.claim_id, ",".join(missing_rules)))
        if non_authoritative_rules:
            errors.append(
                _error(
                    "NON_AUTHORITATIVE_RULE",
                    claim.claim_id,
                    ",".join(non_authoritative_rules),
                )
            )
        if missing_evidence:
            errors.append(_error("UNKNOWN_EVIDENCE", claim.claim_id, ",".join(missing_evidence)))
        if not claim.rule_ids and not claim.evidence_ids:
            errors.append(
                _error(
                    "MISSING_INTERPRETIVE_SUPPORT",
                    claim.claim_id,
                    "claim requires a rule_id or evidence_id",
                )
            )
        if claim.school and claim.school != configured_school:
            errors.append(_error("CLAIM_SCHOOL_MISMATCH", claim.claim_id, claim.school))
        if _RISK.search(claim.statement):
            errors.append(
                _error("POLICY_HIGH_RISK_ASSERTION", claim.claim_id, "absolute unsafe assertion")
            )

        # A referenced-text mismatch can come from natural-language discussion of
        # another pillar or temporal干支. It is useful diagnostics, not a reason to
        # discard an otherwise well-supported interpretation.
        referenced_text = _referenced_text(
            fact_ids=claim.fact_ids,
            rule_ids=claim.rule_ids,
            evidence_ids=claim.evidence_ids,
            fact_index=fact_index,
            relation_fact_index=relation_fact_index,
            shensha_rule_index=shensha_rule_index,
            evidence_index=evidence_index,
        )
        unsupported_ganzhi = sorted(
            char for char in set(claim.statement) & _GANZHI if char not in referenced_text
        )
        if unsupported_ganzhi:
            warnings.append(
                {
                    "code": "UNREFERENCED_GANZHI_TOKEN",
                    "claim_id": claim.claim_id,
                    "detail": "".join(unsupported_ganzhi),
                }
            )
        if claim.confidence >= 0.9 and claim.counterevidence:
            warnings.append(
                {"code": "COUNTEREVIDENCE_OVERCONFIDENCE", "claim_id": claim.claim_id}
            )
        if len(errors) == before:
            approved.append(claim.claim_id)

    status = "passed" if not errors else "failed"
    return ValidationResultDTO(
        validation_id=f"validation_{uuid.uuid4().hex[:12]}",
        analysis_id=analysis.analysis_id,
        status=status,
        errors=errors,
        warnings=warnings,
        approved_claim_ids=approved if status == "passed" else [],
        required_revisions=sorted(
            {str(error.get("code", "VALIDATION_ERROR")) for error in errors}
        ),
    )
