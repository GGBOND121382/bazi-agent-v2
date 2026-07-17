"""Time normalization adapter.

Given a birth request, produces a NormalizedTime. Handles:
- IANA timezone resolution (zoneinfo)
- DST ambiguous-time detection (PEP-495 fold)
- DST nonexistent-time rejection
- Local mean solar time from longitude
- True solar time from longitude plus the equation of time
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import cos, pi, sin
from zoneinfo import ZoneInfo

from ..domain.errors import (
    AmbiguousTimeError,
    NonexistentTimeError,
    TimeError,
)
from ..domain.profile import CalculationProfile
from ..domain.time import NormalizedTime


def normalize(
    *,
    local_dt: datetime,
    timezone_name: str,
    fold: int | None,
    profile: CalculationProfile,
    longitude: float | None = None,
) -> NormalizedTime:
    """Convert a local civil datetime + IANA timezone into NormalizedTime."""
    try:
        tz = ZoneInfo(timezone_name)
    except Exception as exc:
        raise TimeError(
            f"unknown timezone: {timezone_name}",
            safe_details={"hint": "use IANA name like Asia/Shanghai"},
        ) from exc

    if profile.reject_naive_datetime and local_dt.tzinfo is None:
        raise TimeError("naive datetime rejected by profile")

    if local_dt.tzinfo is None:
        local_aware = local_dt.replace(tzinfo=tz)
    else:
        local_aware = local_dt.astimezone(tz)

    nonexistent = _is_nonexistent(local_aware, tz)
    if nonexistent:
        raise NonexistentTimeError(
            "local civil time did not exist (DST spring-forward)",
            safe_details={"local": local_aware.isoformat(), "timezone": timezone_name},
        )

    ambiguous, fold_resolved = _is_ambiguous(local_aware, tz, fold)
    if ambiguous and fold is None:
        raise AmbiguousTimeError(
            "ambiguous local civil time requires fold=0 or fold=1",
            safe_details={"local": local_aware.isoformat(), "timezone": timezone_name},
        )

    final_fold = fold if fold is not None else (1 if ambiguous and not fold_resolved else 0)
    local_with_fold = local_aware.replace(fold=final_fold)
    utc = local_with_fold.astimezone(UTC)

    lmst: datetime | None = None
    true_solar: datetime | None = None
    if profile.time_basis.longitude_correction_enabled and longitude is not None:
        lmst = _local_mean_solar_time(local_with_fold, longitude)
        if profile.time_basis.true_solar_time_enabled:
            correction = (
                _equation_of_time_minutes(local_with_fold)
                if profile.time_basis.equation_of_time_enabled
                else 0.0
            )
            true_solar = lmst + timedelta(minutes=correction)

    return NormalizedTime(
        utc=utc,
        local_civil=local_with_fold,
        timezone=timezone_name,
        local_mean_solar=lmst,
        true_solar=true_solar,
        time_basis=profile.time_basis.default,
        fold=final_fold,
        nonexistent_resolved=nonexistent,
        ambiguous_resolved=ambiguous,
    )


def _is_nonexistent(local_aware: datetime, tz: ZoneInfo) -> bool:
    """Return True if the wall-clock time does not exist in this timezone."""
    utc = local_aware.astimezone(UTC)
    roundtrip = utc.astimezone(tz)
    local_off = local_aware.utcoffset()
    rt_off = roundtrip.utcoffset()
    if local_off is None or rt_off is None:
        return False
    delta = abs((rt_off - local_off).total_seconds())
    return delta > 1 and (roundtrip.hour != local_aware.hour or roundtrip.minute != local_aware.minute)


def _is_ambiguous(local_aware: datetime, tz: ZoneInfo, fold: int | None) -> tuple[bool, int]:
    """Return (is_ambiguous, fold_resolved)."""
    f0 = local_aware.replace(fold=0).astimezone(UTC)
    f1 = local_aware.replace(fold=1).astimezone(UTC)
    if f0 == f1:
        return False, 0
    return True, (fold if fold is not None else 0)


def _local_mean_solar_time(local_aware: datetime, longitude: float) -> datetime:
    """Shift civil wall time to the local longitude's mean solar time.

    A civil UTC offset corresponds to a standard meridian of four minutes per
    degree. Keeping the original timezone on the returned datetime makes the
    corrected wall-clock value explicit in API responses and logs.
    """
    offset = local_aware.utcoffset()
    if offset is None:
        raise TimeError("local datetime has no UTC offset")
    offset_minutes = offset.total_seconds() / 60.0
    standard_meridian = offset_minutes / 4.0
    longitude_minutes = 4.0 * (longitude - standard_meridian)
    return local_aware + timedelta(minutes=longitude_minutes)


def _equation_of_time_minutes(local_aware: datetime) -> float:
    """Approximate the astronomical equation of time in minutes.

    Uses the commonly published fractional-year approximation. Its precision is
    more than sufficient for hour-branch boundary handling; the unrounded value
    is retained so callers may present seconds rather than silently truncating.
    """
    day_of_year = local_aware.timetuple().tm_yday
    days_in_year = 366 if _is_leap_year(local_aware.year) else 365
    hour = (
        local_aware.hour
        + local_aware.minute / 60.0
        + local_aware.second / 3600.0
        + local_aware.microsecond / 3_600_000_000.0
    )
    gamma = 2.0 * pi / days_in_year * (day_of_year - 1 + (hour - 12.0) / 24.0)
    return 229.18 * (
        0.000075
        + 0.001868 * cos(gamma)
        - 0.032077 * sin(gamma)
        - 0.014615 * cos(2.0 * gamma)
        - 0.040849 * sin(2.0 * gamma)
    )


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
