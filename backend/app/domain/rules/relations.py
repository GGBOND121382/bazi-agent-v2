"""Deterministic 天干地支 relation engines.

The engine emits structural facts only.  A hit never means that a combination
has transformed or that a clash/punishment is necessarily inauspicious.  Every
extended APP-compatible rule is tagged with a variant and an explicit basis so
that downstream prompts can distinguish classical core rules from compatibility
candidates.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, cast

from ..pillars import FourPillars, Pillar

CORE_TABLES = Path(__file__).resolve().parents[4] / "contracts" / "core_tables"
REL_FILE = CORE_TABLES / "stem_branch_relations.json"
ELEMENT_FILE = CORE_TABLES / "five_elements.json"
_STEM_CLASHES = (("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"))
_SELF_PUNISHMENT_BRANCHES = frozenset({"辰", "午", "酉", "亥"})
_FOUR_TOMBS = frozenset({"辰", "戌", "丑", "未"})
RuleProfile = Literal["ziping_conservative_v1", "wenzhen_compatible_v1"]
DEFAULT_RULE_PROFILE: RuleProfile = "wenzhen_compatible_v1"


@lru_cache(maxsize=1)
def _relations() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(REL_FILE.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _element_controls() -> dict[str, str]:
    payload = cast(dict[str, Any], json.loads(ELEMENT_FILE.read_text(encoding="utf-8")))
    raw = payload.get("controls", {})
    return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


@dataclass(frozen=True, slots=True)
class BranchRelation:
    """Compatibility relation returned for a natal FourPillars chart."""

    type: str
    branches: tuple[str, ...]
    element: str | None
    rule_id: str
    positions: tuple[str, ...] = ()
    direction: str | None = None
    basis: tuple[str, ...] = ()
    variant: str = "ziping_conservative_v1"


@dataclass(frozen=True, slots=True)
class PositionedPillar:
    """A pillar with a stable position identifier."""

    position: str
    pillar: Pillar


@dataclass(frozen=True, slots=True)
class PositionedRelation:
    """A position-aware deterministic relation candidate."""

    type: str
    participants: tuple[PositionedPillar, ...]
    symbols: tuple[str, ...]
    element: str | None
    rule_id: str
    direction: str | None = None
    basis: tuple[str, ...] = ()
    variant: str = "ziping_conservative_v1"


def _dict_items(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, Any], item) for item in raw if isinstance(item, dict)]


def _pair_items(raw: object) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, list) and len(item) == 2:
            result.append((str(item[0]), str(item[1])))
    return result


def _pair_set(raw: object) -> set[frozenset[str]]:
    return {frozenset(pair) for pair in _pair_items(raw)}


def _combination_map(raw: object, key: str) -> dict[frozenset[str], str | None]:
    result: dict[frozenset[str], str | None] = {}
    for item in _dict_items(raw):
        values = item.get(key)
        if not isinstance(values, list):
            continue
        result[frozenset(str(value) for value in values)] = (
            str(item.get("transformation_candidate") or item.get("element") or "") or None
        )
    return result


def _unordered_match(left: str, right: str, pair: tuple[str, str]) -> bool:
    return {left, right} == set(pair)


def _stem_control_direction(
    left: PositionedPillar, right: PositionedPillar
) -> tuple[PositionedPillar, PositionedPillar] | None:
    controls = _element_controls()
    if controls.get(left.pillar.stem.element) == right.pillar.stem.element:
        return left, right
    if controls.get(right.pillar.stem.element) == left.pillar.stem.element:
        return right, left
    return None


def _pair_relations(  # noqa: PLR0915
    left: PositionedPillar,
    right: PositionedPillar,
    rels: dict[str, Any],
    rule_profile: RuleProfile,
) -> list[PositionedRelation]:
    hits: list[PositionedRelation] = []
    stem_pair = (left.pillar.stem.char, right.pillar.stem.char)
    branch_pair = (left.pillar.branch.char, right.pillar.branch.char)
    branch_set = frozenset(branch_pair)

    if left.pillar.ganzhi == right.pillar.ganzhi:
        hits.append(
            PositionedRelation(
                "fuyin",
                (left, right),
                (left.pillar.ganzhi, right.pillar.ganzhi),
                None,
                "PILLAR-FUYIN-EXACT-001",
                basis=("same_stem", "same_branch", "same_ganzhi"),
            )
        )
    if stem_pair[0] == stem_pair[1]:
        hits.append(
            PositionedRelation(
                "stem_repeat",
                (left, right),
                stem_pair,
                left.pillar.stem.element,
                "STEM-REPEAT-001",
            )
        )
    if branch_pair[0] == branch_pair[1]:
        hits.append(
            PositionedRelation(
                "branch_repeat",
                (left, right),
                branch_pair,
                left.pillar.branch.element,
                "BRANCH-REPEAT-001",
            )
        )

    stem_combinations = _combination_map(rels.get("stem_five_combinations"), "pair")
    stem_combo_key = frozenset(stem_pair)
    if stem_combo_key in stem_combinations:
        canonical_stem_pair = next(
            pair for pair in _pair_items([item.get("pair") for item in _dict_items(rels.get("stem_five_combinations"))])
            if frozenset(pair) == stem_combo_key
        )
        hits.append(
            PositionedRelation(
                "stem_combination",
                (left, right),
                canonical_stem_pair,
                stem_combinations[stem_combo_key],
                "STEM-FIVE-COMBINATION-001",
            )
        )

    matched_stem_clash = next(
        (pair for pair in _STEM_CLASHES if _unordered_match(*stem_pair, pair)), None
    )
    stem_is_clash = matched_stem_clash is not None
    if matched_stem_clash is not None:
        hits.append(
            PositionedRelation(
                "stem_clash", (left, right), matched_stem_clash, None, "STEM-CLASH-001"
            )
        )

    control = _stem_control_direction(left, right)
    if control is not None:
        controller, controlled = control
        hits.append(
            PositionedRelation(
                "stem_control",
                (controller, controlled),
                (controller.pillar.stem.char, controlled.pillar.stem.char),
                f"{controller.pillar.stem.element}_controls_{controlled.pillar.stem.element}",
                "STEM-FIVE-ELEMENT-CONTROL-001",
                direction=f"{controller.position}_controls_{controlled.position}",
            )
        )

    branch_combinations = _combination_map(rels.get("branch_six_combinations"), "pair")
    if branch_set in branch_combinations:
        canonical_branch_pair = next(
            pair for pair in _pair_items([item.get("pair") for item in _dict_items(rels.get("branch_six_combinations"))])
            if frozenset(pair) == branch_set
        )
        hits.append(
            PositionedRelation(
                "six_combination",
                (left, right),
                canonical_branch_pair,
                branch_combinations[branch_set],
                "BRANCH-SIX-COMBINATION-001",
            )
        )

    matched_branch_clash = next(
        (pair for pair in _pair_items(rels.get("branch_clashes")) if frozenset(pair) == branch_set),
        None,
    )
    branch_is_clash = matched_branch_clash is not None
    if matched_branch_clash is not None:
        hits.append(
            PositionedRelation("clash", (left, right), matched_branch_clash, None, "BRANCH-CLASH-001")
        )
    matched_harm = next(
        (pair for pair in _pair_items(rels.get("branch_harms")) if frozenset(pair) == branch_set),
        None,
    )
    if matched_harm is not None:
        hits.append(
            PositionedRelation("harm", (left, right), matched_harm, None, "BRANCH-HARM-001")
        )
    raw_breaks = rels.get("branch_breaks")
    break_pairs = _pair_set(raw_breaks.get("pairs")) if isinstance(raw_breaks, dict) else set()
    if branch_set in break_pairs:
        canonical_break = next(
            pair for pair in _pair_items(raw_breaks.get("pairs") if isinstance(raw_breaks, dict) else [])
            if frozenset(pair) == branch_set
        )
        hits.append(
            PositionedRelation("break", (left, right), canonical_break, None, "BRANCH-BREAK-001")
        )

    punishments = _dict_items(rels.get("punishments"))
    mutual_pairs = {
        frozenset(str(value) for value in item.get("branches", []))
        for item in punishments
        if item.get("type") == "mutual_punishment"
    }
    if branch_set in mutual_pairs:
        canonical_mutual = next(
            tuple(str(value) for value in item.get("branches", []))
            for item in punishments
            if item.get("type") == "mutual_punishment"
            and frozenset(str(value) for value in item.get("branches", [])) == branch_set
        )
        hits.append(
            PositionedRelation(
                "punishment", (left, right), canonical_mutual, None, "BRANCH-PUNISHMENT-M-001"
            )
        )
    if branch_pair[0] == branch_pair[1] and branch_pair[0] in _SELF_PUNISHMENT_BRANCHES:
        hits.append(
            PositionedRelation(
                "punishment",
                (left, right),
                branch_pair,
                None,
                "BRANCH-PUNISHMENT-S-001",
                basis=("self_punishment",),
            )
        )

    if rule_profile == "wenzhen_compatible_v1":
        for item in _dict_items(rels.get("hidden_combinations")):
            raw_pair = item.get("pair")
            if not isinstance(raw_pair, list) or len(raw_pair) != 2:
                continue
            if branch_set != frozenset(str(value) for value in raw_pair):
                continue
            hidden_pairs = item.get("hidden_stem_pairs", [])
            basis = tuple(
                f"hidden_stems:{pair[0]!s}{pair[1]!s}"
                for pair in hidden_pairs
                if isinstance(pair, list) and len(pair) == 2
            )
            hits.append(
                PositionedRelation(
                    "hidden_combination",
                    (left, right),
                    tuple(str(value) for value in raw_pair),
                    str(item.get("element") or "") or None,
                    "BRANCH-HIDDEN-COMBINATION-WZ-001",
                    basis=basis or ("hidden_stem_five_combination",),
                    variant="wenzhen_compatible_v1",
                )
            )

    if branch_is_clash and (stem_is_clash or control is not None):
        basis = (
            ("stem_clash", "branch_clash")
            if stem_is_clash
            else ("stem_control", "branch_clash")
        )
        hits.append(
            PositionedRelation(
                "fanyin",
                (left, right),
                (left.pillar.ganzhi, right.pillar.ganzhi),
                None,
                "PILLAR-FANYIN-CANDIDATE-001",
                basis=basis,
            )
        )
    if branch_is_clash and control is not None:
        controller, controlled = control
        hits.append(
            PositionedRelation(
                "heaven_controls_earth_clashes",
                (controller, controlled),
                (controller.pillar.ganzhi, controlled.pillar.ganzhi),
                None,
                "PILLAR-TIANKEDICHONG-001",
                direction=f"{controller.position}_controls_{controlled.position}",
                basis=("stem_control", "branch_clash"),
            )
        )
    return hits


def _internal_pillar_relations(
    node: PositionedPillar, rule_profile: RuleProfile
) -> list[PositionedRelation]:
    if rule_profile != "wenzhen_compatible_v1":
        return []
    controls = _element_controls()
    stem_element = node.pillar.stem.element
    branch_element = node.pillar.branch.element
    if controls.get(stem_element) == branch_element:
        return [
            PositionedRelation(
                "covering",
                (node,),
                (node.pillar.ganzhi,),
                f"{stem_element}_controls_{branch_element}",
                "PILLAR-GAITOU-WZ-001",
                direction="stem_controls_branch",
                basis=(node.pillar.stem.char, node.pillar.branch.char),
                variant="wenzhen_compatible_v1",
            )
        ]
    if controls.get(branch_element) == stem_element:
        return [
            PositionedRelation(
                "cut_foot",
                (node,),
                (node.pillar.ganzhi,),
                f"{branch_element}_controls_{stem_element}",
                "PILLAR-JIEJIAO-WZ-001",
                direction="branch_controls_stem",
                basis=(node.pillar.branch.char, node.pillar.stem.char),
                variant="wenzhen_compatible_v1",
            )
        ]
    return []


def _full_group_relations(
    nodes: Sequence[PositionedPillar], rels: dict[str, Any]
) -> list[PositionedRelation]:
    hits: list[PositionedRelation] = []
    combo_map = _combination_map(rels.get("three_combinations"), "branches")
    meeting_map = _combination_map(rels.get("three_meetings"), "branches")
    punishment_sets = {
        frozenset(str(value) for value in item.get("branches", []))
        for item in _dict_items(rels.get("punishments"))
        if item.get("type") == "three_punishment"
    }
    for triple in combinations(nodes, 3):
        symbols = tuple(item.pillar.branch.char for item in triple)
        symbol_set = frozenset(symbols)
        if len(symbol_set) != 3:
            continue
        if symbol_set in combo_map:
            canonical_combo = next(
                tuple(str(value) for value in item.get("branches", []))
                for item in _dict_items(rels.get("three_combinations"))
                if frozenset(str(value) for value in item.get("branches", [])) == symbol_set
            )
            hits.append(
                PositionedRelation(
                    "three_combination",
                    triple,
                    canonical_combo,
                    combo_map[symbol_set],
                    "BRANCH-THREE-COMBINATION-001",
                )
            )
        if symbol_set in meeting_map:
            canonical_meeting = next(
                tuple(str(value) for value in item.get("branches", []))
                for item in _dict_items(rels.get("three_meetings"))
                if frozenset(str(value) for value in item.get("branches", [])) == symbol_set
            )
            hits.append(
                PositionedRelation(
                    "three_meeting",
                    triple,
                    canonical_meeting,
                    meeting_map[symbol_set],
                    "BRANCH-THREE-MEETING-001",
                )
            )
        if symbol_set in punishment_sets:
            canonical_punishment = next(
                tuple(str(value) for value in item.get("branches", []))
                for item in _dict_items(rels.get("punishments"))
                if item.get("type") == "three_punishment"
                and frozenset(str(value) for value in item.get("branches", [])) == symbol_set
            )
            hits.append(
                PositionedRelation(
                    "punishment",
                    triple,
                    canonical_punishment,
                    None,
                    "BRANCH-PUNISHMENT-3-001",
                    basis=("three_punishment_complete",),
                )
            )
    return hits


def _half_arch_and_punishment_candidates(
    nodes: Sequence[PositionedPillar],
    rels: dict[str, Any],
    rule_profile: RuleProfile,
) -> list[PositionedRelation]:
    hits: list[PositionedRelation] = []
    all_branches = {node.pillar.branch.char for node in nodes}

    for raw_groups, half_type, arch_type, half_rule, arch_rule in (
        (
            rels.get("three_combinations"),
            "half_combination",
            "arching_combination",
            "BRANCH-HALF-COMBINATION-001",
            "BRANCH-ARCHING-COMBINATION-WZ-001",
        ),
        (
            rels.get("three_meetings"),
            "half_meeting",
            "arching_meeting",
            "BRANCH-HALF-MEETING-001",
            "BRANCH-ARCHING-MEETING-WZ-001",
        ),
    ):
        for group in _dict_items(raw_groups):
            raw = group.get("branches")
            if not isinstance(raw, list) or len(raw) != 3:
                continue
            values = tuple(str(value) for value in raw)
            element = str(group.get("element") or "") or None
            adjacent = {
                frozenset((values[0], values[1])),
                frozenset((values[1], values[2])),
            }
            outer = frozenset((values[0], values[2]))
            for left, right in combinations(nodes, 2):
                pair = frozenset((left.pillar.branch.char, right.pillar.branch.char))
                if pair in adjacent:
                    canonical_half = (
                        (values[0], values[1])
                        if pair == frozenset((values[0], values[1]))
                        else (values[1], values[2])
                    )
                    hits.append(
                        PositionedRelation(
                            half_type, (left, right), canonical_half, element, half_rule
                        )
                    )
                elif (
                    rule_profile == "wenzhen_compatible_v1"
                    and pair == outer
                    and values[1] not in all_branches
                ):
                    hits.append(
                        PositionedRelation(
                            arch_type,
                            (left, right),
                            (values[0], values[2]),
                            element,
                            arch_rule,
                            basis=(f"missing_branch:{values[1]}",),
                            variant="wenzhen_compatible_v1",
                        )
                    )

    if rule_profile == "wenzhen_compatible_v1":
        for item in _dict_items(rels.get("punishments")):
            if item.get("type") != "three_punishment":
                continue
            raw = item.get("branches")
            if not isinstance(raw, list) or len(raw) != 3:
                continue
            punishment_group = tuple(str(value) for value in raw)
            if set(punishment_group) <= all_branches:
                continue
            allowed_pairs = {frozenset(pair) for pair in combinations(punishment_group, 2)}
            for left, right in combinations(nodes, 2):
                pair = frozenset((left.pillar.branch.char, right.pillar.branch.char))
                if pair not in allowed_pairs:
                    continue
                canonical_pair = tuple(value for value in punishment_group if value in pair)
                hits.append(
                    PositionedRelation(
                        "punishment_trigger",
                        (left, right),
                        canonical_pair,
                        None,
                        "BRANCH-PUNISHMENT-PAIR-WZ-001",
                        basis=(f"full_group:{''.join(punishment_group)}", "two_branch_trigger"),
                        variant="wenzhen_compatible_v1",
                    )
                )
    return hits


def _aggregate_candidates(
    nodes: Sequence[PositionedPillar],
    rels: dict[str, Any],
    rule_profile: RuleProfile,
) -> list[PositionedRelation]:
    if rule_profile != "wenzhen_compatible_v1":
        return []
    hits: list[PositionedRelation] = []
    branch_to_nodes: dict[str, list[PositionedPillar]] = {}
    stem_to_nodes: dict[str, list[PositionedPillar]] = {}
    for node in nodes:
        branch_to_nodes.setdefault(node.pillar.branch.char, []).append(node)
        stem_to_nodes.setdefault(node.pillar.stem.char, []).append(node)

    if set(branch_to_nodes) >= _FOUR_TOMBS:
        participants = tuple(branch_to_nodes[branch][0] for branch in ("辰", "戌", "丑", "未"))
        hits.append(
            PositionedRelation(
                "four_tombs_earth_structure",
                participants,
                tuple(item.pillar.branch.char for item in participants),
                "earth",
                "BRANCH-FOUR-TOMBS-EARTH-WZ-001",
                basis=("辰戌丑未齐全", "structure_candidate_not_transformation"),
                variant="wenzhen_compatible_v1",
            )
        )

    combination_pairs = [
        tuple(str(value) for value in item.get("pair", []))
        for item in _dict_items(rels.get("stem_five_combinations"))
        if isinstance(item.get("pair"), list) and len(item.get("pair", [])) == 2
    ]
    counts = Counter(node.pillar.stem.char for node in nodes)
    for left_stem, right_stem in combination_pairs:
        if left_stem not in stem_to_nodes or right_stem not in stem_to_nodes:
            continue
        if counts[left_stem] < 2 and counts[right_stem] < 2:
            continue
        participants = tuple([*stem_to_nodes[left_stem], *stem_to_nodes[right_stem]])
        repeated = left_stem if counts[left_stem] >= 2 else right_stem
        hits.append(
            PositionedRelation(
                "competing_combination",
                participants,
                tuple(item.pillar.stem.char for item in participants),
                None,
                "STEM-COMPETING-COMBINATION-WZ-001",
                basis=(f"five_combination:{left_stem}{right_stem}", f"repeated_stem:{repeated}"),
                variant="wenzhen_compatible_v1",
            )
        )
    return hits


def _deduplicate_positioned(hits: list[PositionedRelation]) -> list[PositionedRelation]:
    result: list[PositionedRelation] = []
    seen: set[
        tuple[str, tuple[str, ...], tuple[str, ...], str | None, str | None, tuple[str, ...]]
    ] = set()
    for hit in hits:
        key = (
            hit.type,
            tuple(item.position for item in hit.participants),
            hit.symbols,
            hit.element,
            hit.direction,
            hit.basis,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(hit)
    return result


def evaluate_positioned_relations(
    nodes: Sequence[PositionedPillar],
    *,
    rule_profile: RuleProfile = DEFAULT_RULE_PROFILE,
) -> list[PositionedRelation]:
    """Evaluate pair, pillar-internal and aggregate relations with positions."""
    if len({node.position for node in nodes}) != len(nodes):
        raise ValueError("position identifiers must be unique")
    rels = _relations()
    hits: list[PositionedRelation] = []
    for node in nodes:
        hits.extend(_internal_pillar_relations(node, rule_profile))
    for left, right in combinations(nodes, 2):
        hits.extend(_pair_relations(left, right, rels, rule_profile))
    hits.extend(_full_group_relations(nodes, rels))
    hits.extend(_half_arch_and_punishment_candidates(nodes, rels, rule_profile))
    hits.extend(_aggregate_candidates(nodes, rels, rule_profile))
    return _deduplicate_positioned(hits)


def evaluate_relations(
    pillars: FourPillars,
    *,
    rule_profile: RuleProfile = DEFAULT_RULE_PROFILE,
) -> list[BranchRelation]:
    """Emit natal relations while retaining duplicate-pillar positions."""
    nodes = [
        PositionedPillar(position, pillar)
        for position, pillar in zip(("year", "month", "day", "hour"), pillars.as_list(), strict=True)
    ]
    return [
        BranchRelation(
            type=relation.type,
            branches=relation.symbols,
            element=relation.element,
            rule_id=relation.rule_id,
            positions=tuple(item.position for item in relation.participants),
            direction=relation.direction,
            basis=relation.basis,
            variant=relation.variant,
        )
        for relation in evaluate_positioned_relations(nodes, rule_profile=rule_profile)
    ]
