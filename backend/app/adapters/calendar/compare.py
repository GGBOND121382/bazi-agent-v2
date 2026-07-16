"""Cross-engine comparison.

Runs the same calculation wall time through both engines and reports drift. The
calculation service uses this to decide calculation_status (passed vs needs_review).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...domain.errors import CrossEngineConflictError
from .base import CalendarAdapter


@dataclass(frozen=True, slots=True)
class ConflictReport:
    calculation_time: datetime
    primary: dict[str, str]
    secondary: dict[str, str]
    drifted: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "calculation_time": self.calculation_time.isoformat(),
            "primary": self.primary,
            "secondary": self.secondary,
            "drifted": list(self.drifted),
        }


class CrossEngineComparer:
    """Compares the 4 pillars from two CalendarAdapter instances."""

    def __init__(self, primary: CalendarAdapter, secondary: CalendarAdapter) -> None:
        self.primary = primary
        self.secondary = secondary

    def compare(self, calculation_time: datetime) -> ConflictReport:
        a = self.primary.calculate(calculation_time).pillars
        b = self.secondary.calculate(calculation_time).pillars
        keys = ("year", "month", "day", "hour")
        primary_dict = {k: str(getattr(a, k)) for k in keys}
        secondary_dict = {k: str(getattr(b, k)) for k in keys}
        drifted = tuple(k for k in keys if primary_dict[k] != secondary_dict[k])
        return ConflictReport(
            calculation_time=calculation_time,
            primary=primary_dict,
            secondary=secondary_dict,
            drifted=drifted,
        )

    def assert_no_conflict(self, calculation_time: datetime) -> None:
        report = self.compare(calculation_time)
        if report.drifted:
            raise CrossEngineConflictError(
                "calendar engines disagreed on pillars",
                safe_details=report.to_dict(),
            )
