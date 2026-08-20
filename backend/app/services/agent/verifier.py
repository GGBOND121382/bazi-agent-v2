"""Deterministic validation for model-produced structured analyses.

The verifier does not judge school-based conclusions such as 旺衰、格局或喜用。
It protects facts that can be checked mechanically: IDs, 十神、藏干、五行生克、
基础干支关系、岁运阶段和 high-risk absolute claims.
"""
from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from ...api.dto import (
    AnalysisReflectionDTO,
    ChartResultDTO,
    FactDTO,
    StructuredAnalysisDTO,
    ValidationResultDTO,
)
from ...domain.pillars import EARTHLY_BRANCHES, HEAVENLY_STEMS, Branch, Pillar, Stem, ten_god_of
from ...domain.rules.relations import relation_rule_catalog
from ..rag.models import RetrievedEvidence
from .context import build_analysis_context

_RISK = re.compile(
    r"(?:必然|注定|保证|百分之百)(?:死亡|患病|离婚|破产|发财|盈利)|"
    r"(?:替代医生|无需就医|停止治疗)|(?:保证盈利|稳赚不赔)",
    re.IGNORECASE,
)
_GANZHI = frozenset("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")
_TEN_GODS = (
    "比肩",
    "劫财",
    "食神",
    "伤官",
    "偏财",
    "正财",
    "七杀",
    "正官",
    "偏印",
    "正印",
)
_ELEMENT_ZH_TO_EN = {"木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water"}
_SYMBOL_PATTERN = r"[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥木火土金水]"
_TEN_GOD_AFTER = re.compile(
    rf"(?P<stem>[甲乙丙丁戊己庚辛壬癸])(?:木|火|土|金|水)?(?:为|是|属|对应)(?:日主(?:之|的)?)?(?P<god>{'|'.join(_TEN_GODS)})"
)
_TEN_GOD_BEFORE = re.compile(
    rf"(?P<god>{'|'.join(_TEN_GODS)})(?P<stem>[甲乙丙丁戊己庚辛壬癸])(?:木|火|土|金|水)?"
)
_STEM_HIDDEN_IN_BRANCHES = re.compile(
    r"(?P<stem>[甲乙丙丁戊己庚辛壬癸])(?:木|火|土|金|水)?"
    r"(?:分别|同时|也)?(?:藏于|藏在|藏入)(?:年|月|日|时)?支?"
    r"(?P<branches>[子丑寅卯辰巳午未申酉戌亥、，和及]+)"
)
_BRANCH_HIDES_STEMS = re.compile(
    r"(?P<branch>[子丑寅卯辰巳午未申酉戌亥])(?:支)?(?:中|内)?"
    r"(?:藏|藏有|所藏)(?P<stems>(?:[甲乙丙丁戊己庚辛壬癸](?:木|火|土|金|水)?[、，和及]?)+)"
)
_ELEMENT_ACTION = re.compile(
    rf"(?P<left>{_SYMBOL_PATTERN})(?:木|火|土|金|水)?(?P<action>生|克)(?P<right>{_SYMBOL_PATTERN})(?:木|火|土|金|水)?"
)
_ELEMENT_PASSIVE_CONTROL = re.compile(
    rf"(?P<right>{_SYMBOL_PATTERN})(?:木|火|土|金|水)?(?:被|受)(?P<left>{_SYMBOL_PATTERN})(?:木|火|土|金|水)?(?:所)?克"
)
_STEM_RELATION = re.compile(
    r"(?P<left>[甲乙丙丁戊己庚辛壬癸])(?:木|火|土|金|水)?(?:与|和)?"
    r"(?P<right>[甲乙丙丁戊己庚辛壬癸])(?:木|火|土|金|水)?"
    r"(?:构成|形成|相)?(?P<relation>五合|合|冲)"
)
_BRANCH_RELATION = re.compile(
    r"(?P<left>[子丑寅卯辰巳午未申酉戌亥])(?:与|和)?(?P<right>[子丑寅卯辰巳午未申酉戌亥])"
    r"(?:构成|形成|相)?(?P<relation>暗合|拱合|半合|六合|拱会|半会|冲|合|会|刑|害|破)"
)
_BRANCH_TRIPLE_RELATION = re.compile(
    r"(?P<first>[子丑寅卯辰巳午未申酉戌亥])(?:、|，|与|和)?"
    r"(?P<second>[子丑寅卯辰巳午未申酉戌亥])(?:、|，|与|和)?"
    r"(?P<third>[子丑寅卯辰巳午未申酉戌亥])"
    r"(?:构成|形成|成|为)?(?P<relation>三合|三会|三刑)"
)
_PILLAR_RELATION = re.compile(
    r"(?P<left>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])(?:与|和|对)?"
    r"(?P<right>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
    r"(?:构成|形成|相|为|呈)?(?P<relation>天克地冲|天合地合|伏吟|反吟)"
)
_INTERNAL_PILLAR_RELATION = re.compile(
    r"(?P<ganzhi>[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
    r"(?:为|属|呈|是)?(?P<relation>盖头|截脚)"
)


