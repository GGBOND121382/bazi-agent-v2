"""Deterministic validator. A model can never override these failures."""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from typing import Any

from ...api.dto import ChartResultDTO, FactDTO, StructuredAnalysisDTO, ValidationResultDTO
from ..rag.models import RetrievedEvidence

_RISK = re.compile(
    r"(?:必然|注定|一定)(?:死亡|患病|离婚|破产|发财)|保证(?:盈利|发财)|"
    r"(?:医疗|法律|投资)(?:诊断|结论|建议)",
    re.IGNORECASE,
)
_QUALIFIERS = ("在本规则体系下", "倾向", "可能", "候选", "传统命理")
_CASE_QUALIFIERS = ("历史案例", "仅作类比", "不代表", "不能推断")
_GANZHI = frozenset("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")


def _error(code: str, claim_id: str, detail: str) -> dict[str, Any]:
    return {"code": code, "claim_id": claim_id, "detail": detail}


def _referenced_text(
    *,
    fact_ids: Iterable[str],
    rule_ids: Iterable[str],
    evidence_ids: Iterable[str],
    fact_index: dict[str, FactDTO],
    relation_fact_index: dict[str, dict[str, Any]],
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
    fact_index = {fact.fact_id: fact for fact in chart.facts}
    relation_fact_index = {
        str(item["fact_id"]): item for item in relation_items if "fact_id" in item
    }
    evidence_index = {item.chunk_id: item for item in evidence}
    chart_rules = {fact.rule_id for fact in chart.facts} | {
        str(item["rule_id"]) for item in relation_items if "rule_id" in item
    }
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
            errors.append(_error("POLICY_HIGH_RISK_ASSERTION", claim.claim_id, "unsafe assertion"))
        if not any(qualifier in claim.statement for qualifier in _QUALIFIERS):
            errors.append(_error("ASSERTION_TOO_DETERMINISTIC", claim.claim_id, "missing qualifier"))
        cited_cases = [
            evidence_index[evidence_id]
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence_index
            and evidence_index[evidence_id].can_support_case_analogy
        ]
        if cited_cases and not any(
            qualifier in claim.statement for qualifier in _CASE_QUALIFIERS
        ):
            errors.append(
                _error(
                    "CASE_ANALOGY_NOT_QUALIFIED",
                    claim.claim_id,
                    "historical cases require an explicit non-inevitability qualifier",
                )
            )

        referenced_text = _referenced_text(
            fact_ids=claim.fact_ids,
            rule_ids=claim.rule_ids,
            evidence_ids=claim.evidence_ids,
            fact_index=fact_index,
            relation_fact_index=relation_fact_index,
            evidence_index=evidence_index,
        )
        unsupported_ganzhi = sorted(
            char for char in set(claim.statement) & _GANZHI if char not in referenced_text
        )
        if unsupported_ganzhi:
            errors.append(
                _error("FACTUAL_TOKEN_MISMATCH", claim.claim_id, "".join(unsupported_ganzhi))
            )
        if claim.confidence >= 0.85 and claim.counterevidence:
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
