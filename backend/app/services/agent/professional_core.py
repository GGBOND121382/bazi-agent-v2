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
from ..rag.models import RetrievedEvidence
from .context import build_analysis_context
from .prompts import (
    INTERPRETER_PROMPT_VERSION,
    INTERPRETER_SYSTEM_PROMPT,
    LOCAL_REPAIR_PROMPT_VERSION,
    LOCAL_REPAIR_SYSTEM_PROMPT,
)
from .report import ReportAssembler
from .verifier import build_programmatic_reflection, verify_analysis


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
    "UNKNOWN_FACT": "删除或改用 analysis_context 中真实存在的确定性 fact_id。",
    "UNKNOWN_RULE": "删除或改用 analysis_context 中真实存在的确定性 rule_id。",
    "EVIDENCE_DISABLED": "RAG 已关闭；删除 evidence_ids，不得使用外部证据 ID。",
    "SCHOOL_MISMATCH": "analysis.school 必须逐字等于 analysis_profile.school。",
    "CLAIM_SCHOOL_MISMATCH": "claim.school 应省略，或逐字等于 analysis_profile.school。",
    "POLICY_HIGH_RISK_ASSERTION": "改为条件、趋势和风险提示。",
    "TEN_GOD_MISMATCH": "按日主与目标天干的确定性十神映射重写相关块。",
    "INVALID_HIDDEN_STEM": "按地支确定性藏干表重写相关块。",
    "INVALID_ELEMENT_RELATION": "修正五行生克方向，并同步修正由此产生的解释。",
    "INVALID_STEM_RELATION": "修正天干五合或天干冲的参与者，并与 analysis_context 的确定性关系一致。",
    "INVALID_BRANCH_RELATION": "修正六合、冲、刑、害、破、半合半会、拱合拱会或暗合类型。",
    "INVALID_BRANCH_GROUP_RELATION": "修正三合、三会或三刑的完整三支组合。",
    "INVALID_PILLAR_RELATION": "修正伏吟、反吟、天克地冲或天合地合的干支条件。",
    "INVALID_INTERNAL_PILLAR_RELATION": "按干支五行方向修正盖头或截脚判断。",
    "MISSING_KINSHIP_ASSESSMENT": "补全父亲、母亲、兄弟姐妹、配偶婚恋、子女和家庭互动六项。",
    "MISSING_HEALTH_ASSESSMENT": "补全五行偏性、寒暖燥湿、传统脏腑象义、保护因素、大运变化和生活建议六项。",
    "INCOMPLETE_DAYUN_ASSESSMENT": "补全出生至起运和 analysis_context.temporal_hierarchy.dayun_sequence 中每一步大运。",
}

_REPAIRABLE_ROOTS = frozenset(
    {
        "executive_summary",
        "reasoning_summary",
        "structure_assessment",
        "temporal_assessment",
        "kinship_assessment",
        "health_assessment",
        "dayun_assessment",
        "claims",
        "limitations",
    }
)


def _json_pointer_parts(path: str) -> list[str]:
    return [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]


def _repair_unit(path: str) -> str | None:
    parts = _json_pointer_parts(path)
    if not parts or parts[0] not in _REPAIRABLE_ROOTS:
        return None
    root = parts[0]
    if (
        root
        in {
            "reasoning_summary",
            "temporal_assessment",
            "kinship_assessment",
            "health_assessment",
            "dayun_assessment",
            "claims",
        }
        and len(parts) >= 2
        and parts[1].isdigit()
    ):
        return f"/{root}/{parts[1]}"
    return f"/{root}"


def _claim_path(analysis: StructuredAnalysisDTO, claim_id: str) -> str | None:
    for index, claim in enumerate(analysis.claims):
        if claim.claim_id == claim_id:
            return f"/claims/{index}"
    return None


