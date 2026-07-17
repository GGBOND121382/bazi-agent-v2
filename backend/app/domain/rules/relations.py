"""Deterministic 天干地支 relations.

Covers 天干五合/相冲 and 地支六合、三合、半合、三会、半会、六冲、
六害、相破、相刑、自刑. A combination is only a relation candidate;
whether it transforms is a separate profile/interpretation decision.
"""
from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from ..pillars import FourPillars

CORE_TABLES = Path(__file__).resolve().parents[4] / "contracts" / "core_tables"
REL_FILE = CORE_TABLES / "stem_branch_relations.json"
_STEM_CLASHES = (("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"))


@lru_cache(maxsize=1)
def _relations() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(REL_FILE.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class BranchRelation:
    """A visible-stem or visible-branch relation.

    The historical class name is retained for API compatibility. `branches`
    contains the participating characters, including stems for stem relations.
    """

    type: str
    branches: tuple[str, ...]
    element: str | None
    rule_id: str


def _ordered_unique(*values: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _pair_in(values: Collection[str], pair: Iterable[str]) -> bool:
    return all(value in values for value in pair)


def _dict_items(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, Any], item) for item in raw if isinstance(item, dict)]


def _pair_items(raw: object) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        return []
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            continue
        pairs.append((str(item[0]), str(item[1])))
    return pairs


def _stem_relations(rels: dict[str, Any], seen_stems: set[str]) -> list[BranchRelation]:
    hits: list[BranchRelation] = []
    for combo in _dict_items(rels.get("stem_five_combinations")):
        raw_pair = combo.get("pair")
        if not isinstance(raw_pair, list) or len(raw_pair) != 2:
            continue
        combo_pair = (str(raw_pair[0]), str(raw_pair[1]))
        if _pair_in(seen_stems, combo_pair):
            hits.append(
                BranchRelation(
                    type="stem_combination",
                    branches=combo_pair,
                    element=str(combo.get("transformation_candidate") or "") or None,
                    rule_id="STEM-FIVE-COMBINATION-001",
                )
            )
    for clash_pair in _STEM_CLASHES:
        if _pair_in(seen_stems, clash_pair):
            hits.append(
                BranchRelation(
                    type="stem_clash",
                    branches=clash_pair,
                    element=None,
                    rule_id="STEM-CLASH-001",
                )
            )
    return hits


def _six_combination_relations(
    rels: dict[str, Any], seen_branches: set[str]
) -> list[BranchRelation]:
    hits: list[BranchRelation] = []
    for combo in _dict_items(rels.get("branch_six_combinations")):
        raw_pair = combo.get("pair")
        if not isinstance(raw_pair, list) or len(raw_pair) != 2:
            continue
        combo_pair = (str(raw_pair[0]), str(raw_pair[1]))
        if _pair_in(seen_branches, combo_pair):
            hits.append(
                BranchRelation(
                    type="six_combination",
                    branches=combo_pair,
                    element=str(combo.get("transformation_candidate") or "") or None,
                    rule_id="BRANCH-SIX-COMBINATION-001",
                )
            )
    return hits


def _group_relations(
    raw_groups: object,
    seen_branches: set[str],
    *,
    full_type: str,
    half_type: str,
    full_rule_id: str,
    half_rule_id: str,
) -> list[BranchRelation]:
    hits: list[BranchRelation] = []
    for combo in _dict_items(raw_groups):
        raw_group = combo.get("branches")
        if not isinstance(raw_group, list) or len(raw_group) != 3:
            continue
        group = (str(raw_group[0]), str(raw_group[1]), str(raw_group[2]))
        element = str(combo.get("element") or "") or None
        if _pair_in(seen_branches, group):
            hits.append(BranchRelation(full_type, group, element, full_rule_id))
            continue
        for half_pair in ((group[0], group[1]), (group[1], group[2])):
            if _pair_in(seen_branches, half_pair):
                hits.append(BranchRelation(half_type, half_pair, element, half_rule_id))
    return hits


