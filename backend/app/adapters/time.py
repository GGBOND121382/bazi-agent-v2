"""Time normalization adapter.

Given a birth request, produces a NormalizedTime. Handles:
- IANA timezone resolution (zoneinfo)
- DST ambiguous-time detection (PEP-495 fold)
- DST nonexistent-time rejection
- Optional true-solar-time adjustment
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    except Exception as e:
        raise TimeError(
            f"unknown timezone: {timezone_name}",
            safe_details={"hint": "use IANA name like Asia/Shanghai"},
        ) from e

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

    lmst = _local_mean_solar_time(utc, longitude) if profile.time_basis.longitude_correction_enabled and longitude is not None else None
    tst = lmst  # TODO: real equation-of-time + longitude correction

    return NormalizedTime(
        utc=utc,
        local_civil=local_with_fold,
        timezone=timezone_name,
        local_mean_solar=lmst,
        true_solar=tst,
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


def _local_mean_solar_time(utc: datetime, longitude: float | None) -> datetime | None:
    """LMST shifts UTC by 4 minutes per degree of longitude east of GMT."""
    if longitude is None:
        return None
    delta = timedelta(minutes=longitude * 4.0)
    return utc + delta