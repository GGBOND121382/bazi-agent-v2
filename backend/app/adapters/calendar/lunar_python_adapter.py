"""lunar_python adapter — primary calendar engine.

The adapter returns the four pillars plus the deterministic detail fields used
by the mobile chart UI.  No interpretation is performed here: every value is
read from lunar_python or derived from versioned core tables.
"""
from __future__ import annotations

import time as _time
from datetime import datetime
from functools import lru_cache
from typing import Any

from lunar_python import Solar

from ...domain.chart import EngineVersion, Fact
from ...domain.pillars import Branch, FourPillars, Pillar, Stem
from ...domain.rules import evaluate_shensha
from .base import CalendarAdapter, CalendarResult


_ELEMENT_ZH = {
    "wood": "木",
    "fire": "火",
    "earth": "土",
    "metal": "金",
    "water": "水",
    "木": "木",
    "火": "火",
    "土": "土",
    "金": "金",
    "水": "水",
}
_CHANG_SHENG = ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")
_CHANG_SHENG_OFFSET = {
    "甲": 1,
    "丙": 10,
    "戊": 10,
    "庚": 7,
    "壬": 4,
    "乙": 6,
    "丁": 9,
    "己": 9,
    "辛": 0,
    "癸": 3,
}


@lru_cache(maxsize=1)
def _lib_version() -> str:
    try:
        import lunar_python

        return str(getattr(lunar_python, "__version__", "unknown"))
    except Exception:  # pragma: no cover
        return "unknown"


def _safe_call(obj: Any, method: str, default: object = "") -> object:
    value = getattr(obj, method, None)
    if not callable(value):
        return default
    try:
        result = value()
    except Exception:
        return default
    return default if result is None else result


def _solar_to_datetime(value: Any, tzinfo: object) -> datetime:
    return datetime(
        int(value.getYear()),
        int(value.getMonth()),
        int(value.getDay()),
        int(value.getHour()),
        int(value.getMinute()),
        int(value.getSecond()),
        tzinfo=tzinfo,  # type: ignore[arg-type]
    )