def _repair_paths(analysis: StructuredAnalysisDTO, validation: ValidationResultDTO) -> set[str]:
    paths: set[str] = set()
    for error in validation.errors:
        code = str(error.get("code", ""))
        explicit_path = str(error.get("path", "")).strip()
        if explicit_path:
            unit = _repair_unit(explicit_path)
            if unit:
                paths.add(unit)
                continue
        claim_id = str(error.get("claim_id", "")).strip()
        if claim_id:
            claim_path = _claim_path(analysis, claim_id)
            if claim_path:
                paths.add(claim_path)
                continue
        if code == "MISSING_KINSHIP_ASSESSMENT":
            paths.add("/kinship_assessment")
        elif code == "MISSING_HEALTH_ASSESSMENT":
            paths.add("/health_assessment")
        elif code == "INCOMPLETE_DAYUN_ASSESSMENT":
            paths.add("/dayun_assessment")
        elif code in {"SCHOOL_MISMATCH", "CHART_ID_MISMATCH", "CHART_NOT_VALIDATED"}:
            return set()
    return paths


def _get_pointer(document: object, path: str) -> object:
    current = document
    for part in _json_pointer_parts(path):
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def _replace_pointer(document: object, path: str, value: object) -> None:
    parts = _json_pointer_parts(path)
    if not parts:
        raise KeyError(path)
    current = document
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(path)
    leaf = parts[-1]
    if isinstance(current, dict):
        current[leaf] = value
    elif isinstance(current, list):
        current[int(leaf)] = value
    else:
        raise KeyError(path)


def _remove_pointer(document: object, path: str) -> None:
    parts = _json_pointer_parts(path)
    if not parts:
        raise KeyError(path)
    current = document
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(path)
    leaf = parts[-1]
    if isinstance(current, dict):
        current.pop(leaf, None)
    elif isinstance(current, list):
        current.pop(int(leaf))
    else:
        raise KeyError(path)


def _local_repair_schema(paths: set[str]) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "analysis-json-patch-v2",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "operations", "repair_summary"],
        "properties": {
            "schema_version": {"const": "analysis-json-patch-v2"},
            "operations": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["op", "path"],
                    "properties": {
                        "op": {"enum": ["replace", "remove"]},
                        "path": {"enum": sorted(paths)},
                        "value": {},
                    },
                },
            },
            "repair_summary": {"type": "string"},
        },
    }


def _compact_global_state(candidate: dict[str, Any]) -> dict[str, Any]:
    structure = candidate.get("structure_assessment")
    if isinstance(structure, dict):
        compact_structure = {
            key: structure[key]
            for key in (
                "day_master_strength",
                "wang_xiang_xiu_qiu_si",
                "pattern",
                "useful_gods",
                "climate_adjustment",
            )
            if key in structure
        }
    else:
        compact_structure = {}
    return {
        "school": candidate.get("school"),
        "structure_assessment": compact_structure,
        "executive_summary_anchor": candidate.get("executive_summary"),
    }


def _collect_ids(value: object, key: str) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for name, child in value.items():
            if name == key and isinstance(child, list):
                result.update(str(item) for item in child if item)
            else:
                result.update(_collect_ids(child, key))
    elif isinstance(value, list | tuple):
        for child in value:
            result.update(_collect_ids(child, key))
    return result


def _project_natal_core(
    natal: dict[str, Any], *, roots: set[str], predicates: set[str]
) -> dict[str, Any]:
    keys = {"day_master", "pillars", "basic"}
    if roots & {
        "structure_assessment",
        "health_assessment",
        "executive_summary",
        "reasoning_summary",
        "claims",
    }:
        keys.add("five_elements")
    if roots & {
        "kinship_assessment",
        "structure_assessment",
        "executive_summary",
        "reasoning_summary",
        "claims",
    } or any(predicate.startswith("branch_") for predicate in predicates):
        keys.add("natal_relations")
    if roots & {"kinship_assessment", "health_assessment"}:
        keys.add("shensha")
    return {key: natal[key] for key in keys if key in natal}


def _dayun_outline(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "index",
        "start_year",
        "end_year",
        "start_age",
        "end_age",
        "ganzhi",
        "stem_ten_god",
        "branch_ten_god",
        "fact_id",
        "rule_id",
    )
    return {key: item[key] for key in keys if key in item}


