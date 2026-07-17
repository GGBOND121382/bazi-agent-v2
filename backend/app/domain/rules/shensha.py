"""Versioned, source-traceable 神煞 calculation.

The rule table is intentionally data driven. Classical and modern schools
sometimes use different anchors, so every hit records the exact rule id,
anchor and source locator. 神煞 are deterministic auxiliary markers; they do
not replace 月令、旺衰、格局、用神、十神 or 干支作用.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from ..pillars import EARTHLY_BRANCHES, HEAVENLY_STEMS, FourPillars

CORE_TABLES = Path(__file__).resolve().parents[4] / "contracts" / "core_tables"
SHENSHA_FILE = CORE_TABLES / "shensha_classics_v2.json"
_POSITION_ORDER = ("year", "month", "day", "hour")
_BRANCH_GROUPS = ("申子辰", "寅午戌", "巳酉丑", "亥卯未")
_SEASON_GROUPS = ("寅卯辰", "巳午未", "申酉戌", "亥子丑")


@dataclass(frozen=True, slots=True)
class ShenShaHit:
    name: str
    rule_id: str
    reference: str
    anchor: str
    target: str
    target_position: str
    source_title: str
    source_locator: str
    rule_version: str


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    payload: object = json.loads(SHENSHA_FILE.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shensha rule catalog root must be an object")
    catalog = cast(dict[str, Any], payload)
    rules: list[object] = []
    rule_files = catalog.get("rule_files", [])
    if isinstance(rule_files, list):
        for filename in rule_files:
            part_path = CORE_TABLES / str(filename)
            part: object = json.loads(part_path.read_text(encoding="utf-8"))
            if not isinstance(part, dict):
                raise ValueError(f"shensha rule file root must be an object: {filename}")
            raw_rules = part.get("rules", [])
            if isinstance(raw_rules, list):
                rules.extend(raw_rules)
    catalog["rules"] = rules
    return catalog


def _group_of(value: str, groups: tuple[str, ...]) -> str | None:
    return next((group for group in groups if value in group), None)


def _targets(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        return tuple(str(item) for item in raw)
    return ()


def _xunkong(ganzhi: str) -> tuple[str, str]:
    stem_index = HEAVENLY_STEMS.index(ganzhi[0])
    branch_index = EARTHLY_BRANCHES.index(ganzhi[1])
    cycle_index = next(
        index
        for index in range(60)
        if index % 10 == stem_index and index % 12 == branch_index
    )
    xun_start = (cycle_index // 10) * 10
    return (
        EARTHLY_BRANCHES[(xun_start + 10) % 12],
        EARTHLY_BRANCHES[(xun_start + 11) % 12],
    )


def _anchor_values(reference: str, pillars: FourPillars) -> tuple[tuple[str, str], ...]:
    if reference == "day_stem":
        return (("day_stem", pillars.day.stem.char),)
    if reference == "year_stem":
        return (("year_stem", pillars.year.stem.char),)
    if reference == "day_or_year_stem":
        return (
            ("day_stem", pillars.day.stem.char),
            ("year_stem", pillars.year.stem.char),
        )
    if reference == "year_branch":
        return (("year_branch", pillars.year.branch.char),)
    if reference == "year_pillar":
        return (("year_pillar", pillars.year.ganzhi),)
    if reference == "day_branch":
        return (("day_branch", pillars.day.branch.char),)
    if reference == "day_or_year_branch_group":
        values: list[tuple[str, str]] = []
        for label, branch in (
            ("day_branch_group", pillars.day.branch.char),
            ("year_branch_group", pillars.year.branch.char),
        ):
            group = _group_of(branch, _BRANCH_GROUPS)
            if group:
                values.append((label, group))
        return tuple(values)
    if reference == "month_branch":
        return (("month_branch", pillars.month.branch.char),)
    if reference == "month_branch_group":
        group = _group_of(pillars.month.branch.char, _BRANCH_GROUPS)
        return (("month_branch_group", group),) if group else ()
    if reference == "day_pillar":
        return (("day_pillar", pillars.day.ganzhi),)
    if reference == "seasonal_day_pillar":
        group = _group_of(pillars.month.branch.char, _SEASON_GROUPS)
        return (("season", group),) if group else ()
    return ()


def _matches(target_kind: str, token: str, ganzhi: str) -> bool:
    if target_kind == "branch":
        return ganzhi[1] == token
    if target_kind == "stem":
        return ganzhi[0] == token
    if target_kind == "stem_or_branch":
        return token in ganzhi
    if target_kind == "pillar":
        return ganzhi == token
    return False


def _source(rule: dict[str, Any]) -> tuple[str, str]:
    raw = rule.get("source")
    if not isinstance(raw, dict):
        return ("未标注来源", "")
    return (str(raw.get("title", "未标注来源")), str(raw.get("locator", "")))


def _add_hit(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    reference: str,
    anchor: str,
    target: str,
    target_position: str,
    version: str,
) -> None:
    source_title, source_locator = _source(rule)
    key = (str(rule["rule_id"]), target_position)
    previous = bucket.get(key)
    merged_anchor = anchor
    merged_reference = reference
    if previous is not None:
        merged_anchor = " / ".join(dict.fromkeys((*previous.anchor.split(" / "), anchor)))
        merged_reference = " / ".join(
            dict.fromkeys((*previous.reference.split(" / "), reference))
        )
    bucket[key] = ShenShaHit(
        name=str(rule["name"]),
        rule_id=str(rule["rule_id"]),
        reference=merged_reference,
        anchor=merged_anchor,
        target=target,
        target_position=target_position,
        source_title=source_title,
        source_locator=source_locator,
        rule_version=version,
    )


def _evaluate_mapped_rule(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    pillars: FourPillars,
    version: str,
) -> None:
    reference = str(rule.get("reference", ""))
    target_kind = str(rule.get("target_kind", "branch"))
    mapping = rule.get("mapping", {})
    if not isinstance(mapping, dict):
        return
    ganzhi_by_position = {
        position: pillar.ganzhi
        for position, pillar in zip(_POSITION_ORDER, pillars.as_list(), strict=True)
    }
    configured_positions = rule.get("target_positions")
    allowed_positions = (
        {str(item) for item in configured_positions}
        if isinstance(configured_positions, list)
        else set(_POSITION_ORDER)
    )
    for anchor_label, anchor_value in _anchor_values(reference, pillars):
        for token in _targets(mapping.get(anchor_value)):
            for position, ganzhi in ganzhi_by_position.items():
                if position not in allowed_positions:
                    continue
                if _matches(target_kind, token, ganzhi):
                    _add_hit(
                        bucket,
                        rule=rule,
                        reference=anchor_label,
                        anchor=anchor_value,
                        target=token,
                        target_position=position,
                        version=version,
                    )


def _evaluate_special_rule(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    pillars: FourPillars,
    version: str,
) -> None:
    reference = str(rule.get("reference", ""))
    values = {str(item) for item in cast(list[object], rule.get("values", []))}
    if reference == "day_pillar":
        if pillars.day.ganzhi in values:
            _add_hit(
                bucket,
                rule=rule,
                reference="day_pillar",
                anchor=pillars.day.ganzhi,
                target=pillars.day.ganzhi,
                target_position="day",
                version=version,
            )
        return
    if reference == "year_or_day_xunkong":
        targets = set(_xunkong(pillars.year.ganzhi)) | set(_xunkong(pillars.day.ganzhi))
        for position, pillar in zip(_POSITION_ORDER, pillars.as_list(), strict=True):
            if pillar.branch.char in targets:
                _add_hit(
                    bucket,
                    rule=rule,
                    reference="year/day_xunkong",
                    anchor=f"{pillars.year.ganzhi}/{pillars.day.ganzhi}",
                    target=pillar.branch.char,
                    target_position=position,
                    version=version,
                )
        return
    if reference == "consecutive_stems":
        stems = "".join(pillar.stem.char for pillar in pillars.as_list())
        for start in (0, 1):
            sequence = stems[start : start + 3]
            if sequence not in values:
                continue
            for position in _POSITION_ORDER[start : start + 3]:
                _add_hit(
                    bucket,
                    rule=rule,
                    reference="consecutive_stems",
                    anchor=sequence,
                    target=sequence,
                    target_position=position,
                    version=version,
                )


def evaluate_shensha(pillars: FourPillars) -> list[ShenShaHit]:
    catalog = _catalog()
    version = str(catalog.get("version", "unknown"))
    raw_rules = catalog.get("rules", [])
    if not isinstance(raw_rules, list):
        return []
    bucket: dict[tuple[str, str], ShenShaHit] = {}
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        rule = cast(dict[str, Any], raw_rule)
        reference = str(rule.get("reference", ""))
        if reference in {"year_or_day_xunkong", "consecutive_stems", "day_pillar"}:
            _evaluate_special_rule(bucket, rule=rule, pillars=pillars, version=version)
        else:
            _evaluate_mapped_rule(bucket, rule=rule, pillars=pillars, version=version)
    position_rank = {position: index for index, position in enumerate(_POSITION_ORDER)}
    return sorted(
        bucket.values(),
        key=lambda hit: (position_rank.get(hit.target_position, 99), hit.rule_id),
    )