def _error(code: str, claim_id: str | None, detail: str, *, path: str | None = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "detail": detail}
    if claim_id:
        payload["claim_id"] = claim_id
    if path:
        payload["path"] = path
    payload.update(extra)
    return payload


def _walk_dicts(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        item = cast(dict[str, Any], value)
        yield item
        for child in item.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list | tuple):
        for child in value:
            yield from _walk_dicts(child)


def _walk_text(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        if value.strip():
            yield path or "/", value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_text(child, f"{path}/{key}")
    elif isinstance(value, list | tuple):
        for index, child in enumerate(value):
            yield from _walk_text(child, f"{path}/{index}")


def _deterministic_shensha(chart: ChartResultDTO) -> tuple[dict[str, Any], ...]:
    details = chart.calendar.get("deterministic_details", {})
    if not isinstance(details, dict):
        return ()
    raw = details.get("shensha", [])
    if not isinstance(raw, list):
        return ()
    return tuple(cast(dict[str, Any], item) for item in raw if isinstance(item, dict))


def _deterministic_temporal_items(chart: ChartResultDTO) -> tuple[dict[str, Any], ...]:
    seen: set[int] = set()
    items: list[dict[str, Any]] = []
    for root in (chart.qiyun, chart.dayun, chart.temporal_context):
        for item in _walk_dicts(root):
            if not item.get("fact_id") and not item.get("rule_id"):
                continue
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            items.append(item)
    return tuple(items)


@dataclass(frozen=True, slots=True)
class _ReferenceIndexes:
    fact_index: dict[str, FactDTO]
    relation_fact_index: dict[str, dict[str, Any]]
    temporal_fact_index: dict[str, dict[str, Any]]
    temporal_rule_index: dict[str, list[dict[str, Any]]]
    shensha_rule_index: dict[str, list[dict[str, Any]]]
    known_fact_ids: set[str]
    known_rules: set[str]


def _append_rule_item(index: dict[str, list[dict[str, Any]]], item: dict[str, Any]) -> None:
    rule_id = str(item.get("rule_id", ""))
    if rule_id:
        index.setdefault(rule_id, []).append(item)


def _build_reference_indexes(
    *,
    chart: ChartResultDTO,
    relation_items: tuple[dict[str, Any], ...],
) -> _ReferenceIndexes:
    shensha_rule_index: dict[str, list[dict[str, Any]]] = {}
    for item in _deterministic_shensha(chart):
        _append_rule_item(shensha_rule_index, item)

    temporal_items = _deterministic_temporal_items(chart)
    temporal_fact_index = {
        str(item["fact_id"]): item for item in temporal_items if item.get("fact_id")
    }
    temporal_rule_index: dict[str, list[dict[str, Any]]] = {}
    for item in temporal_items:
        _append_rule_item(temporal_rule_index, item)

    fact_index = {fact.fact_id: fact for fact in chart.facts}
    relation_fact_index = {
        str(item["fact_id"]): item for item in relation_items if item.get("fact_id")
    }
    known_rules = (
        {fact.rule_id for fact in chart.facts}
        | {str(item["rule_id"]) for item in relation_items if item.get("rule_id")}
        | set(temporal_rule_index)
        | set(shensha_rule_index)
    )
    return _ReferenceIndexes(
        fact_index=fact_index,
        relation_fact_index=relation_fact_index,
        temporal_fact_index=temporal_fact_index,
        temporal_rule_index=temporal_rule_index,
        shensha_rule_index=shensha_rule_index,
        known_fact_ids=set(fact_index) | set(relation_fact_index) | set(temporal_fact_index),
        known_rules=known_rules,
    )


def _referenced_text(
    *,
    fact_ids: Iterable[str],
    rule_ids: Iterable[str],
    indexes: _ReferenceIndexes,
) -> str:
    parts = [
        json.dumps(indexes.fact_index[fact_id].value, ensure_ascii=False, default=str)
        for fact_id in fact_ids
        if fact_id in indexes.fact_index
    ]
    parts.extend(
        json.dumps(indexes.relation_fact_index[fact_id], ensure_ascii=False, default=str)
        for fact_id in fact_ids
        if fact_id in indexes.relation_fact_index
    )
    parts.extend(
        json.dumps(indexes.temporal_fact_index[fact_id], ensure_ascii=False, default=str)
        for fact_id in fact_ids
        if fact_id in indexes.temporal_fact_index
    )
    parts.extend(
        json.dumps(item, ensure_ascii=False, default=str)
        for rule_id in rule_ids
        for item in indexes.temporal_rule_index.get(rule_id, [])
    )
    parts.extend(
        json.dumps(item, ensure_ascii=False, default=str)
        for rule_id in rule_ids
        for item in indexes.shensha_rule_index.get(rule_id, [])
    )
    return " ".join(parts)


@lru_cache(maxsize=1)
def _element_cycles() -> tuple[dict[str, str], dict[str, str]]:
    path = Path(__file__).resolve().parents[4] / "contracts" / "core_tables" / "five_elements.json"
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    return (
        {str(k): str(v) for k, v in cast(dict[str, object], payload["generates"]).items()},
        {str(k): str(v) for k, v in cast(dict[str, object], payload["controls"]).items()},
    )


def _element_of(symbol: str) -> str | None:
    if symbol in _ELEMENT_ZH_TO_EN:
        return _ELEMENT_ZH_TO_EN[symbol]
    if symbol in HEAVENLY_STEMS:
        return Stem(symbol).element
    if symbol in EARTHLY_BRANCHES:
        return Branch(symbol).element
    return None


def _semantic_rule_errors(
    chart: ChartResultDTO,
    analysis: StructuredAnalysisDTO,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    day_master = Stem(chart.day_master)
    analysis_payload = analysis.model_dump(mode="json")
    catalog = relation_rule_catalog()
    generates, controls = _element_cycles()
    seen_errors: set[tuple[str, str, str]] = set()
    seen_warnings: set[tuple[str, str, str]] = set()

    def add(code: str, path: str, detail: str, **extra: Any) -> None:
        key = (code, path, detail)
        if key not in seen_errors:
            seen_errors.add(key)
            errors.append(_error(code, None, detail, path=path, **extra))

    def warn(code: str, path: str, detail: str, **extra: Any) -> None:
        key = (code, path, detail)
        if key not in seen_warnings:
            seen_warnings.add(key)
            warnings.append(_error(code, None, detail, path=path, **extra))

    def allowed_hidden_stems(branch: str) -> list[str]:
        branch_obj = Branch(branch)
        compatible_stem = Stem("甲" if branch_obj.index % 2 == 0 else "乙")
        return [item.char for item in Pillar(compatible_stem, branch_obj).hidden_stems()]

    def check_element_relation(
        *, left: str, right: str, action: str, path: str
    ) -> None:
        left_element = _element_of(left)
        right_element = _element_of(right)
        if not left_element or not right_element:
            return
        cycle = generates if action == "生" else controls
        if cycle.get(left_element) != right_element:
            add(
                "INVALID_ELEMENT_RELATION",
                path,
                f"{left}{action}{right}的五行方向不成立",
                assertion={
                    "predicate": "generates" if action == "生" else "controls",
                    "subject": left,
                    "object": right,
                },
                expected={"left_element": left_element, "right_element": cycle.get(left_element)},
            )

    for path, text in _walk_text(analysis_payload):
        # Reflection contains prior diagnostics and may quote rejected text verbatim.
        if path == "/reflection" or path.startswith("/reflection/"):
            continue

        for pattern in (_TEN_GOD_AFTER, _TEN_GOD_BEFORE):
            for match in pattern.finditer(text):
                stem = match.group("stem")
                stated = match.group("god")
                expected = ten_god_of(day_master, Stem(stem))
                if expected and stated != expected:
                    add(
                        "TEN_GOD_MISMATCH",
                        path,
                        f"{chart.day_master}日主见{stem}应为{expected}，不是{stated}",
                        assertion={"predicate": "ten_god", "subject": stem, "value": stated},
                        expected=expected,
                    )

        # Validate every branch in statements such as “辛金藏于戌未之中”.
        for match in _STEM_HIDDEN_IN_BRANCHES.finditer(text):
            stem = match.group("stem")
            for branch in re.findall(r"[子丑寅卯辰巳午未申酉戌亥]", match.group("branches")):
                allowed = allowed_hidden_stems(branch)
                if stem not in allowed:
                    add(
                        "INVALID_HIDDEN_STEM",
                        path,
                        f"{branch}的藏干为{'、'.join(allowed)}，不含{stem}",
                        assertion={"predicate": "hidden_in", "subject": stem, "object": branch},
                        expected={"allowed_hidden_stems": allowed},
                    )
        # Validate every stem in statements such as “申中藏庚壬戊”.
        for match in _BRANCH_HIDES_STEMS.finditer(text):
            branch = match.group("branch")
            allowed = allowed_hidden_stems(branch)
            for stem in re.findall(r"[甲乙丙丁戊己庚辛壬癸]", match.group("stems")):
                if stem not in allowed:
                    add(
                        "INVALID_HIDDEN_STEM",
                        path,
                        f"{branch}的藏干为{'、'.join(allowed)}，不含{stem}",
                        assertion={"predicate": "hidden_in", "subject": stem, "object": branch},
                        expected={"allowed_hidden_stems": allowed},
                    )

        for match in _ELEMENT_ACTION.finditer(text):
            # “乙木生申月” means “born in the Shen month”, not “wood generates metal”.
            if (
                match.group("action") == "生"
                and match.group("right") in EARTHLY_BRANCHES
                and match.group(0).endswith(match.group("right"))
                and text[match.end():].startswith("月")
            ):
                continue
            check_element_relation(
                left=match.group("left"),
                right=match.group("right"),
                action=match.group("action"),
                path=path,
            )
        for match in _ELEMENT_PASSIVE_CONTROL.finditer(text):
            check_element_relation(
                left=match.group("left"),
                right=match.group("right"),
                action="克",
                path=path,
            )

        for match in _STEM_RELATION.finditer(text):
            pair = frozenset((match.group("left"), match.group("right")))
            relation = match.group("relation")
            valid = (
                pair in catalog.stem_clashes
                if relation == "冲"
                else pair in catalog.stem_combinations
            )
            if not valid:
                add(
                    "INVALID_STEM_RELATION",
                    path,
                    f"未发现{match.group('left')}{match.group('right')}{relation}的确定性天干规则",
                    assertion={
                        "predicate": f"stem_{relation}",
                        "participants": [match.group("left"), match.group("right")],
                    },
                )

        for match in _BRANCH_RELATION.finditer(text):
            left = match.group("left")
            right = match.group("right")
            pair = frozenset((left, right))
            relation = match.group("relation")
            candidate_labels: list[str] = []
            if pair in catalog.branch_six_combinations:
                candidate_labels.append("六合")
            if pair in catalog.half_combinations:
                candidate_labels.append("半合")
            if pair in catalog.arching_combinations:
                candidate_labels.append("拱合候选")
            if pair in catalog.hidden_combinations:
                candidate_labels.append("暗合候选")
            if pair in catalog.half_meetings:
                candidate_labels.append("半会")
            if pair in catalog.arching_meetings:
                candidate_labels.append("拱会候选")

            valid = False
            if relation == "六合":
                valid = pair in catalog.branch_six_combinations
            elif relation == "半合":
                valid = pair in catalog.half_combinations
            elif relation == "拱合":
                valid = pair in catalog.arching_combinations
            elif relation == "暗合":
                valid = pair in catalog.hidden_combinations
            elif relation == "合":
                valid = any(label in candidate_labels for label in ("六合", "半合", "拱合候选", "暗合候选"))
                if valid and candidate_labels != ["六合"]:
                    warn(
                        "AMBIGUOUS_BRANCH_COMBINATION_TERM",
                        path,
                        f"{left}{right}笼统写作‘合’，实际候选为{'、'.join(candidate_labels)}，应明确类型",
                    )
            elif relation == "半会":
                valid = pair in catalog.half_meetings
            elif relation == "拱会":
                valid = pair in catalog.arching_meetings
            elif relation == "会":
                valid = pair in catalog.half_meetings or pair in catalog.arching_meetings
                if valid:
                    labels = [
                        label
                        for label in candidate_labels
                        if label in {"半会", "拱会候选"}
                    ]
                    warn(
                        "AMBIGUOUS_BRANCH_MEETING_TERM",
                        path,
                        f"{left}{right}笼统写作‘会’，实际候选为{'、'.join(labels)}，应明确类型",
                    )
            elif relation == "冲":
                valid = pair in catalog.branch_clashes
            elif relation == "害":
                valid = pair in catalog.branch_harms
            elif relation == "破":
                valid = pair in catalog.branch_breaks
            elif relation == "刑":
                valid = (
                    pair in catalog.mutual_punishments
                    or pair in catalog.punishment_triggers
                    or (left == right and left in catalog.self_punishments)
                )
                if pair in catalog.punishment_triggers:
                    warn(
                        "PARTIAL_THREE_PUNISHMENT_TRIGGER",
                        path,
                        f"{left}{right}为三刑中的两支触发，不等于三刑齐全",
                    )

            if not valid:
                add(
                    "INVALID_BRANCH_RELATION",
                    path,
                    f"未发现{left}{right}{relation}的确定性地支规则",
                    assertion={
                        "predicate": f"branch_{relation}",
                        "participants": [left, right],
                    },
                )

        for match in _BRANCH_TRIPLE_RELATION.finditer(text):
            branches = [match.group("first"), match.group("second"), match.group("third")]
            group = frozenset(branches)
            relation = match.group("relation")
            table = {
                "三合": catalog.three_combinations,
                "三会": catalog.three_meetings,
                "三刑": catalog.three_punishments,
            }[relation]
            if len(group) != 3 or group not in table:
                add(
                    "INVALID_BRANCH_GROUP_RELATION",
                    path,
                    f"未发现{''.join(branches)}{relation}的确定性地支规则",
                    assertion={"predicate": f"branch_{relation}", "participants": branches},
                )

        for match in _PILLAR_RELATION.finditer(text):
            left = match.group("left")
            right = match.group("right")
            relation = match.group("relation")
            stem_pair = frozenset((left[0], right[0]))
            branch_pair = frozenset((left[1], right[1]))
            left_stem_element = Stem(left[0]).element
            right_stem_element = Stem(right[0]).element
            stem_control = (
                controls.get(left_stem_element) == right_stem_element
                or controls.get(right_stem_element) == left_stem_element
            )
            stem_clash = stem_pair in catalog.stem_clashes
            branch_clash = branch_pair in catalog.branch_clashes
            valid = False
            if relation == "伏吟":
                valid = left == right
            elif relation == "天克地冲":
                valid = stem_control and branch_clash
            elif relation == "反吟":
                valid = branch_clash and (stem_control or stem_clash)
            elif relation == "天合地合":
                valid = (
                    stem_pair in catalog.stem_combinations
                    and branch_pair in catalog.branch_six_combinations
                )
            if not valid:
                add(
                    "INVALID_PILLAR_RELATION",
                    path,
                    f"未发现{left}与{right}{relation}的确定性干支规则",
                    assertion={"predicate": relation, "participants": [left, right]},
                )

        for match in _INTERNAL_PILLAR_RELATION.finditer(text):
            ganzhi = match.group("ganzhi")
            relation = match.group("relation")
            stem_element = Stem(ganzhi[0]).element
            branch_element = Branch(ganzhi[1]).element
            valid = (
                controls.get(stem_element) == branch_element
                if relation == "盖头"
                else controls.get(branch_element) == stem_element
            )
            if not valid:
                add(
                    "INVALID_INTERNAL_PILLAR_RELATION",
                    path,
                    f"{ganzhi}不构成{relation}",
                    assertion={"predicate": relation, "participants": [ganzhi]},
                )

        if _RISK.search(text):
            add("POLICY_HIGH_RISK_ASSERTION", path, "包含绝对化高风险断言")

    return errors, warnings


def build_programmatic_reflection(
    *, analysis: StructuredAnalysisDTO, validation: ValidationResultDTO
) -> AnalysisReflectionDTO:
    """Create the authoritative reflection from deterministic checks, not model self-rating."""
    checked = [
        "schema_and_chart_identity",
        "reference_ids",
        "ten_god_mapping",
        "hidden_stems",
        "five_element_generation_control",
        "stem_branch_relation_catalog",
        "pillar_composite_relations",
        "dayun_stage_coverage",
        "high_risk_language",
    ]
    contradictions = [str(item.get("detail", item.get("code", ""))) for item in validation.errors]
    return AnalysisReflectionDTO(
        status="pass" if validation.status == "passed" else "revise",
        checked_dimensions=checked,
        missing_dimensions=[],
        contradictions=contradictions,
        revision_instructions=[
            f"修复 {item.get('path', item.get('claim_id', '对应字段'))}: {item.get('detail', item.get('code', ''))}"
            for item in validation.errors
        ],
        coverage_scores={
            "deterministic_rule_checks": 1.0 if validation.status == "passed" else 0.0,
            "model_declared_sections": min(
                1.0,
                (
                    len(analysis.kinship_assessment)
                    + len(analysis.health_assessment)
                    + len(analysis.dayun_assessment)
                )
                / max(1, 6 + 6 + len(analysis.dayun_assessment)),
            ),
        },
    )


def verify_analysis(
    *,
    chart: ChartResultDTO,
    evidence: Iterable[RetrievedEvidence] = (),
    analysis: StructuredAnalysisDTO,
    configured_school: str,
    computed_relations: Iterable[dict[str, Any]] = (),
) -> ValidationResultDTO:
    # RAG has been removed from report generation.  Keep the parameter for API
    # compatibility, but reject model-created evidence references.
    del evidence
    relation_items = tuple(computed_relations)
    indexes = _build_reference_indexes(chart=chart, relation_items=relation_items)
    # The model may cite any fact_id visible in the compact prompt.  Dayun relation
    # IDs are generated while enriching the prompt and are not stored in chart.dayun,
    # so index the exact same model-visible projection before validating references.
    visible_context = build_analysis_context(
        chart=chart,
        computed_relations=list(relation_items),
        computed_shensha=list(_deterministic_shensha(chart)),
    )
    for item in _walk_dicts(visible_context):
        fact_id = str(item.get("fact_id", "")).strip()
        if not fact_id:
            continue
        indexes.temporal_fact_index.setdefault(fact_id, item)
        indexes.known_fact_ids.add(fact_id)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    approved: list[str] = []

    if chart.calculation_status != "passed":
        errors.append({"code": "CHART_NOT_VALIDATED", "detail": "chart status must be passed"})
    if analysis.chart_id != chart.chart_id:
        errors.append({"code": "CHART_ID_MISMATCH", "detail": "analysis references another chart"})
    if analysis.school != configured_school:
        errors.append({"code": "SCHOOL_MISMATCH", "detail": "analysis school is not configured"})

    for section_name, items in (
        ("kinship_assessment", analysis.kinship_assessment),
        ("dayun_assessment", analysis.dayun_assessment),
    ):
        for index, item in enumerate(items):
            referenced_ids: set[str] = set()
            for key in ("fact_refs", "fact_ids", "trel_refs"):
                raw = item.get(key, [])
                if isinstance(raw, list):
                    referenced_ids.update(str(value) for value in raw if value)
            missing_facts = sorted(referenced_ids - indexes.known_fact_ids)
            if missing_facts:
                errors.append(
                    {
                        "code": "UNKNOWN_FACT",
                        "path": f"/{section_name}/{index}",
                        "detail": ",".join(missing_facts),
                    }
                )

    for claim in analysis.claims:
        before = len(errors)
        missing_facts = sorted(set(claim.fact_ids) - indexes.known_fact_ids)
        missing_rules = sorted(set(claim.rule_ids) - indexes.known_rules)
        if missing_facts:
            errors.append(_error("UNKNOWN_FACT", claim.claim_id, ",".join(missing_facts)))
        if missing_rules:
            errors.append(_error("UNKNOWN_RULE", claim.claim_id, ",".join(missing_rules)))
        if claim.evidence_ids:
            errors.append(
                _error(
                    "EVIDENCE_DISABLED",
                    claim.claim_id,
                    "RAG evidence_ids are disabled; remove these IDs",
                )
            )
        if claim.school and claim.school != configured_school:
            errors.append(_error("CLAIM_SCHOOL_MISMATCH", claim.claim_id, claim.school))
        if _RISK.search(claim.statement):
            errors.append(_error("POLICY_HIGH_RISK_ASSERTION", claim.claim_id, "absolute unsafe assertion"))

        referenced_text = _referenced_text(
            fact_ids=claim.fact_ids,
            rule_ids=claim.rule_ids,
            indexes=indexes,
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

    semantic_errors, semantic_warnings = _semantic_rule_errors(chart, analysis)
    errors.extend(semantic_errors)
    warnings.extend(semantic_warnings)

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