def _target_dayun_window(
    sequence: list[dict[str, Any]], current_blocks: dict[str, object]
) -> list[dict[str, Any]]:
    fact_ids = _collect_ids(current_blocks, "fact_ids")
    text = json.dumps(current_blocks, ensure_ascii=False, default=str)
    matches = [
        index
        for index, item in enumerate(sequence)
        if (item.get("fact_id") and str(item["fact_id"]) in fact_ids)
        or (item.get("ganzhi") and str(item["ganzhi"]) in text)
    ]
    if not matches:
        return [_dayun_outline(item) for item in sequence]
    indexes: set[int] = set()
    for index in matches:
        indexes.update(item for item in (index - 1, index, index + 1) if 0 <= item < len(sequence))
    return [
        sequence[index] if index in matches else _dayun_outline(sequence[index])
        for index in sorted(indexes)
    ]


def _consistency_neighbors(
    candidate: dict[str, Any], roots: set[str], paths: set[str]
) -> dict[str, Any]:
    neighbors: dict[str, Any] = {}
    if "executive_summary" not in roots and roots & {
        "structure_assessment",
        "temporal_assessment",
        "kinship_assessment",
        "health_assessment",
        "dayun_assessment",
        "reasoning_summary",
    }:
        neighbors["/executive_summary"] = candidate.get("executive_summary")

    keywords_by_root = {
        "structure_assessment": ("强弱", "格局", "喜用", "调候", "结构"),
        "temporal_assessment": ("岁运", "流年", "流月", "流日", "大运"),
        "kinship_assessment": ("六亲", "父", "母", "兄弟", "配偶", "婚恋", "子女"),
        "health_assessment": ("健康", "寒暖", "燥湿", "脏腑", "五行偏性"),
        "dayun_assessment": ("大运", "起运", "生命周期"),
    }
    requested = {keyword for root in roots for keyword in keywords_by_root.get(root, ())}
    reasoning = candidate.get("reasoning_summary")
    if requested and isinstance(reasoning, list) and "/reasoning_summary" not in paths:
        selected = [
            item
            for item in reasoning
            if isinstance(item, dict)
            and any(keyword in json.dumps(item, ensure_ascii=False) for keyword in requested)
        ]
        if selected:
            neighbors["/reasoning_summary:related"] = selected[:4]
    return {key: value for key, value in neighbors.items() if value not in (None, "", [], {})}


def _project_repair_context(
    *,
    base_context: dict[str, Any],
    paths: set[str],
    errors: list[dict[str, Any]],
    current_blocks: dict[str, object],
) -> dict[str, Any]:
    roots = {parts[0] for path in paths if (parts := _json_pointer_parts(path))}
    predicates = {
        str(error.get("assertion", {}).get("predicate", ""))
        for error in errors
        if isinstance(error.get("assertion"), dict)
    }
    context: dict[str, Any] = {
        "context_version": base_context.get("context_version"),
        "context_policy": base_context.get("context_policy"),
    }
    natal = base_context.get("natal_core")
    if isinstance(natal, dict):
        context["natal_core"] = _project_natal_core(natal, roots=roots, predicates=predicates)

    referenced_fact_ids = _collect_ids(current_blocks, "fact_ids")
    catalog = base_context.get("fact_catalog")
    if isinstance(catalog, list):
        selected_catalog = [
            item
            for item in catalog
            if isinstance(item, dict) and str(item.get("fact_id", "")) in referenced_fact_ids
        ]
        if selected_catalog:
            context["fact_catalog"] = selected_catalog

    temporal = base_context.get("temporal_hierarchy")
    if isinstance(temporal, dict):
        projected: dict[str, Any] = {}
        if "hierarchy" in temporal:
            projected["hierarchy"] = temporal["hierarchy"]
        if roots & {"dayun_assessment", "temporal_assessment"}:
            if "qiyun" in temporal:
                projected["qiyun"] = temporal["qiyun"]
            sequence_raw = temporal.get("dayun_sequence")
            sequence = (
                [item for item in sequence_raw if isinstance(item, dict)]
                if isinstance(sequence_raw, list)
                else []
            )
            if sequence:
                if any(path.startswith("/dayun_assessment/") for path in paths):
                    projected["dayun_window"] = _target_dayun_window(sequence, current_blocks)
                else:
                    projected["dayun_sequence"] = sequence
        elif roots & {"health_assessment", "kinship_assessment"}:
            if "qiyun" in temporal:
                projected["qiyun"] = temporal["qiyun"]
            sequence_raw = temporal.get("dayun_sequence")
            if isinstance(sequence_raw, list):
                projected["dayun_outline"] = [
                    _dayun_outline(item) for item in sequence_raw if isinstance(item, dict)
                ]
        for key in ("active_dayun", "target_liunian", "selected_liuyue", "selected_liuri"):
            if key in temporal and roots & {
                "temporal_assessment",
                "kinship_assessment",
                "health_assessment",
                "reasoning_summary",
                "executive_summary",
                "claims",
            }:
                projected[key] = temporal[key]
        if len(projected) > 1:
            context["temporal_hierarchy"] = projected

    if predicates:
        context["rule_checks_needed"] = sorted(predicates)
    return context