def _duration_text(seconds: float) -> str:
    total_hours = max(0, int(seconds // 3600))
    days, hours = divmod(total_hours, 24)
    if days and hours:
        return f"{days}天{hours}小时"
    if days:
        return f"{days}天"
    return f"{hours}小时"


def _self_seat(stem: Stem, branch: Branch) -> str:
    offset = _CHANG_SHENG_OFFSET[stem.char]
    index = offset + (branch.index if stem.index % 2 == 0 else -branch.index)
    return _CHANG_SHENG[index % 12]


class LunarPythonAdapter(CalendarAdapter):
    name = "lunar_python"

    def __init__(self, *, library_version: str | None = None) -> None:
        self._library_version = library_version or _lib_version()

    def engine_version(self) -> EngineVersion:
        return EngineVersion(engine=self.name, version=self._library_version, took_ms=0.0)

    def calculate(self, calculation_time: datetime) -> CalendarResult:
        started = _time.perf_counter()
        if calculation_time.tzinfo is None:
            raise ValueError("calculation_time must be timezone-aware")

        # lunar_python consumes wall-clock fields and has no timezone model. The
        # caller therefore passes the selected civil/true-solar calculation time.
        local_naive = calculation_time.replace(tzinfo=None)
        solar = Solar.fromYmdHms(
            local_naive.year,
            local_naive.month,
            local_naive.day,
            local_naive.hour,
            local_naive.minute,
            local_naive.second,
        )
        lunar = solar.getLunar()
        eight_char = lunar.getEightChar()
        eight_char.setSect(2)

        year_p = self._build_pillar(str(eight_char.getYear()), "year")
        month_p = self._build_pillar(str(eight_char.getMonth()), "month")
        day_p = self._build_pillar(str(eight_char.getDay()), "day")
        hour_p = self._build_pillar(str(eight_char.getTime()), "hour")
        pillars = FourPillars(year=year_p, month=month_p, day=day_p, hour=hour_p)

        facts: list[Fact] = [
            Fact("FACT-Y-1", "pillar", str(year_p), "RULE-PILLAR-YEAR", (calculation_time.year,)),
            Fact(
                "FACT-M-1",
                "pillar",
                str(month_p),
                "RULE-PILLAR-MONTH",
                (calculation_time.year, calculation_time.month),
            ),
            Fact(
                "FACT-D-1",
                "pillar",
                str(day_p),
                "RULE-PILLAR-DAY",
                (calculation_time.year, calculation_time.month, calculation_time.day),
            ),
            Fact(
                "FACT-H-1",
                "pillar",
                str(hour_p),
                "RULE-PILLAR-HOUR",
                (
                    calculation_time.year,
                    calculation_time.month,
                    calculation_time.day,
                    calculation_time.hour,
                ),
            ),
            Fact(
                "FACT-DM-1",
                "day_master",
                str(pillars.day_master),
                "RULE-DAY-MASTER",
                (str(day_p.stem),),
            ),
        ]
        details = self._build_details(
            calculation_time=calculation_time,
            solar=solar,
            lunar=lunar,
            eight_char=eight_char,
            pillars=pillars,
        )
        took = (_time.perf_counter() - started) * 1000.0
        return CalendarResult(
            pillars=pillars,
            facts=tuple(facts),
            warnings=(),
            engine_version=EngineVersion(self.name, self._library_version, took),
            details=details,
        )

    def nearest_jie(self, calculation_time: datetime, *, forward: bool) -> datetime:
        """Return the precise next/previous 节 instant in the adapter time basis."""
        if calculation_time.tzinfo is None:
            raise ValueError("calculation_time must be timezone-aware")
        local = calculation_time.replace(tzinfo=None)
        solar = Solar.fromYmdHms(
            local.year, local.month, local.day, local.hour, local.minute, local.second
        )
        lunar = solar.getLunar()
        jie = lunar.getNextJie(False) if forward else lunar.getPrevJie(False)
        value = jie.getSolar()
        return _solar_to_datetime(value, calculation_time.tzinfo)

    def _build_details(
        self,
        *,
        calculation_time: datetime,
        solar: Any,
        lunar: Any,
        eight_char: Any,
        pillars: FourPillars,
    ) -> dict[str, object]:
        position_defs = (
            ("year", "Year", pillars.year),
            ("month", "Month", pillars.month),
            ("day", "Day", pillars.day),
            ("hour", "Time", pillars.hour),
        )
        hits = evaluate_shensha(pillars)
        pillar_details: list[dict[str, object]] = []
        explicit_counts = {element: 0 for element in "木火土金水"}
        hidden_counts = {element: 0 for element in "木火土金水"}

        for position, prefix, pillar in position_defs:
            hidden = list(_safe_call(eight_char, f"get{prefix}HideGan", []))
            hidden_ten_gods = list(
                _safe_call(eight_char, f"get{prefix}ShiShenZhi", [])
            )
            hidden_items = [
                {
                    "stem": str(stem),
                    "ten_god": str(hidden_ten_gods[index])
                    if index < len(hidden_ten_gods)
                    else "",
                }
                for index, stem in enumerate(hidden)
            ]
            explicit_counts[_ELEMENT_ZH[pillar.stem.element]] += 1
            explicit_counts[_ELEMENT_ZH[pillar.branch.element]] += 1
            for stem in hidden:
                hidden_counts[_ELEMENT_ZH[Stem(str(stem)).element]] += 1
            pillar_details.append(
                {
                    "position": position,
                    "ganzhi": pillar.ganzhi,
                    "stem": pillar.stem.char,
                    "branch": pillar.branch.char,
                    "major_star": str(
                        _safe_call(eight_char, f"get{prefix}ShiShenGan", "")
                    ),
                    "hidden_stems": hidden_items,
                    "secondary_stars": [item["ten_god"] for item in hidden_items],
                    "growth_stage": str(
                        _safe_call(eight_char, f"get{prefix}DiShi", "")
                    ),
                    "self_seat": _self_seat(pillar.stem, pillar.branch),
                    "void": str(
                        _safe_call(eight_char, f"get{prefix}XunKong", "")
                    ),
                    "nayin": str(
                        _safe_call(eight_char, f"get{prefix}NaYin", pillar.nayin)
                    ),
                    "five_elements": str(
                        _safe_call(eight_char, f"get{prefix}WuXing", "")
                    ),
                    "shensha": sorted(
                        {hit.name for hit in hits if hit.target == pillar.branch.char}
                    ),
                }
            )

        prev_jie_qi = lunar.getPrevJieQi(False)
        next_jie_qi = lunar.getNextJieQi(False)
        prev_dt = _solar_to_datetime(prev_jie_qi.getSolar(), calculation_time.tzinfo)
        next_dt = _solar_to_datetime(next_jie_qi.getSolar(), calculation_time.tzinfo)
        after_prev = _duration_text((calculation_time - prev_dt).total_seconds())
        before_next = _duration_text((next_dt - calculation_time).total_seconds())

        month_hidden = pillars.month.hidden_stems()
        commander = month_hidden[0] if month_hidden else pillars.month.stem
        lunar_mansion_parts = [
            str(_safe_call(lunar, "getXiu", "")),
            str(_safe_call(lunar, "getGong", "")),
            str(_safe_call(lunar, "getShou", "")),
        ]
        lunar_mansion = "".join(part for part in lunar_mansion_parts if part)
        lunar_text = str(_safe_call(lunar, "toString", ""))
        time_label = f"{pillars.hour.branch.char}时"

        return {
            "basic": {
                "solar_datetime": str(_safe_call(solar, "toYmdHms", "")),
                "calculation_datetime": calculation_time.isoformat(),
                "lunar_date": f"{lunar_text} {time_label}".strip(),
                "zodiac": str(_safe_call(lunar, "getYearShengXiaoExact", "")),
                "western_zodiac": str(_safe_call(solar, "getXingZuo", "")),
                "lunar_mansion": lunar_mansion,
                "tai_yuan": str(_safe_call(eight_char, "getTaiYuan", "")),
                "tai_yuan_nayin": str(_safe_call(eight_char, "getTaiYuanNaYin", "")),
                "tai_xi": str(_safe_call(eight_char, "getTaiXi", "")),
                "tai_xi_nayin": str(_safe_call(eight_char, "getTaiXiNaYin", "")),
                "ming_gong": str(_safe_call(eight_char, "getMingGong", "")),
                "ming_gong_nayin": str(_safe_call(eight_char, "getMingGongNaYin", "")),
                "shen_gong": str(_safe_call(eight_char, "getShenGong", "")),
                "shen_gong_nayin": str(_safe_call(eight_char, "getShenGongNaYin", "")),
                "ren_yuan_commander": f"{commander.char}{_ELEMENT_ZH[commander.element]}用事",
                "birth_solar_terms": (
                    f"出生于{prev_jie_qi.getName()}后{after_prev}，"
                    f"{next_jie_qi.getName()}前{before_next}"
                ),
                "previous_solar_term": {
                    "name": prev_jie_qi.getName(),
                    "datetime": prev_dt.isoformat(),
                    "elapsed": after_prev,
                },
                "next_solar_term": {
                    "name": next_jie_qi.getName(),
                    "datetime": next_dt.isoformat(),
                    "remaining": before_next,
                },
            },
            "pillars": pillar_details,
            "five_elements": [
                {
                    "element": element,
                    "explicit": explicit_counts[element],
                    "hidden": hidden_counts[element],
                    "total": explicit_counts[element] + hidden_counts[element],
                }
                for element in "木火土金水"
            ],
            "shensha": [
                {
                    "name": hit.name,
                    "target": hit.target,
                    "anchor": hit.anchor,
                    "reference": hit.reference,
                    "rule_id": hit.rule_id,
                }
                for hit in hits
            ],
        }

    @staticmethod
    def _build_pillar(gz: str, position: str) -> Pillar:
        if not isinstance(gz, str) or len(gz) < 2:
            raise ValueError(f"unexpected ganzhi from library for {position}: {gz!r}")
        return Pillar(stem=Stem(gz[0]), branch=Branch(gz[1]))
