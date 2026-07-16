"""NormalizedTime — canonical UTC+local representation of a birth instant.

Holds timezone-aware datetime plus resolved fold (for ambiguous times),
local civil datetime, and the chosen time basis (civil / LMST / TST).

The domain layer never imports zoneinfo or any calendar lib; the adapter
layer constructs NormalizedTime and hands it to the domain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class NormalizedTime:
    # Original instant in UTC, timezone-aware.
    utc: datetime
    # Civil local datetime (with original offset preserved).
    local_civil: datetime
    # IANA timezone string.
    timezone: str
    # Local mean solar time at the birthplace longitude (optional).
    local_mean_solar: datetime | None
    # True solar time (LMST + equation-of-time + longitude) — optional.
    true_solar: datetime | None
    # Which basis the rest of the calculation should use.
    time_basis: str  # 'civil_time' | 'local_mean_solar_time' | 'true_solar_time'
    # PEP-495 fold used to disambiguate when local clock falls back.
    fold: int
    # True when the local civil time did not actually exist (DST spring-forward).
    nonexistent_resolved: bool = False
    # True when the local civil time was ambiguous and we resolved via fold.
    ambiguous_resolved: bool = False

    def __post_init__(self) -> None:
        if self.utc.tzinfo is None or self.utc.tzinfo.utcoffset(self.utc) != UTC.utcoffset(self.utc):
            raise ValueError("utc must be a timezone-aware UTC datetime")
        if self.fold not in (0, 1):
            raise ValueError("fold must be 0 or 1")
        if self.time_basis not in {"civil_time", "local_mean_solar_time", "true_solar_time"}:
            raise ValueError(f"unknown time_basis: {self.time_basis}")

    @property
    def effective_calendar_time(self) -> datetime:
        """Wall-clock datetime whose fields the calendar engine must consume."""
        if self.time_basis == "civil_time":
            return self.local_civil
        if self.time_basis == "local_mean_solar_time" and self.local_mean_solar is not None:
            return self.local_mean_solar
        if self.time_basis == "true_solar_time" and self.true_solar is not None:
            return self.true_solar
        return self.local_civil
