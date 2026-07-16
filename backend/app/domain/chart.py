"""ChartResult — pure-data result of a deterministic calculation.

Bridges the domain (pillars, facts) to the API DTO (`chart-result-v1`).
The API layer converts ChartResult to the JSON shape; the domain never knows about HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .pillars import FourPillars


@dataclass(frozen=True, slots=True)
class Fact:
    """A single deterministic fact derived from rules (e.g. '日干 = 己')."""

    fact_id: str
    fact_type: str
    value: object
    rule_id: str
    inputs: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class EngineVersion:
    engine: str  # 'lunar_python' | 'sxtwl' | 'domain_rule_v1'
    version: str
    took_ms: float


@dataclass(frozen=True, slots=True)
class Warning:
    severity: str  # 'info' | 'warning' | 'error'
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ChartResult:
    chart_id: str
    calculation_status: str  # 'passed' | 'needs_review' | 'ambiguous' | 'failed'
    calculation_profile_id: str
    normalized_utc: datetime
    calculation_time: datetime
    time_basis: str
    pillars: FourPillars
    facts: tuple[Fact, ...]
    engine_versions: tuple[EngineVersion, ...]
    warnings: tuple[Warning, ...]
    qiyun: dict[str, object] | None = None
    dayun: tuple[dict[str, object], ...] = ()

    @property
    def day_master(self) -> str:
        return str(self.pillars.day_master)

    def pillar_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "position": pos,
                "ganzhi": str(p),
                "stem": str(p.stem),
                "branch": str(p.branch),
                "nayin": p.nayin,
                "hidden_stems": [{"stem": str(h), "ten_god": ""} for h in p.hidden_stems()],
                "ten_god_of_stem": p.ten_god_of_stem(self.pillars.day_master),
            }
            for pos, p in zip(
                ("year", "month", "day", "hour"), self.pillars.as_list(), strict=True
            )
        ]
