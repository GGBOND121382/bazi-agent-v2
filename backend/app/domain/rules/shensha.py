"""Versioned, source-traceable 神煞 calculation.

The engine separates natal-position matching from external temporal matching.
That distinction is important: year/day-branch markers such as 将星 are not
reported on the anchor pillar itself in the APP-compatible convention, while
the same branch may legitimately trigger the marker in 大运、流年、流月或流日.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

from ..pillars import EARTHLY_BRANCHES, HEAVENLY_STEMS, FourPillars, Pillar

CORE_TABLES = Path(__file__).resolve().parents[4] / "contracts" / "core_tables"
SHENSHA_FILE = CORE_TABLES / "shensha_classics_v2.json"
_POSITION_ORDER = ("year", "month", "day", "hour")
_BRANCH_GROUPS = ("申子辰", "寅午戌", "巳酉丑", "亥卯未")
_SEASON_GROUPS = ("寅卯辰", "巳午未", "申酉戌", "亥子丑")
TemporalScope = Literal["dayun", "liunian", "liuyue", "liuri", "liushi"]
ShenshaRuleProfile = Literal["ziping_conservative_v1", "wenzhen_compatible_v1"]
DEFAULT_SHENSHA_RULE_PROFILE: ShenshaRuleProfile = "wenzhen_compatible_v1"


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
    anchor_position: str | None = None
    variant: str = "classical_or_common"


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


def _nayin_element(pillar: Pillar) -> str:
    nayin = pillar.nayin
    return nayin[-1] if nayin and nayin[-1] in "木火土金水" else ""


def _anchor_values(
    reference: str,
    pillars: FourPillars,
    *,
    season_branch: str | None = None,
) -> tuple[tuple[str, str, str | None], ...]:
    direct: dict[str, tuple[tuple[str, str, str | None], ...]] = {
        "day_stem": (("day_stem", pillars.day.stem.char, "day"),),
        "year_stem": (("year_stem", pillars.year.stem.char, "year"),),
        "day_or_year_stem": (
            ("day_stem", pillars.day.stem.char, "day"),
            ("year_stem", pillars.year.stem.char, "year"),
        ),
        "year_branch": (("year_branch", pillars.year.branch.char, "year"),),
        "year_pillar": (("year_pillar", pillars.year.ganzhi, "year"),),
        "day_branch": (("day_branch", pillars.day.branch.char, "day"),),
        "month_branch": (("month_branch", pillars.month.branch.char, "month"),),
        "day_pillar": (("day_pillar", pillars.day.ganzhi, "day"),),
        "year_nayin_element": (("year_nayin_element", _nayin_element(pillars.year), "year"),),
    }
    values = direct.get(reference, ())
    if reference == "day_or_year_branch_group":
        grouped: list[tuple[str, str, str | None]] = []
        for label, branch, position in (
            ("day_branch_group", pillars.day.branch.char, "day"),
            ("year_branch_group", pillars.year.branch.char, "year"),
        ):
            group = _group_of(branch, _BRANCH_GROUPS)
            if group:
                grouped.append((label, group, position))
        values = tuple(grouped)
    elif reference == "year_branch_group":
        group = _group_of(pillars.year.branch.char, _BRANCH_GROUPS)
        values = (("year_branch_group", group, "year"),) if group else ()
    elif reference == "month_branch_group":
        group = _group_of(pillars.month.branch.char, _BRANCH_GROUPS)
        values = (("month_branch_group", group, "month"),) if group else ()
    elif reference == "seasonal_day_pillar":
        branch = season_branch or pillars.month.branch.char
        group = _group_of(branch, _SEASON_GROUPS)
        values = (("season", group, "month"),) if group else ()
    return values


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
    anchor_position: str | None = None,
) -> None:
    source_title, source_locator = _source(rule)
    key = (str(rule["rule_id"]), target_position)
    previous = bucket.get(key)
    merged_anchor = anchor
    merged_reference = reference
    merged_anchor_position = anchor_position
    if previous is not None:
        merged_anchor = " / ".join(dict.fromkeys((*previous.anchor.split(" / "), anchor)))
        merged_reference = " / ".join(
            dict.fromkeys((*previous.reference.split(" / "), reference))
        )
        positions = tuple(
            item
            for item in (previous.anchor_position, anchor_position)
            if item
        )
        merged_anchor_position = " / ".join(dict.fromkeys(positions)) or None
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
        anchor_position=merged_anchor_position,
        variant=str(rule.get("variant", "classical_or_common")),
    )


def _exclude_natal_self(rule: dict[str, Any], anchor_position: str | None, position: str) -> bool:
    return bool(rule.get("exclude_anchor_position")) and anchor_position == position


def _evaluate_mapped_natal(
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
    for anchor_label, anchor_value, anchor_position in _anchor_values(reference, pillars):
        for token in _targets(mapping.get(anchor_value)):
            for position, ganzhi in ganzhi_by_position.items():
                if position not in allowed_positions:
                    continue
                if _exclude_natal_self(rule, anchor_position, position):
                    continue
                if _matches(target_kind, token, ganzhi):
                    _add_hit(
                        bucket,
                        rule=rule,
                        reference=anchor_label,
                        anchor=anchor_value,
                        anchor_position=anchor_position,
                        target=token,
                        target_position=position,
                        version=version,
                    )


def _evaluate_mapped_target(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    natal: FourPillars,
    target: Pillar,
    target_position: str,
    version: str,
    season_branch: str | None,
) -> None:
    reference = str(rule.get("reference", ""))
    target_kind = str(rule.get("target_kind", "branch"))
    mapping = rule.get("mapping", {})
    if not isinstance(mapping, dict):
        return
    scopes = rule.get("temporal_scopes")
    if isinstance(scopes, list) and target_position not in {str(item) for item in scopes}:
        return
    for anchor_label, anchor_value, anchor_position in _anchor_values(
        reference, natal, season_branch=season_branch
    ):
        for token in _targets(mapping.get(anchor_value)):
            if _matches(target_kind, token, target.ganzhi):
                _add_hit(
                    bucket,
                    rule=rule,
                    reference=anchor_label,
                    anchor=anchor_value,
                    anchor_position=anchor_position,
                    target=token,
                    target_position=target_position,
                    version=version,
                )


def _gender_group(pillars: FourPillars, gender: str) -> str | None:
    if gender not in {"male", "female"}:
        return None
    yang_year = pillars.year.stem.yin_yang == "yang"
    return "yang_male_yin_female" if (gender == "male") == yang_year else "yin_male_yang_female"


def _offset_branch(branch: str, steps: int) -> str:
    return EARTHLY_BRANCHES[(EARTHLY_BRANCHES.index(branch) + steps) % 12]


def _special_target_branch(rule: dict[str, Any], pillars: FourPillars, gender: str) -> str | None:
    reference = str(rule.get("reference", ""))
    group = _gender_group(pillars, gender)
    if group is None:
        return None
    if reference == "year_branch_goujiao":
        # Wenzhen-compatible display uses the third branch ahead as the hit.
        # Sex and year-stem polarity only determine the role name; they do not
        # reverse the target branch. The former reversal caused sample mismatches.
        return _offset_branch(pillars.year.branch.char, 3)
    if reference == "year_branch_yuanchen":
        mapping = rule.get("mapping", {})
        if not isinstance(mapping, dict):
            return None
        group_mapping = mapping.get(group, {})
        if not isinstance(group_mapping, dict):
            return None
        value = group_mapping.get(pillars.year.branch.char)
        return str(value) if value else None
    return None


def _evaluate_gender_natal(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    pillars: FourPillars,
    gender: str,
    version: str,
) -> None:
    target = _special_target_branch(rule, pillars, gender)
    if not target:
        return
    for position, pillar in zip(_POSITION_ORDER, pillars.as_list(), strict=True):
        if position == "year":
            continue
        if pillar.branch.char == target:
            _add_hit(
                bucket,
                rule=rule,
                reference=str(rule.get("reference", "")),
                anchor=f"{pillars.year.ganzhi}/{gender}",
                anchor_position="year",
                target=target,
                target_position=position,
                version=version,
            )


def _evaluate_gender_target(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    natal: FourPillars,
    target: Pillar,
    target_position: str,
    gender: str,
    version: str,
) -> None:
    target_branch = _special_target_branch(rule, natal, gender)
    if target_branch and target.branch.char == target_branch:
        _add_hit(
            bucket,
            rule=rule,
            reference=str(rule.get("reference", "")),
            anchor=f"{natal.year.ganzhi}/{gender}",
            anchor_position="year",
            target=target_branch,
            target_position=target_position,
            version=version,
        )


def _evaluate_special_natal(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    pillars: FourPillars,
    version: str,
) -> None:
    reference = str(rule.get("reference", ""))
    values = {str(item) for item in cast(list[object], rule.get("values", []))}
    if reference == "day_or_hour_pillar":
        for position, pillar in (("day", pillars.day), ("hour", pillars.hour)):
            if pillar.ganzhi not in values:
                continue
            _add_hit(
                bucket,
                rule=rule,
                reference="day_or_hour_pillar",
                anchor=pillar.ganzhi,
                anchor_position=position,
                target=pillar.ganzhi,
                target_position=position,
                version=version,
            )
        return
    if reference == "tongzi_season_nayin":
        month_branch = pillars.month.branch.char
        seasonal_targets = (
            {"寅", "子"}
            if month_branch in "寅卯辰申酉戌"
            else {"卯", "未", "辰"}
        )
        nayin_element = _nayin_element(pillars.year)
        nayin_targets = {
            "金": {"午", "卯"},
            "木": {"午", "卯"},
            "水": {"酉", "戌"},
            "火": {"酉", "戌"},
            "土": {"辰", "巳"},
        }.get(nayin_element, set())
        for position, pillar in (("day", pillars.day), ("hour", pillars.hour)):
            reasons: list[str] = []
            if pillar.branch.char in seasonal_targets:
                reasons.append(f"month_branch:{month_branch}")
            if pillar.branch.char in nayin_targets:
                reasons.append(f"year_nayin:{nayin_element}")
            if not reasons:
                continue
            _add_hit(
                bucket,
                rule=rule,
                reference="tongzi_season_nayin",
                anchor=" / ".join(reasons),
                anchor_position="month/year",
                target=pillar.branch.char,
                target_position=position,
                version=version,
            )
        return
    if reference == "day_pillar":
        if pillars.day.ganzhi in values:
            _add_hit(
                bucket,
                rule=rule,
                reference="day_pillar",
                anchor=pillars.day.ganzhi,
                anchor_position="day",
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


def _evaluate_special_target(
    bucket: dict[tuple[str, str], ShenShaHit],
    *,
    rule: dict[str, Any],
    natal: FourPillars,
    target: Pillar,
    target_position: str,
    version: str,
) -> None:
    reference = str(rule.get("reference", ""))
    if reference == "year_or_day_xunkong":
        targets = set(_xunkong(natal.year.ganzhi)) | set(_xunkong(natal.day.ganzhi))
        if target.branch.char in targets:
            _add_hit(
                bucket,
                rule=rule,
                reference="year/day_xunkong",
                anchor=f"{natal.year.ganzhi}/{natal.day.ganzhi}",
                target=target.branch.char,
                target_position=target_position,
                version=version,
            )
        return
    if reference == "day_pillar" and target_position == "liuri":
        values = {str(item) for item in cast(list[object], rule.get("values", []))}
        if target.ganzhi in values:
            _add_hit(
                bucket,
                rule=rule,
                reference="flow_day_pillar",
                anchor=target.ganzhi,
                target=target.ganzhi,
                target_position=target_position,
                version=version,
            )


def _rules() -> tuple[str, list[dict[str, Any]]]:
    catalog = _catalog()
    version = str(catalog.get("version", "unknown"))
    raw_rules = catalog.get("rules", [])
    if not isinstance(raw_rules, list):
        return version, []
    return version, [cast(dict[str, Any], item) for item in raw_rules if isinstance(item, dict)]



def _rule_enabled(rule: dict[str, Any], rule_profile: ShenshaRuleProfile) -> bool:
    """Filter compatibility-only rules when the conservative profile is selected."""
    variant = str(rule.get("variant", "classical_or_common"))
    return rule_profile == "wenzhen_compatible_v1" or variant != "wenzhen_compatible_v1"


def evaluate_shensha(
    pillars: FourPillars,
    *,
    gender: str = "unspecified",
    rule_profile: ShenshaRuleProfile = DEFAULT_SHENSHA_RULE_PROFILE,
) -> list[ShenShaHit]:
    """Evaluate natal shensha using APP-compatible anchor self-exclusion."""
    version, rules = _rules()
    bucket: dict[tuple[str, str], ShenShaHit] = {}
    for rule in rules:
        if not _rule_enabled(rule, rule_profile):
            continue
        reference = str(rule.get("reference", ""))
        if reference in {"year_branch_goujiao", "year_branch_yuanchen"}:
            _evaluate_gender_natal(
                bucket, rule=rule, pillars=pillars, gender=gender, version=version
            )
        elif reference in {
            "year_or_day_xunkong",
            "consecutive_stems",
            "day_pillar",
            "day_or_hour_pillar",
            "tongzi_season_nayin",
        }:
            _evaluate_special_natal(bucket, rule=rule, pillars=pillars, version=version)
        else:
            _evaluate_mapped_natal(bucket, rule=rule, pillars=pillars, version=version)
    position_rank = {position: index for index, position in enumerate(_POSITION_ORDER)}
    return sorted(
        bucket.values(),
        key=lambda hit: (position_rank.get(hit.target_position, 99), hit.rule_id),
    )


def evaluate_shensha_for_target(
    natal: FourPillars,
    target: Pillar,
    *,
    target_position: TemporalScope,
    gender: str = "unspecified",
    season_branch: str | None = None,
    rule_profile: ShenshaRuleProfile = DEFAULT_SHENSHA_RULE_PROFILE,
) -> list[ShenShaHit]:
    """Evaluate one external temporal pillar against the natal anchors."""
    version, rules = _rules()
    bucket: dict[tuple[str, str], ShenShaHit] = {}
    for rule in rules:
        if not _rule_enabled(rule, rule_profile):
            continue
        reference = str(rule.get("reference", ""))
        if reference in {"year_branch_goujiao", "year_branch_yuanchen"}:
            _evaluate_gender_target(
                bucket,
                rule=rule,
                natal=natal,
                target=target,
                target_position=target_position,
                gender=gender,
                version=version,
            )
        elif reference in {"year_or_day_xunkong", "day_pillar"}:
            _evaluate_special_target(
                bucket,
                rule=rule,
                natal=natal,
                target=target,
                target_position=target_position,
                version=version,
            )
        elif reference not in {
            "consecutive_stems",
            "day_or_hour_pillar",
            "tongzi_season_nayin",
        }:
            _evaluate_mapped_target(
                bucket,
                rule=rule,
                natal=natal,
                target=target,
                target_position=target_position,
                version=version,
                season_branch=season_branch,
            )
    return sorted(bucket.values(), key=lambda hit: (hit.name, hit.rule_id))
