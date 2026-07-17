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
from itertools import combinations
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
    """A relation among visible stems or branches.

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


def _full_group_present(values: Collection[str], group: list[object]) -> bool:
    return all(str(value) in values for value in group)


def evaluate_relations(pillars: FourPillars) -> list[BranchRelation]:
    """Emit all configured visible-stem and visible-branch relations."""
    stems = [pillar.stem.char for pillar in pillars.as_list()]
    branches = [pillar.branch.char for pillar in pillars.as_list()]
    seen_stems = set(stems)
    seen_branches = set(branches)
    rels = _relations()
    hits: list[BranchRelation] = []

    # 天干五合. 化气 is only a candidate element, never asserted as completed.
    for combo in rels.get("stem_five_combinations", []):
        if not isinstance(combo, dict):
            continue
        pair = [str(value) for value in combo.get("pair", [])]
        if len(pair) == 2 and _pair_in(seen_stems, pair):
            hits.append(
                BranchRelation(
                    type="stem_combination",
                    branches=_ordered_unique(*pair),
                    element=str(combo.get("transformation_candidate") or "") or None,
                    rule_id="STEM-FIVE-COMBINATION-001",
                )
            )

    # Common 子平 visible-stem clash pairs. 戊己不列入天干冲。
    for pair in _STEM_CLASHES:
        if _pair_in(seen_stems, pair):
            hits.append(
                BranchRelation(
                    type="stem_clash",
                    branches=pair,
                    element=None,
                    rule_id="STEM-CLASH-001",
                )
            )

    # 六合.
    for combo in rels.get("branch_six_combinations", []):
        if not isinstance(combo, dict):
            continue
        pair = [str(value) for value in combo.get("pair", [])]
        if len(pair) == 2 and _pair_in(seen_branches, pair):
            hits.append(
                BranchRelation(
                    type="six_combination",
                    branches=_ordered_unique(*pair),
                    element=str(combo.get("transformation_candidate") or "") or None,
                    rule_id="BRANCH-SIX-COMBINATION-001",
                )
            )

    # 三合 and the two 旺支-linked 半合 pairs. Do not duplicate 半合 when三合全。
    for combo in rels.get("three_combinations", []):
        if not isinstance(combo, dict):
            continue
        tri = [str(value) for value in combo.get("branches", [])]
        if len(tri) != 3:
            continue
        full = _full_group_present(seen_branches, cast(list[object], tri))
        element = str(combo.get("element") or "") or None
        if full:
            hits.append(
                BranchRelation(
                    type="three_combination",
                    branches=_ordered_unique(*tri),
                    element=element,
                    rule_id="BRANCH-THREE-COMBINATION-001",
                )
            )
        else:
            for pair in ((tri[0], tri[1]), (tri[1], tri[2])):
                if _pair_in(seen_branches, pair):
                    hits.append(
                        BranchRelation(
                            type="half_combination",
                            branches=pair,
                            element=element,
                            rule_id="BRANCH-HALF-COMBINATION-001",
                        )
                    )

    # 三会 and adjacent 半会 pairs. Do not duplicate 半会 when三会全。
    for combo in rels.get("three_meetings", []):
        if not isinstance(combo, dict):
            continue
        tri = [str(value) for value in combo.get("branches", [])]
        if len(tri) != 3:
            continue
        full = _full_group_present(seen_branches, cast(list[object], tri))
        element = str(combo.get("element") or "") or None
        if full:
            hits.append(
                BranchRelation(
                    type="three_meeting",
                    branches=_ordered_unique(*tri),
                    element=element,
                    rule_id="BRANCH-THREE-MEETING-001",
                )
            )
        else:
            for pair in ((tri[0], tri[1]), (tri[1], tri[2])):
                if _pair_in(seen_branches, pair):
                    hits.append(
                        BranchRelation(
                            type="half_meeting",
                            branches=pair,
                            element=element,
                            rule_id="BRANCH-HALF-MEETING-001",
                        )
                    )

    for pair_raw in rels.get("branch_clashes", []):
        pair = tuple(str(value) for value in cast(list[object], pair_raw))
        if len(pair) == 2 and _pair_in(seen_branches, pair):
            hits.append(BranchRelation("clash", pair, None, "BRANCH-CLASH-001"))

    for pair_raw in rels.get("branch_harms", []):
        pair = tuple(str(value) for value in cast(list[object], pair_raw))
        if len(pair) == 2 and _pair_in(seen_branches, pair):
            hits.append(BranchRelation("harm", pair, None, "BRANCH-HARM-001"))

    breaks = rels.get("branch_breaks", {})
    if isinstance(breaks, dict):
        for pair_raw in breaks.get("pairs", []):
            pair = tuple(str(value) for value in cast(list[object], pair_raw))
            if len(pair) == 2 and _pair_in(seen_branches, pair):
                hits.append(BranchRelation("break", pair, None, "BRANCH-BREAK-001"))

    for punishment in rels.get("punishments", []):
        if not isinstance(punishment, dict):
            continue
        kind = str(punishment.get("type", ""))
        values = tuple(str(value) for value in punishment.get("branches", []))
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

    # Stable de-duplication protects against overlapping configurable tables.
    deduplicated: list[BranchRelation] = []
    seen: set[tuple[str, tuple[str, ...], str | None]] = set()
    for hit in hits:
        key = (hit.type, hit.branches, hit.element)
        if key not in seen:
            seen.add(key)
            deduplicated.append(hit)
    return deduplicated
