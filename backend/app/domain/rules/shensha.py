"""神煞 seed evaluation.

Implements the core 神煞 set drawn from `contracts/core_tables/shensha_core_v1_seed.json`:
- 天乙贵人 (tianyi_guiren) — anchor: day_stem
- 文昌贵人 (wenchang_guiren) — anchor: day_stem
- 桃花 (taohua) — anchor: branch group (申子辰 / 寅午戌 / 巳酉丑 / 亥卯未) → 桃花支
- 驿马 (yima) — same group → 驿马支
- 华盖 (huagai) — same group → 华盖支

Each 神煞 is a pure function: given pillars, return a list of hits where the
target branch actually appears in the four 柱.

NOTE: 神煞 are 'auxiliary_only' per calculation profile; the analysis layer
treats them as supplementary, not authoritative.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from ..pillars import FourPillars

CORE_TABLES = Path(__file__).resolve().parents[4] / "contracts" / "core_tables"
SHENSHA_FILE = CORE_TABLES / "shensha_core_v1_seed.json"


# Branch groups used by 三合 起局 for taohua/yima/huagai.
_BRANCH_GROUPS = ("申子辰", "寅午戌", "巳酉丑", "亥卯未")


@dataclass(frozen=True, slots=True)
class ShenShaHit:
    name: str  # e.g. '天乙贵人'
    rule_id: str
    reference: str  # 'day_stem' | 'year_branch' | 'day_branch'
    anchor: str  # the anchor char (e.g. '甲', '申', or the group '申子辰')
    target: str  # the branch where the 神煞 lands


@lru_cache(maxsize=1)
def _seed() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(SHENSHA_FILE.read_text(encoding="utf-8")))


def _branch_group_of(branch: str) -> str | None:
    for g in _BRANCH_GROUPS:
        if branch in g:
            return g
    return None


def evaluate_shensha(pillars: FourPillars) -> list[ShenShaHit]:
    """Walk all core 神煞 rules and emit hits for any target branch visible in
    the four 柱."""
    seed = _seed()
    rules = seed.get("rules", [])
    branches = [str(p.branch) for p in pillars.as_list()]
    branch_set = set(branches)
    hits: list[ShenShaHit] = []

    day_stem = str(pillars.day_master)
    year_branch = str(pillars.year.branch)
    day_branch = str(pillars.day.branch)

    for rule in rules:
        name = rule["name"]
        rule_id = rule["rule_id"]
        ref = rule.get("reference", "day_stem")
        mapping = rule.get("mapping", {})

        if ref == "day_stem":
            # mapping: stem char → list of branches where the 神煞 lands
            for b in mapping.get(day_stem, []):
                if b in branch_set:
                    hits.append(
                        ShenShaHit(
                            name=name,
                            rule_id=rule_id,
                            reference="day_stem",
                            anchor=day_stem,
                            target=b,
                        )
                    )
        elif ref == "day_or_year_branch_group":
            # mapping: group → single target branch
            for branch in (year_branch, day_branch):
                grp = _branch_group_of(branch)
                if grp and grp in mapping:
                    target = mapping[grp]
                    if target in branch_set:
                        hits.append(
                            ShenShaHit(
                                name=name,
                                rule_id=rule_id,
                                reference=f"branch_group({branch})",
                                anchor=grp,
                                target=target,
                            )
                        )
        else:
            # Unknown reference; skip silently. Future 神煞 types (天德/月德 etc.)
            # would extend this dispatch.
            continue

    return hits