def _simple_pair_relations(
    raw_pairs: object,
    seen_branches: set[str],
    *,
    relation_type: str,
    rule_id: str,
) -> list[BranchRelation]:
    return [
        BranchRelation(relation_type, relation_pair, None, rule_id)
        for relation_pair in _pair_items(raw_pairs)
        if _pair_in(seen_branches, relation_pair)
    ]


def _punishment_relations(
    raw_punishments: object,
    seen_branches: set[str],
    branches: list[str],
) -> list[BranchRelation]:
    hits: list[BranchRelation] = []
    for punishment in _dict_items(raw_punishments):
        raw_values = punishment.get("branches")
        if not isinstance(raw_values, list):
            continue
        values = tuple(str(value) for value in raw_values)
        kind = str(punishment.get("type", ""))
        if kind == "three_punishment" and len(values) == 3 and _pair_in(seen_branches, values):
            hits.append(
                BranchRelation("punishment", values, None, "BRANCH-PUNISHMENT-3-001")
            )
        elif kind == "mutual_punishment" and len(values) == 2 and _pair_in(
            seen_branches, values
        ):
            hits.append(
                BranchRelation("punishment", values, None, "BRANCH-PUNISHMENT-M-001")
            )
        elif kind == "self_punishment" and len(values) == 1 and branches.count(values[0]) >= 2:
            hits.append(
                BranchRelation(
                    "punishment",
                    (values[0], values[0]),
                    None,
                    "BRANCH-PUNISHMENT-S-001",
                )
            )
    return hits


def _deduplicate(hits: list[BranchRelation]) -> list[BranchRelation]:
    result: list[BranchRelation] = []
    seen: set[tuple[str, tuple[str, ...], str | None]] = set()
    for hit in hits:
        key = (hit.type, hit.branches, hit.element)
        if key in seen:
            continue
        seen.add(key)
        result.append(hit)
    return result


def evaluate_relations(pillars: FourPillars) -> list[BranchRelation]:
    """Emit all configured visible-stem and visible-branch relations."""
    stems = [pillar.stem.char for pillar in pillars.as_list()]
    branches = [pillar.branch.char for pillar in pillars.as_list()]
    seen_stems = set(stems)
    seen_branches = set(branches)
    rels = _relations()

    hits = _stem_relations(rels, seen_stems)
    hits.extend(_six_combination_relations(rels, seen_branches))
    hits.extend(
        _group_relations(
            rels.get("three_combinations"),
            seen_branches,
            full_type="three_combination",
            half_type="half_combination",
            full_rule_id="BRANCH-THREE-COMBINATION-001",
            half_rule_id="BRANCH-HALF-COMBINATION-001",
        )
    )
    hits.extend(
        _group_relations(
            rels.get("three_meetings"),
            seen_branches,
            full_type="three_meeting",
            half_type="half_meeting",
            full_rule_id="BRANCH-THREE-MEETING-001",
            half_rule_id="BRANCH-HALF-MEETING-001",
        )
    )
    hits.extend(
        _simple_pair_relations(
            rels.get("branch_clashes"),
            seen_branches,
            relation_type="clash",
            rule_id="BRANCH-CLASH-001",
        )
    )
    hits.extend(
        _simple_pair_relations(
            rels.get("branch_harms"),
            seen_branches,
            relation_type="harm",
            rule_id="BRANCH-HARM-001",
        )
    )
    raw_breaks = rels.get("branch_breaks")
    if isinstance(raw_breaks, dict):
        hits.extend(
            _simple_pair_relations(
                raw_breaks.get("pairs"),
                seen_branches,
                relation_type="break",
                rule_id="BRANCH-BREAK-001",
            )
        )
    hits.extend(_punishment_relations(rels.get("punishments"), seen_branches, branches))
    return _deduplicate(hits)
