"""Time normalization tests — DST and solar-time policies."""
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
        assert nt.utc.hour == 4
        assert nt.utc.tzinfo is not None
        assert nt.effective_calendar_time.hour == 12
        assert nt.effective_calendar_time.utcoffset().total_seconds() == 8 * 3600


class TestDST:
    """America/New_York DST 2024 transition cases."""

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
        assert nt.utc.hour == 6
        assert nt.fold == 1


class TestTimeBasis:
    def test_lmst_when_longitude_provided(self, profile):
        civil = datetime(2024, 6, 1, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        nt = normalize(
            local_dt=civil,
            timezone_name="Asia/Shanghai",
            fold=None,
            profile=profile,
            longitude=121.5,
        )
        assert nt.local_mean_solar is not None
        assert (nt.local_mean_solar - civil).total_seconds() == 6 * 60
        assert nt.local_mean_solar.tzinfo == civil.tzinfo

    def test_beijing_1999_true_solar_time_is_not_civil_time(self, profile):
        civil = datetime(1999, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        nt = normalize(
            local_dt=civil,
            timezone_name="Asia/Shanghai",
            fold=None,
            profile=profile,
            longitude=116.42,
        )
        assert nt.local_mean_solar is not None
        assert nt.true_solar is not None
        assert nt.local_mean_solar.strftime("%Y-%m-%d %H:%M:%S") == "1999-06-29 11:45:40"
        assert nt.true_solar.strftime("%Y-%m-%d %H:%M:%S") == "1999-06-29 11:42:37"
        assert nt.true_solar.tzinfo == civil.tzinfo
        # The profile still explicitly selects civil time for the actual chart.
        assert nt.effective_calendar_time == civil

    def test_standard_meridian_has_only_equation_of_time_shift(self, profile):
        civil = datetime(2026, 7, 17, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        nt = normalize(
            local_dt=civil,
            timezone_name="Asia/Shanghai",
            fold=None,
            profile=profile,
            longitude=120.0,
        )
        assert nt.local_mean_solar == civil
        assert nt.true_solar is not None
        assert nt.true_solar != civil
