"""人元司令分野 — common commercial charting table.

The month starts at the precise 节 instant (not the intermediate 气).  The
elapsed duration from that instant selects the stem currently 用事.  This is a
versioned deterministic display rule; interpretation remains in the LLM/RAG
layer.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..pillars import Stem

RULE_ID = "RENYUAN-COMMON-TABLE-V1"

# Common charting table, each tuple is (stem, duration_days). Totals are 30 days;
# a solar-term month can be slightly longer, in which case the last entry stays
# in force until the next 节.
_COMMON_TABLE: dict[str, tuple[tuple[str, int], ...]] = {
    "寅": (("戊", 7), ("丙", 7), ("甲", 16)),
    "卯": (("甲", 10), ("乙", 20)),
    "辰": (("乙", 9), ("癸", 3), ("戊", 18)),
    "巳": (("戊", 5), ("庚", 9), ("丙", 16)),
    "午": (("丙", 10), ("己", 9), ("丁", 11)),
    "未": (("丁", 9), ("乙", 3), ("己", 18)),
    "申": (("戊", 10), ("壬", 3), ("庚", 17)),
    "酉": (("庚", 10), ("辛", 20)),
    "戌": (("辛", 9), ("丁", 3), ("戊", 18)),
    "亥": (("戊", 7), ("甲", 5), ("壬", 18)),
    "子": (("壬", 10), ("癸", 20)),
    "丑": (("癸", 9), ("辛", 3), ("己", 18)),
}

_ELEMENT_ZH = {
    "wood": "木",
    "fire": "火",
    "earth": "土",
    "metal": "金",
    "water": "水",
}


@dataclass(frozen=True, slots=True)
class RenyuanCommander:
    stem: str
    element: str
    elapsed_days: float
    phase_start_day: float
    phase_end_day: float | None
    rule_id: str = RULE_ID

    @property
    def label(self) -> str:
        return f"{self.stem}{self.element}用事"


def compute_renyuan_commander(month_branch: str, days_since_jie: float) -> RenyuanCommander:
    """Return the common-table commander for a precise solar-term month offset."""
    entries = _COMMON_TABLE.get(month_branch)
    if entries is None:
        raise ValueError(f"unsupported month branch: {month_branch}")
    elapsed = max(0.0, float(days_since_jie))
    start = 0.0
    for index, (stem_char, duration) in enumerate(entries):
        end = start + duration
        if elapsed < end or index == len(entries) - 1:
            stem = Stem(stem_char)
            return RenyuanCommander(
                stem=stem_char,
                element=_ELEMENT_ZH[stem.element],
                elapsed_days=elapsed,
                phase_start_day=start,
                phase_end_day=None if index == len(entries) - 1 else end,
            )
        start = end
    raise AssertionError("renyuan commander table must contain at least one entry")
