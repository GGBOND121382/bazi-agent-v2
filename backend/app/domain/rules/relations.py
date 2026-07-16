"""Branch relations: 六合, 三合, 六冲, 六害, 相刑, 自刑.

Pure functions; no I/O. Uses `contracts/core_tables/stem_branch_relations.json`.

Combination is a *relation candidate*; transformation is a separate decision
governed by the CalculationProfile (`combination_means_transformation` flag).
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


@lru_cache(maxsize=1)
def _relations() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(REL_FILE.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class BranchRelation:
    type: str  # 'six_combination' | 'three_combination' | 'clash' | 'harm' | 'break' | 'punishment'
    branches: tuple[str, ...]
    element: str | None  # for combinations
    rule_id: str


def _branch_set(*branches: str) -> tuple[str, ...]:
    return tuple(sorted(set(branches)))


def _pair_in(branches: Collection[str], pair: Iterable[str]) -> bool:
    """True if all of `pair` appear in `branches`."""
    return all(b in branches for b in pair)


def evaluate_relations(pillars: FourPillars) -> list[BranchRelation]:
    """Walk the four 柱 and emit all relations involving at least two branches."""
    branches: list[str] = [str(p.branch) for p in pillars.as_list()]
    seen_branches: set[str] = set(branches)
    rels = _relations()
    hits: list[BranchRelation] = []

    # Six combinations (六合) — element candidate
    for combo in rels.get("branch_six_combinations", []):
        pair = combo["pair"]
        if _pair_in(seen_branches, pair):
            hits.append(
                BranchRelation(
                    type="six_combination",
                    branches=_branch_set(*pair),
                    element=combo.get("transformation_candidate"),
                    rule_id="BRANCH-SIX-COMBINATION-001",
                )
            )

    # Three combinations (三合) — element candidate
    for combo in rels.get("three_combinations", []):
        tri = combo["branches"]
        if all(b in seen_branches for b in tri):
            hits.append(
                BranchRelation(
                    type="three_combination",
                    branches=_branch_set(*tri),
                    element=combo.get("element"),
                    rule_id="BRANCH-THREE-COMBINATION-001",
                )
            )

    # Three meetings (三会) — element candidate
    for combo in rels.get("three_meetings", []):
        tri = combo["branches"]
        if all(b in seen_branches for b in tri):
            hits.append(
                BranchRelation(
                    type="three_meeting",
                    branches=_branch_set(*tri),
                    element=combo.get("element"),
                    rule_id="BRANCH-THREE-MEETING-001",
                )
            )

    # Clashes (六冲)
    for pair in rels.get("branch_clashes", []):
        if _pair_in(seen_branches, pair):
            hits.append(
                BranchRelation(
                    type="clash",
                    branches=_branch_set(*pair),
                    element=None,
                    rule_id="BRANCH-CLASH-001",
                )
            )

    # Harms (六害)
    for pair in rels.get("branch_harms", []):
        if _pair_in(seen_branches, pair):
            hits.append(
                BranchRelation(
                    type="harm",
                    branches=_branch_set(*pair),
                    element=None,
                    rule_id="BRANCH-HARM-001",
                )
            )

    # Branch breaks (相穿) — optional, controlled by profile.enable_branch_break
    for pair in rels.get("branch_breaks", {}).get("pairs", []):
        if _pair_in(seen_branches, pair):
            hits.append(
                BranchRelation(
                    type="break",
                    branches=_branch_set(*pair),
                    element=None,
                    rule_id="BRANCH-BREAK-001",
                )
            )

    # Punishments (相刑) — three_punishment, mutual_punishment, self_punishment
    for p in rels.get("punishments", []):
        if p["type"] == "three_punishment":
            tri = p["branches"]
            if all(b in seen_branches for b in tri):
                hits.append(
                    BranchRelation(
                        type="punishment",
                        branches=_branch_set(*tri),
                        element=None,
                        rule_id="BRANCH-PUNISHMENT-3-001",
                    )
                )
        elif p["type"] == "mutual_punishment":
            pair = p["branches"]
            if _pair_in(seen_branches, pair):
                hits.append(
                    BranchRelation(
                        type="punishment",
                        branches=_branch_set(*pair),
                        element=None,
                        rule_id="BRANCH-PUNISHMENT-M-001",
                    )
                )
        elif p["type"] == "self_punishment":
            branch = p["branches"][0]
            count = branches.count(branch)
            if count >= 2:
                hits.append(
                    BranchRelation(
                        type="punishment",
                        branches=(branch, branch),
                        element=None,
                        rule_id="BRANCH-PUNISHMENT-S-001",
                    )
                )

    return hits
