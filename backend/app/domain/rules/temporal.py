"""Exact 大运、流年、流月、流日 calculation backed by lunar-python.

The old implementation sampled the 15th of each civil month and rounded 起运
to an integer age.  This module uses lunar-python's Yun/DaYun/LiuNian/LiuYue
objects and exact 节 timestamps, then enriches every temporal pillar with 十神、
藏干、纳音、长生、空亡、神煞 and relations against the natal chart.
"""
from __future__ import annotations

from datetime import date, datetime, tzinfo
from typing import Any, Literal

from lunar_python import Solar
from lunar_python.util import LunarUtil

from ..pillars import Branch, FourPillars, Pillar, Stem, ten_god_of
from .relations import evaluate_relations
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
    "six_combination": "六合",
    "three_combination": "三合",
    "half_combination": "半合",
    "three_meeting": "三会",
    "half_meeting": "半会",
    "clash": "相冲",
    "harm": "相害",
    "break": "相破",
    "punishment": "相刑",
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


def _target_relations(natal: FourPillars, target: Pillar) -> list[dict[str, object]]:
    """Find relations involving the temporal pillar, preserving natal position."""
    results: list[dict[str, object]] = []
    seen: set[tuple[str, tuple[str, ...], str | None]] = set()
    for position, natal_pillar in zip(_POSITION_ORDER, natal.as_list(), strict=True):
        # Duplicate a target into the hour slot and retain relations containing it.
        overlay = FourPillars(
            year=natal.year,
            month=natal.month,
            day=natal.day,
            hour=target,
        )
        for relation in evaluate_relations(overlay):
            target_char = target.stem.char if relation.type.startswith("stem_") else target.branch.char
            natal_char = (
                natal_pillar.stem.char if relation.type.startswith("stem_") else natal_pillar.branch.char
            )
            if target_char not in relation.branches or natal_char not in relation.branches:
                continue
            key = (relation.type, relation.branches, relation.element)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "type": relation.type,
                    "label": _RELATION_LABELS.get(relation.type, relation.type),
                    "participants": list(relation.branches),
                    "natal_position": position,
                    "element": relation.element,
                    "rule_id": relation.rule_id,
                }
            )
    return results


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
        "relations": _target_relations(natal, target),
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
    local = calculation_time.replace(tzinfo=None)
    eight_char = Solar.fromYmdHms(
        local.year, local.month, local.day, local.hour, local.minute, local.second
    ).getLunar().getEightChar()
    eight_char.setSect(2)
    gender_code = 0 if gender == "female" else 1
    yun = eight_char.getYun(gender_code, 2)
    active_dayun_obj, liunian_obj = _find_liunian(yun, target_year)

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
        "year": target_year,
        "age": int(liunian_obj.getAge()),
        "fact_id": f"LIUNIAN-{target_year}",
        "rule_id": "LIUNIAN-LICHUN-V2",
    }
    xiaoyun = next(
        (
            str(item.getGanZhi())
            for item in active_dayun_obj.getXiaoYun(
                int(active_dayun_obj.getEndYear()) - int(active_dayun_obj.getStartYear()) + 1
            )
            if int(item.getYear()) == target_year
        ),
        None,
    )
    year["xiaoyun"] = xiaoyun

    boundaries = _exact_month_boundaries(target_year, calculation_time.tzinfo)
    months: list[dict[str, object]] = []
    for index, (liuyue, boundary) in enumerate(
        zip(liunian_obj.getLiuYue(), boundaries, strict=True), start=1
    ):
        name, start, end = boundary
        pillar = _pillar(str(liuyue.getGanZhi()))
        months.append(
            {
                **describe_temporal_pillar(
                    natal, pillar, scope="liuyue", gender=gender, season_branch=pillar.branch.char
                ),
                "index": index,
                "label": f"{liuyue.getMonthInChinese()}月",
                "jie_name": name,
                "start_datetime": start.isoformat(),
                "end_datetime": end.isoformat(),
                "fact_id": f"LIUYUE-{target_year}-{index:02d}",
                "rule_id": "LIUYUE-EXACT-JIE-V2",
            }
        )

    selected_date = target_date or date(target_year, 1, 1)
    solar = Solar.fromYmdHms(selected_date.year, selected_date.month, selected_date.day, 12, 0, 0)
    lunar = solar.getLunar()
    day_pillar = _pillar(str(lunar.getDayInGanZhiExact2()))
    month_pillar = _pillar(str(lunar.getMonthInGanZhiExact()))
    selected_day = {
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

    return {
        "qiyun": qiyun,
        "dayuns": dayuns,
        "active_dayun": active_dayun,
        "year": year,
        "months": months,
        "selected_day": selected_day,
        "seasonal_strength": _SEASON_STATES.get(natal.month.branch.char, {}),
    }