def _build_local_repair_payload(
    *,
    base_payload: dict[str, Any],
    analysis: StructuredAnalysisDTO,
    validation: ValidationResultDTO,
    paths: set[str],
) -> dict[str, Any]:
    candidate = analysis.model_dump(mode="json")
    relevant_errors = [
        error
        for error in validation.errors
        if not error.get("path")
        or _repair_unit(str(error.get("path"))) in paths
        or _claim_path(analysis, str(error.get("claim_id", ""))) in paths
    ]
    current_blocks = {path: _get_pointer(candidate, path) for path in sorted(paths)}
    roots = {parts[0] for path in paths if (parts := _json_pointer_parts(path))}
    return {
        "chart_id": base_payload["chart_id"],
        "analysis_profile": base_payload["analysis_profile"],
        "user_focus": base_payload["user_focus"],
        "repair_mode": "minimal_dependency_closure",
        "allowed_paths": sorted(paths),
        "current_blocks": current_blocks,
        "global_analysis_state": _compact_global_state(candidate),
        "consistency_neighbors": _consistency_neighbors(candidate, roots, paths),
        "relevant_context": _project_repair_context(
            base_context=base_payload["analysis_context"],
            paths=paths,
            errors=relevant_errors,
            current_blocks=current_blocks,
        ),
        "validation_errors": relevant_errors,
        "revision_guidance": [
            _REVISION_GUIDANCE.get(str(error.get("code", "")), str(error.get("code", "")))
            for error in relevant_errors
        ],
    }


def _apply_local_repair(
    *,
    analysis: StructuredAnalysisDTO,
    repair_payload: dict[str, Any],
    paths: set[str],
) -> dict[str, Any]:
    if repair_payload.get("schema_version") != "analysis-json-patch-v2":
        raise AnalysisPipelineError(
            "provider output violates local repair schema",
            safe_details={"required_revisions": ["LOCAL_REPAIR_SCHEMA_INVALID"]},
        )
    operations = repair_payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise AnalysisPipelineError(
            "provider omitted local repair operations",
            safe_details={"required_revisions": ["LOCAL_REPAIR_FIELDS_MISSING"]},
        )
    merged = analysis.model_dump(mode="json")
    touched: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise AnalysisPipelineError("invalid local repair operation")
        path = str(operation.get("path", ""))
        if path not in paths:
            raise AnalysisPipelineError(
                "provider attempted to modify frozen report fields",
                safe_details={"required_revisions": ["LOCAL_REPAIR_SCOPE_VIOLATION"]},
            )
        op = str(operation.get("op", ""))
        if op == "replace":
            if "value" not in operation:
                raise AnalysisPipelineError("replace operation requires value")
            _replace_pointer(merged, path, operation["value"])
        elif op == "remove":
            _remove_pointer(merged, path)
        else:
            raise AnalysisPipelineError("unsupported local repair operation")
        touched.add(path)
    if not touched:
        raise AnalysisPipelineError("local repair changed no fields")
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


