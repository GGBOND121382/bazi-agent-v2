"""Exact 大运、流年、流月、流日 calculation backed by lunar-python.

The old implementation sampled the 15th of each civil month and rounded 起运
to an integer age.  This module uses lunar-python's Yun/DaYun/LiuNian/LiuYue
objects and exact 节 timestamps, then enriches every temporal pillar with 十神、
藏干、纳音、长生、空亡、神煞 and relations against the natal chart.
"""
from __future__ import annotations

from datetime import date, datetime, tzinfo
from hashlib import sha1
from typing import Any, Literal

from lunar_python import Solar
from lunar_python.util import LunarUtil

from ..pillars import Branch, FourPillars, Pillar, Stem, ten_god_of
from .relations import (
    PositionedPillar,
    PositionedRelation,
    evaluate_positioned_relations,
)
from .shensha import evaluate_shensha_for_target

_CHANG_SHENG = ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")
_CHANG_SHENG_OFFSET = {
    "甲": 1, "丙": 10, "戊": 10, "庚": 7, "壬": 4,
    "乙": 6, "丁": 9, "己": 9, "辛": 0, "癸": 3,
}
_POSITION_ORDER = ("year", "month", "day", "hour")
_JIE_NAMES = ("立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "小寒")
_RELATION_LABELS = {
    "stem_combination": "天干相合",
    "stem_clash": "天干相冲",
    "stem_control": "天干相克",
    "stem_repeat": "天干同现",
    "branch_repeat": "地支同现",
    "six_combination": "六合",
    "three_combination": "三合",
    "half_combination": "半合",
    "three_meeting": "三会",
    "half_meeting": "半会",
    "clash": "相冲",
    "harm": "相害",
    "break": "相破",
    "punishment": "相刑",
    "fuyin": "伏吟（同柱）",
    "fanyin": "反吟候选（干冲/克且支冲）",
    "heaven_controls_earth_clashes": "天克地冲",
    "suiyun_binglin": "岁运并临",
    "punishment_trigger": "两支刑触发",
    "hidden_combination": "暗合候选",
    "arching_combination": "拱合候选",
    "arching_meeting": "拱会候选",
    "covering": "盖头",
    "cut_foot": "截脚",
    "four_tombs_earth_structure": "四库齐全（土局候选）",
    "competing_combination": "争合/妒合候选",
}
_HIGH_ATTENTION_TYPES = {
    "fanyin",
    "heaven_controls_earth_clashes",
    "suiyun_binglin",
}
_ATTENTION_TYPES = {
    "clash",
    "harm",
    "punishment",
    "punishment_trigger",
    "break",
    "fuyin",
    "stem_control",
}

_SEASON_STATES = {
    "寅": {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"},
    "卯": {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"},
    "辰": {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"},
    "巳": {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"},
    "午": {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"},
    "未": {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"},
    "申": {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"},
    "酉": {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"},
    "戌": {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"},
    "亥": {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"},
    "子": {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"},
    "丑": {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"},
}
TemporalScope = Literal["dayun", "liunian", "liuyue", "liuri", "liushi"]


def _pillar(ganzhi: str) -> Pillar:
    return Pillar(Stem(ganzhi[0]), Branch(ganzhi[1]))


def _solar_datetime(solar: Any, zone: tzinfo) -> datetime:
    return datetime(
        int(solar.getYear()), int(solar.getMonth()), int(solar.getDay()),
        int(solar.getHour()), int(solar.getMinute()), int(solar.getSecond()), tzinfo=zone,
    )


def _growth_stage(day_master: Stem, branch: Branch) -> str:
    offset = _CHANG_SHENG_OFFSET[day_master.char]
    index = offset + (branch.index if day_master.index % 2 == 0 else -branch.index)
    return _CHANG_SHENG[index % 12]


def _self_seat(pillar: Pillar) -> str:
    return _growth_stage(pillar.stem, pillar.branch)


def _shensha_payload(hits: list[Any]) -> list[dict[str, object]]:
    return [
        {
            "name": hit.name,
            "rule_id": hit.rule_id,
            "reference": hit.reference,
            "anchor": hit.anchor,
            "anchor_position": hit.anchor_position,
            "target": hit.target,
            "source_title": hit.source_title,
            "source_locator": hit.source_locator,
            "rule_version": hit.rule_version,
            "variant": hit.variant,
        }
        for hit in hits
    ]


def _relation_attention(relation_type: str) -> str:
    if relation_type in _HIGH_ATTENTION_TYPES:
        return "high_attention"
    if relation_type in _ATTENTION_TYPES:
        return "attention"
    return "contextual"


def _relation_payload(relation: PositionedRelation) -> dict[str, object]:
    identity = "|".join(
        [
            relation.type,
            *(item.position for item in relation.participants),
            *relation.symbols,
            relation.direction or "",
        ]
    )
    fact_id = f"TREL-{sha1(identity.encode()).hexdigest()[:12].upper()}"
    natal_positions = [
        item.position.removeprefix("natal_")
        for item in relation.participants
        if item.position.startswith("natal_")
    ]
    temporal_positions = [
        item.position
        for item in relation.participants
        if not item.position.startswith("natal_")
    ]
    payload: dict[str, object] = {
        "fact_id": fact_id,
        "type": relation.type,
        "label": _RELATION_LABELS.get(relation.type, relation.type),
        "participants": list(relation.symbols),
        "participant_positions": [
            {
                "position": item.position,
                "ganzhi": item.pillar.ganzhi,
                "stem": item.pillar.stem.char,
                "branch": item.pillar.branch.char,
            }
            for item in relation.participants
        ],
        "natal_positions": natal_positions,
        "temporal_positions": temporal_positions,
        "element": relation.element,
        "direction": relation.direction,
        "basis": list(relation.basis),
        "rule_id": relation.rule_id,
        "attention": _relation_attention(relation.type),
        "requires_interpretation": True,
        "variant": relation.variant,
    }
    if len(natal_positions) == 1:
        payload["natal_position"] = natal_positions[0]
    return payload


def _natal_nodes(natal: FourPillars) -> list[PositionedPillar]:
    return [
        PositionedPillar(f"natal_{position}", pillar)
        for position, pillar in zip(_POSITION_ORDER, natal.as_list(), strict=True)
    ]


def _target_relations(
    natal: FourPillars,
    target: Pillar,
    *,
    target_position: str,
) -> list[dict[str, object]]:
    """Find every relation involving a temporal pillar without replacing 时柱."""
    target_node = PositionedPillar(target_position, target)
    relations = evaluate_positioned_relations([*_natal_nodes(natal), target_node])
    return [
        _relation_payload(relation)
        for relation in relations
        if any(item.position == target_position for item in relation.participants)
        and any(item.position.startswith("natal_") for item in relation.participants)
    ]


def _payload_pillar(payload: dict[str, object]) -> Pillar | None:
    ganzhi = str(payload.get("ganzhi", ""))
    if len(ganzhi) != 2:
        return None
    return _pillar(ganzhi)


def _cross_layer_relations(
    layers: list[tuple[str, dict[str, object] | None]],
) -> list[dict[str, object]]:
    nodes: list[PositionedPillar] = []
    payload_by_position: dict[str, dict[str, object]] = {}
    for position, payload in layers:
        if not isinstance(payload, dict):
            continue
        pillar = _payload_pillar(payload)
        if pillar is None:
            continue
        nodes.append(PositionedPillar(position, pillar))
        payload_by_position[position] = payload
    relations = [_relation_payload(item) for item in evaluate_positioned_relations(nodes)]

    dayun = payload_by_position.get("dayun")
    liunian = payload_by_position.get("liunian")
    if dayun is not None and liunian is not None and dayun.get("ganzhi") == liunian.get("ganzhi"):
        relations.append(
            {
                "fact_id": f"TREL-{sha1(f'suiyun_binglin|{dayun["ganzhi"]}'.encode()).hexdigest()[:12].upper()}",
                "type": "suiyun_binglin",
                "label": _RELATION_LABELS["suiyun_binglin"],
                "participants": [str(dayun["ganzhi"]), str(liunian["ganzhi"])],
                "participant_positions": [
                    {"position": "dayun", "ganzhi": dayun["ganzhi"]},
                    {"position": "liunian", "ganzhi": liunian["ganzhi"]},
                ],
                "natal_positions": [],
                "temporal_positions": ["dayun", "liunian"],
                "element": None,
                "direction": None,
                "basis": ["same_dayun_liunian_ganzhi"],
                "rule_id": "TEMPORAL-SUIYUN-BINGLIN-001",
                "attention": "high_attention",
                "requires_interpretation": True,
            }
        )
    unique: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for relation in relations:
        raw_positions = relation.get("temporal_positions", [])
        raw_participants = relation.get("participants", [])
        positions = raw_positions if isinstance(raw_positions, list) else []
        participants = raw_participants if isinstance(raw_participants, list) else []
        key = (
            relation.get("type"),
            tuple(str(item) for item in positions),
            tuple(str(item) for item in participants),
            relation.get("direction"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(relation)
    return unique


def _interaction_summary(relations: list[dict[str, object]]) -> dict[str, object]:
    high = [item for item in relations if item.get("attention") == "high_attention"]
    attention = [item for item in relations if item.get("attention") == "attention"]
    return {
        "total": len(relations),
        "high_attention_count": len(high),
        "attention_count": len(attention),
        "high_attention_types": list(dict.fromkeys(str(item.get("type")) for item in high)),
        "note": "结构触发不等于吉凶结论，需结合旺衰、喜忌、成化与救应解释。",
    }


def describe_temporal_pillar(
    natal: FourPillars,
    target: Pillar,
    *,
    scope: TemporalScope,
    gender: str,
    season_branch: str | None = None,
) -> dict[str, object]:
    hidden_stems = target.hidden_stems()
    hits = evaluate_shensha_for_target(
        natal,
        target,
        target_position=scope,
        gender=gender,
        season_branch=season_branch,
    )
    relations = _target_relations(natal, target, target_position=scope)
    return {
        "ganzhi": target.ganzhi,
        "stem": target.stem.char,
        "branch": target.branch.char,
        "stem_ten_god": ten_god_of(natal.day_master, target.stem),
        "branch_ten_god": ten_god_of(natal.day_master, hidden_stems[0]) if hidden_stems else "",
        "hidden_stems": [
            {"stem": stem.char, "ten_god": ten_god_of(natal.day_master, stem)}
            for stem in hidden_stems
        ],
        "growth_stage": _growth_stage(natal.day_master, target.branch),
        "self_seat": _self_seat(target),
        "xunkong": str(LunarUtil.getXunKong(target.ganzhi)),
        "nayin": target.nayin,
        "shensha": _shensha_payload(hits),
        "relations": relations,
        "relation_summary": _interaction_summary(relations),
    }


def _exact_month_boundaries(year: int, zone: tzinfo) -> list[tuple[str, datetime, datetime]]:
    current = Solar.fromYmdHms(year, 6, 15, 12, 0, 0).getLunar().getJieQiTable()
    next_year = Solar.fromYmdHms(year + 1, 6, 15, 12, 0, 0).getLunar().getJieQiTable()
    starts: list[tuple[str, datetime]] = []
    for name in _JIE_NAMES:
        source = next_year if name == "小寒" else current
        solar = source.get(name)
        if solar is None:
            raise ValueError(f"missing exact jie timestamp: {year} {name}")
        dt = _solar_datetime(solar, zone)
        if name == "小寒" and dt.year == year:
            solar = next_year[name]
            dt = _solar_datetime(solar, zone)
        starts.append((name, dt))
    next_lichun = next_year.get("立春")
    if next_lichun is None:
        raise ValueError(f"missing next lichun timestamp: {year + 1}")
    end = _solar_datetime(next_lichun, zone)
    result: list[tuple[str, datetime, datetime]] = []
    for index, (name, start) in enumerate(starts):
        next_start = starts[index + 1][1] if index + 1 < len(starts) else end
        result.append((name, start, next_start))
    return result


def _find_liunian(yun: Any, target_year: int) -> tuple[Any, Any]:
    for dayun in yun.getDaYun(16):
        if int(dayun.getStartYear()) <= target_year <= int(dayun.getEndYear()):
            count = int(dayun.getEndYear()) - int(dayun.getStartYear()) + 1
            for liunian in dayun.getLiuNian(count):
                if int(liunian.getYear()) == target_year:
                    return dayun, liunian
    raise ValueError(f"target year is outside lunar-python yun range: {target_year}")


def compute_exact_yun(
    calculation_time: datetime,
    *,
    gender: str,
    count: int = 12,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Return exact 起运 metadata and library-authored 大运 periods."""
    local = calculation_time.replace(tzinfo=None)
    eight_char = Solar.fromYmdHms(
        local.year, local.month, local.day, local.hour, local.minute, local.second
    ).getLunar().getEightChar()
    eight_char.setSect(2)
    gender_code = 0 if gender == "female" else 1
    yun = eight_char.getYun(gender_code, 2)
    start_solar = yun.getStartSolar()
    zone = calculation_time.tzinfo
    if zone is None:
        raise ValueError("calculation_time must be timezone-aware")
    qiyun: dict[str, object] = {
        "direction": "forward" if yun.isForward() else "reverse",
        "start_years": int(yun.getStartYear()),
        "start_months": int(yun.getStartMonth()),
        "start_days": int(yun.getStartDay()),
        "start_hours": int(yun.getStartHour()),
        "start_age_years": int(yun.getStartYear()),
        "start_datetime": _solar_datetime(start_solar, zone).isoformat(),
        "rule_id": "QIYUN-LUNAR-PYTHON-SECT2-V2",
    }
    dayun = [
        {
            "index": int(item.getIndex()),
            "start_year": int(item.getStartYear()),
            "end_year": int(item.getEndYear()),
            "start_age": int(item.getStartAge()),
            "end_age": int(item.getEndAge()),
            "ganzhi": str(item.getGanZhi()),
            "xunkong": str(item.getXunKong()),
            "fact_id": f"DAYUN-{int(item.getIndex())}",
            "rule_id": "DAYUN-LUNAR-PYTHON-V2",
        }
        for item in yun.getDaYun(count + 1)
        if int(item.getIndex()) > 0
    ]
    return qiyun, dayun


def build_temporal_context(
    natal: FourPillars,
    calculation_time: datetime,
    *,
    gender: str,
    target_year: int,
    target_date: date | None = None,
) -> dict[str, object]:
    if calculation_time.tzinfo is None:
        raise ValueError("calculation_time must be timezone-aware")
    selected_date = target_date or date(target_year, 7, 1)
    zone = calculation_time.tzinfo
    target_moment = datetime(
        selected_date.year,
        selected_date.month,
        selected_date.day,
        12,
        0,
        tzinfo=zone,
    )
    target_year_boundaries = _exact_month_boundaries(target_year, zone)
    lichun = target_year_boundaries[0][1]
    effective_liunian_year = target_year - 1 if target_moment < lichun else target_year

    local = calculation_time.replace(tzinfo=None)
    eight_char = Solar.fromYmdHms(
        local.year, local.month, local.day, local.hour, local.minute, local.second
    ).getLunar().getEightChar()
    eight_char.setSect(2)
    gender_code = 0 if gender == "female" else 1
    yun = eight_char.getYun(gender_code, 2)
    active_dayun_obj, liunian_obj = _find_liunian(yun, effective_liunian_year)

    qiyun, raw_dayuns = compute_exact_yun(calculation_time, gender=gender)
    dayuns: list[dict[str, object]] = []
    for item in raw_dayuns:
        pillar = _pillar(str(item["ganzhi"]))
        enriched = describe_temporal_pillar(natal, pillar, scope="dayun", gender=gender)
        dayuns.append({**item, **enriched})
    active_dayun = next(
        (item for item in dayuns if int(str(item["index"])) == int(active_dayun_obj.getIndex())), None
    )

    year_pillar = _pillar(str(liunian_obj.getGanZhi()))
    year = {
        **describe_temporal_pillar(natal, year_pillar, scope="liunian", gender=gender),
        "year": effective_liunian_year,
        "civil_target_year": target_year,
        "lichun_year": effective_liunian_year,
        "age": int(liunian_obj.getAge()),
        "fact_id": f"LIUNIAN-{effective_liunian_year}",
        "rule_id": "LIUNIAN-LICHUN-V2",
    }
    xiaoyun = next(
        (
            str(item.getGanZhi())
            for item in active_dayun_obj.getXiaoYun(
                int(active_dayun_obj.getEndYear()) - int(active_dayun_obj.getStartYear()) + 1
            )
            if int(item.getYear()) == effective_liunian_year
        ),
        None,
    )
    year["xiaoyun"] = xiaoyun
    year_interactions = _cross_layer_relations(
        [("dayun", active_dayun), ("liunian", year)]
    )
    year["temporal_interactions"] = year_interactions
    year["interaction_summary"] = _interaction_summary(year_interactions)

    boundaries = (
        target_year_boundaries
        if effective_liunian_year == target_year
        else _exact_month_boundaries(effective_liunian_year, zone)
    )
    months: list[dict[str, object]] = []
    for index, (liuyue, boundary) in enumerate(
        zip(liunian_obj.getLiuYue(), boundaries, strict=True), start=1
    ):
        name, start, end = boundary
        pillar = _pillar(str(liuyue.getGanZhi()))
        month_payload: dict[str, object] = {
            **describe_temporal_pillar(
                natal, pillar, scope="liuyue", gender=gender, season_branch=pillar.branch.char
            ),
            "index": index,
            "label": f"{liuyue.getMonthInChinese()}月",
            "jie_name": name,
            "start_datetime": start.isoformat(),
            "end_datetime": end.isoformat(),
            "fact_id": f"LIUYUE-{effective_liunian_year}-{index:02d}",
            "rule_id": "LIUYUE-EXACT-JIE-V2",
        }
        month_interactions = _cross_layer_relations(
            [("dayun", active_dayun), ("liunian", year), ("liuyue", month_payload)]
        )
        month_payload["temporal_interactions"] = month_interactions
        month_payload["interaction_summary"] = _interaction_summary(month_interactions)
        months.append(month_payload)

    solar = Solar.fromYmdHms(selected_date.year, selected_date.month, selected_date.day, 12, 0, 0)
    lunar = solar.getLunar()
    day_pillar = _pillar(str(lunar.getDayInGanZhiExact2()))
    month_pillar = _pillar(str(lunar.getMonthInGanZhiExact()))
    selected_day: dict[str, object] = {
        **describe_temporal_pillar(
            natal,
            day_pillar,
            scope="liuri",
            gender=gender,
            season_branch=month_pillar.branch.char,
        ),
        "date": selected_date.isoformat(),
        "lunar_date": str(lunar.toString()),
        "month_ganzhi": month_pillar.ganzhi,
        "fact_id": f"LIURI-{selected_date.isoformat()}",
        "rule_id": "LIURI-CALENDAR-V2",
    }
    selected_month = next(
        (item for item in months if item.get("ganzhi") == month_pillar.ganzhi),
        None,
    )
    selected_day_interactions = _cross_layer_relations(
        [
            ("dayun", active_dayun),
            ("liunian", year),
            ("liuyue", selected_month),
            ("liuri", selected_day),
        ]
    )
    selected_day["temporal_interactions"] = selected_day_interactions
    selected_day["interaction_summary"] = _interaction_summary(selected_day_interactions)

    interactions = selected_day_interactions
    return {
        "qiyun": qiyun,
        "dayuns": dayuns,
        "active_dayun": active_dayun,
        "year": year,
        "months": months,
        "selected_month": selected_month,
        "selected_day": selected_day,
        "interactions": interactions,
        "interaction_summary": _interaction_summary(interactions),
        "seasonal_strength": _SEASON_STATES.get(natal.month.branch.char, {}),
    }
