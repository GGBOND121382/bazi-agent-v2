"""Time normalization tests — covers DST ambiguous/nonexistent policies."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.adapters.time import normalize
from app.domain.errors import AmbiguousTimeError, NonexistentTimeError, TimeError
from app.domain.profile import load_profile


@pytest.fixture
def profile():
    return load_profile()


class TestTimezone:
    def test_unknown_timezone_rejected(self, profile):
        with pytest.raises(TimeError):
            normalize(
                local_dt=datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                timezone_name="Mars/Olympus",
                fold=None,
                profile=profile,
            )

    def test_naive_datetime_rejected(self, profile):
        with pytest.raises(TimeError):
            normalize(
                local_dt=datetime(2024, 1, 1, 12, 0),
                timezone_name="Asia/Shanghai",
                fold=None,
                profile=profile,
            )

    def test_known_timezone_resolves(self, profile):
        nt = normalize(
            local_dt=datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone_name="Asia/Shanghai",
            fold=None,
            profile=profile,
        )
        assert nt.timezone == "Asia/Shanghai"
        # 12:00 Asia/Shanghai (UTC+8) → 04:00 UTC
        assert nt.utc.hour == 4
        assert nt.utc.tzinfo is not None
        assert nt.effective_calendar_time.hour == 12
        assert nt.effective_calendar_time.utcoffset().total_seconds() == 8 * 3600


class TestDST:
    """America/New_York DST 2024: spring-forward 2024-03-10 02:00, fall-back 2024-11-03 02:00."""

    def test_nonexistent_time_rejected(self, profile):
        with pytest.raises(NonexistentTimeError):
            normalize(
                local_dt=datetime(2024, 3, 10, 2, 30, tzinfo=ZoneInfo("America/New_York")),
                timezone_name="America/New_York",
                fold=None,
                profile=profile,
            )

    def test_ambiguous_time_requires_fold(self, profile):
        with pytest.raises(AmbiguousTimeError):
            normalize(
                local_dt=datetime(2024, 11, 3, 1, 30, tzinfo=ZoneInfo("America/New_York")),
                timezone_name="America/New_York",
                fold=None,
                profile=profile,
            )

    def test_ambiguous_time_fold_0_resolves_to_utc_5(self, profile):
        nt = normalize(
            local_dt=datetime(2024, 11, 3, 1, 30, tzinfo=ZoneInfo("America/New_York")),
            timezone_name="America/New_York",
            fold=0,
            profile=profile,
        )
        # EDT (UTC-4) → 05:30 UTC
        assert nt.utc.hour == 5
        assert nt.fold == 0
        assert nt.ambiguous_resolved is True

    def test_ambiguous_time_fold_1_resolves_to_utc_6(self, profile):
        nt = normalize(
            local_dt=datetime(2024, 11, 3, 1, 30, tzinfo=ZoneInfo("America/New_York")),
            timezone_name="America/New_York",
            fold=1,
            profile=profile,
        )
        # EST (UTC-5) → 06:30 UTC
        assert nt.utc.hour == 6
        assert nt.fold == 1


class TestTimeBasis:
    def test_lmst_when_longitude_provided(self, profile):
        nt = normalize(
            local_dt=datetime(2024, 6, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone_name="Asia/Shanghai",
            fold=None,
            profile=profile,
            longitude=121.5,  # Shanghai approx
        )
        assert nt.local_mean_solar is not None
        # 4 min per degree east of GMT
        delta_minutes = (nt.local_mean_solar - nt.utc).total_seconds() / 60
        assert abs(delta_minutes - 121.5 * 4) < 0.01