def _discard_malformed_claims(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop individual untraceable claims without discarding an otherwise valid analysis."""
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return payload, []

    valid_claims: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    rejected_count = 0
    for index, raw_claim in enumerate(claims):
        candidate = dict(raw_claim) if isinstance(raw_claim, dict) else raw_claim
        defaulted_fields: list[str] = []
        if isinstance(candidate, dict):
            # These reference lists are allowed to be empty. Some providers omit
            # an empty array even when the JSON schema marks the field required.
            # Supplying [] preserves the meaning and never invents a citation.
            if candidate.get("rule_ids") or "rule_ids" not in candidate:
                candidate["rule_ids"] = []
                defaulted_fields.append("rule_ids")
            # RAG is disabled for reports.  Normalize legacy/provider-created
            # evidence references to the only valid value instead of spending a
            # repair call on a field with no remaining semantics.
            if candidate.get("evidence_ids") or "evidence_ids" not in candidate:
                candidate["evidence_ids"] = []
                defaulted_fields.append("evidence_ids")
        try:
            claim = ClaimDTO.model_validate(candidate)
        except ValueError as exc:
            claim_id = raw_claim.get("claim_id") if isinstance(raw_claim, dict) else None
            rejected_count += 1
            repairs.append(
                {
                    "code": "INVALID_CLAIM_SCHEMA",
                    "claim_id": str(claim_id) if claim_id else None,
                    "claim_index": index,
                    "detail": str(exc).splitlines()[0],
                }
            )
        else:
            valid_claims.append(claim.model_dump(mode="json"))
            if defaulted_fields:
                repairs.append(
                    {
                        "code": "DEFAULTED_EMPTY_CLAIM_REFERENCES",
                        "claim_id": claim.claim_id,
                        "claim_index": index,
                        "fields": defaulted_fields,
                    }
                )

    # An analysis with no valid claims should go through the normal schema-failure
    # path instead of being silently accepted as an empty report.
    if not repairs or (claims and not valid_claims):
        return payload, repairs

    limitations = payload.get("limitations")
    cleaned_limitations = list(limitations) if isinstance(limitations, list) else []
    if rejected_count:
        cleaned_limitations.append(
            f"{rejected_count} model claim(s) were omitted because they were not traceable."
        )
    return {**payload, "claims": valid_claims, "limitations": cleaned_limitations}, repairs


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


def _substantive_items(items: list[dict[str, Any]]) -> int:
    keys = {
        "conclusion",
        "summary",
        "analysis",
        "statement",
        "title",
        "relation",
        "dimension",
        "stage",
        "period",
        "system",
        "finding",
        "strength",
        "risk",
        "protection",
        "advice",
    }
    return sum(1 for item in items if any(str(item.get(key, "")).strip() for key in keys))


def _dayun_item_identity(item: dict[str, Any]) -> tuple[set[str], str]:
    fact_ids_raw = item.get("fact_ids", [])
    fact_ids = {str(value) for value in fact_ids_raw} if isinstance(fact_ids_raw, list) else set()
    stage = " ".join(
        str(item.get(key, "")) for key in ("stage", "period", "title", "ganzhi")
    ).casefold()
    return fact_ids, stage


def _enforce_core_topic_coverage(
    *,
    chart: ChartResultDTO,
    analysis: StructuredAnalysisDTO,
    validation: ValidationResultDTO,
) -> ValidationResultDTO:
    """Protect the three core product capabilities without judging interpretations."""
    errors = list(validation.errors)
    warnings = list(validation.warnings)
    if _substantive_items(analysis.kinship_assessment) < 6:
        errors.append(
            {
                "code": "MISSING_KINSHIP_ASSESSMENT",
                "path": "/kinship_assessment",
                "detail": "kinship_assessment must contain six substantive relation groups",
            }
        )
    if _substantive_items(analysis.health_assessment) < 6:
        errors.append(
            {
                "code": "MISSING_HEALTH_ASSESSMENT",
                "path": "/health_assessment",
                "detail": "health_assessment must contain six substantive dimensions",
            }
        )

    identities = [_dayun_item_identity(item) for item in analysis.dayun_assessment]
    qiyun_hits = [
        index
        for index, (_, stage) in enumerate(identities)
        if "出生至起运" in stage or "起运前" in stage or "birth" in stage or "qiyun" in stage
    ]
    missing: list[str] = []
    duplicate: list[str] = []
    if chart.dayun:
        if not qiyun_hits:
            missing.append("birth_to_qiyun")
        elif len(qiyun_hits) > 1:
            duplicate.append("birth_to_qiyun")
    elif not analysis.dayun_assessment:
        warnings.append(
            {
                "code": "DAYUN_DATA_UNAVAILABLE",
                "path": "/dayun_assessment",
                "detail": "缺少可核验出生日期或大运数据，允许留空并在 limitations 说明",
            }
        )

    for expected in chart.dayun or []:
        fact_id = str(expected.get("fact_id", ""))
        ganzhi = str(expected.get("ganzhi", "")).casefold()
        matches = [
            index
            for index, (fact_ids, stage) in enumerate(identities)
            if (fact_id and fact_id in fact_ids) or (ganzhi and ganzhi in stage)
        ]
        label = fact_id or ganzhi
        if not matches:
            missing.append(label)
        elif len(matches) > 1:
            duplicate.append(label)

    if missing or duplicate:
        errors.append(
            {
                "code": "INCOMPLETE_DAYUN_ASSESSMENT",
                "path": "/dayun_assessment",
                "detail": "dayun stages must uniquely cover birth-to-qiyun and every deterministic period",
                "missing_stages": missing,
                "duplicate_stages": duplicate,
            }
        )

    theme_keywords = ("事业", "财", "感情", "六亲", "健康", "承接", "结构")
    for index, item in enumerate(analysis.dayun_assessment):
        text = " ".join(str(value) for value in item.values())
        if index not in qiyun_hits and sum(keyword in text for keyword in theme_keywords) < 3:
            warnings.append(
                {
                    "code": "DAYUN_THEME_COVERAGE_WEAK",
                    "path": f"/dayun_assessment/{index}",
                    "detail": "该阶段的事业、财运、感情六亲、健康或承接说明较少",
                }
            )

    if len(errors) == len(validation.errors) and len(warnings) == len(validation.warnings):
        return validation
    status = "failed" if errors else "passed"
    return validation.model_copy(
        update={
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "approved_claim_ids": validation.approved_claim_ids if status == "passed" else [],
            "required_revisions": sorted(
                {str(error.get("code", "VALIDATION_ERROR")) for error in errors}
            ),
        }
    )


def _supplement_deterministic_dayun_stages(
    chart: ChartResultDTO, analysis: StructuredAnalysisDTO
) -> StructuredAnalysisDTO:
    """List missing deterministic dayun stages without inventing an interpretation."""
    dayun = chart.dayun or []
    if not dayun:
        return analysis

    items = list(analysis.dayun_assessment)
    searchable_stages = [str(item.get("stage", "")).casefold() for item in items]
    additions: list[dict[str, Any]] = []
    if not any(
        "起运" in stage or "qiyun" in stage or "birth" in stage for stage in searchable_stages
    ):
        additions.append(
            {
                "stage": "出生至起运",
                "conclusion": "仅列示确定性起运前阶段；扩展解读未通过校验，暂不作趋势断言。",
                "coverage_status": "deterministic_fallback",
                "interpretation_status": "missing",
                "fact_ids": [],
                "rule_ids": [],
                "evidence_ids": [],
            }
        )

    for item in dayun:
        markers = [
            str(item.get("ganzhi", "")).casefold(),
            str(item.get("fact_id", "")).casefold(),
        ]
        if any(marker and marker in stage for marker in markers for stage in searchable_stages):
            continue
        ganzhi = str(item.get("ganzhi", "大运"))
        start_year = item.get("start_year")
        end_year = item.get("end_year")
        additions.append(
            {
                "stage": f"{ganzhi}大运（{start_year}—{end_year}）",
                "conclusion": "仅列示确定性排盘阶段；扩展解读未通过校验，暂不作趋势断言。",
                "coverage_status": "deterministic_fallback",
                "interpretation_status": "missing",
                "fact_ids": [str(item["fact_id"])] if item.get("fact_id") else [],
                "rule_ids": [str(item["rule_id"])] if item.get("rule_id") else [],
                "evidence_ids": [],
            }
        )

    if not additions:
        return analysis
    limitation = "部分大运阶段仅保留确定性排盘信息，未作未经校验的扩展解读。"
    limitations = list(analysis.limitations)
    if limitation not in limitations:
        limitations.append(limitation)
    return analysis.model_copy(
        update={"dayun_assessment": [*items, *additions], "limitations": limitations}
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

    cleaned = analysis
    rejected = {str(e["claim_id"]) for e in validation.errors if e.get("claim_id")}
    remaining = [claim for claim in analysis.claims if claim.claim_id not in rejected]
    if rejected and remaining:
        limitations = list(cleaned.limitations)
        limitations.append(f"已移除 {len(rejected)} 条未通过确定性引用校验的模型结论。")
        cleaned = cleaned.model_copy(update={"claims": remaining, "limitations": limitations})

    if "INCOMPLETE_DAYUN_ASSESSMENT" in validation.required_revisions:
        cleaned = _supplement_deterministic_dayun_stages(chart, cleaned)
    if cleaned is analysis:
        return analysis, validation

    repaired_validation = verify_analysis(
        chart=chart,
        evidence=evidence,
        analysis=cleaned,
        configured_school=school,
        computed_relations=relations,
    )
    return cleaned, _enforce_core_topic_coverage(
        chart=chart, analysis=cleaned, validation=repaired_validation
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
    def __init__(self, *, provider: StructuredOutputProvider) -> None:
        self.provider = provider
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

        trace_id = f"analysis_{uuid.uuid4().hex[:12]}"
        relations = _relations(chart)
        shensha = _shensha(chart)
        context = build_analysis_context(
            chart=chart,
            computed_relations=relations,
            computed_shensha=shensha,
        )
        evidence: tuple[RetrievedEvidence, ...] = ()

        schema_path = (
            Path(__file__).resolve().parents[4]
            / "contracts"
            / "schemas"
            / "analysis_output.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        payload: dict[str, Any] = {
            "chart_id": chart.chart_id,
            "calculation_profile_id": chart.calculation_profile_id,
            "analysis_context": context,
            "analysis_profile": {
                "school": school,
                "methodology": "ziping_structure_first_with_tiaohou_pattern_bingyao_tongguan",
                "nayin_role": "secondary_only",
                "shensha_role": "auxiliary_only",
            },
            "output_contract": {
                "schema": "analysis-output-v1",
                "required_sections": [
                    "executive_summary",
                    "reasoning_summary",
                    "structure_assessment",
                    "kinship_assessment",
                    "health_assessment",
                    "dayun_assessment",
                    "claims",
                    "limitations",
                ],
                "claim_references": "fact_ids required; rule_ids and evidence_ids empty",
                "reflection": "program_generated",
            },
            "user_focus": list(user_focus),
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
        repair_paths: set[str] = set()

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
                    paths=repair_paths,
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
            analysis = analysis.model_copy(
                update={
                    "reflection": build_programmatic_reflection(
                        analysis=analysis, validation=validation
                    )
                }
            )
            candidate_payload = analysis.model_dump(mode="json")
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "request_kind": request_kind,
                    "system_prompt": request_system_prompt,
                    "prompt_version": request_prompt_version,
                    "input_payload": request_payload,
                    "output_schema": request_schema,
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
            if validation.status == "passed" or attempt == max_revisions:
                break
            if on_stage:
                on_stage("revision_pending")

            repair_paths = _repair_paths(analysis, validation)
            if repair_paths:
                request_kind = "local_repair"
                request_payload = _build_local_repair_payload(
                    base_payload=payload,
                    analysis=analysis,
                    validation=validation,
                    paths=repair_paths,
                )
                request_schema = _local_repair_schema(repair_paths)
                request_system_prompt = LOCAL_REPAIR_SYSTEM_PROMPT
                request_prompt_version = LOCAL_REPAIR_PROMPT_VERSION
            else:
                # Rare cross-cutting failures still use a coherent full rewrite.  The
                # initial call remains a single global analysis; this fallback exists
                # only when the validator cannot safely isolate a section.
                request_kind = "full_revision"
                request_payload = {
                    **payload,
                    "request_kind": "full_revision_after_unscoped_failure",
                    "validation_errors": validation.errors,
                    "revision_guidance": [
                        _REVISION_GUIDANCE.get(code, code) for code in validation.required_revisions
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
        analysis = analysis.model_copy(
            update={
                "reflection": build_programmatic_reflection(
                    analysis=analysis, validation=validation
                )
            }
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
            "analysis_trace_id": trace_id,
            "retrieval_trace_id": trace_id,
            "rag_enabled": False,
            "prompt_version": primary_response.prompt_version,
            "model_id": primary_response.model_id,
            "system_prompt": INTERPRETER_SYSTEM_PROMPT,
            # Every attempt retains its exact prompt and raw model payload, whether
            # validation passed or failed.
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
