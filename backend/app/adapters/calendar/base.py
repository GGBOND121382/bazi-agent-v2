"""Adapter base types — kept abstract, no third-party imports here.

This is the only module the rest of the codebase uses to talk to a calendar
engine. Swapping lunar_python for sxtwl happens by passing a different adapter
instance to the calculation service.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from ...domain.chart import EngineVersion, Fact, Warning
from ...domain.pillars import FourPillars


@dataclass(frozen=True, slots=True)
class CalendarResult:
    pillars: FourPillars
    facts: tuple[Fact, ...]
    warnings: tuple[Warning, ...]
    engine_version: EngineVersion
    # Engine-specific deterministic detail payload.  This stays data-only so
    # higher layers never need to import lunar_python directly.
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SolarTermResult:
    name: str  # 'lichun' | 'jingzhe' | etc.
    instant_utc: datetime


class CalendarAdapter(ABC):
    """Computes 柱 + facts from timezone-aware calculation wall time."""

    name: str

    @abstractmethod
    def calculate(self, calculation_time: datetime) -> CalendarResult: ...

    @abstractmethod
    def engine_version(self) -> EngineVersion: ...


class SolarTermAdapter(ABC):
    name: str

    @abstractmethod
    def previous_jie(self, utc: datetime) -> SolarTermResult: ...

    @abstractmethod
    def next_jie(self, utc: datetime) -> SolarTermResult: ...
