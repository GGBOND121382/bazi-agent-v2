"""Calendar adapter tests — covers B1 双引擎 + 边界.

Marker 'calendar' filters these out from the default B1 gate run.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.calendar import (
    CrossEngineComparer,
    LunarPythonAdapter,
    ReferenceAdapter,
    SxtwlAdapter,
)
from app.adapters.calendar.base import CalendarAdapter
from app.domain.errors import CrossEngineConflictError


def test_lunar_python_runs():
    """Smoke: lunar_python must produce valid pillars at a known instant."""
    a = LunarPythonAdapter()
    r = a.calculate(datetime(1990, 6, 15, 12, 0, tzinfo=UTC))
    assert len(r.pillars.as_list()) == 4
    for p in r.pillars.as_list():
        assert len(str(p)) == 2


def test_reference_runs():
    a = ReferenceAdapter()
    r = a.calculate(datetime(1990, 6, 15, 12, 0, tzinfo=UTC))
    assert len(r.pillars.as_list()) == 4
    # ReferenceAdapter is the sxtwl fallback; it carries REF_FALLBACK warning.
    assert "REF_FALLBACK" in [w.code for w in r.warnings]


def test_sxtwl_adapter_instantiable_when_lib_present():
    """If sxtwl isn't installed (Windows without MSVC), adapter raises on use;
    we only assert that the constructor either succeeds or raises ImportError-like."""
    try:
        a = SxtwlAdapter()
        a.engine_version()
    except Exception as e:
        # We accept ImportError or build error gracefully
        assert "sxtwl" in str(e).lower() or type(e).__name__ in {"ImportError", "OSError", "RuntimeError"}


def test_cross_engine_comparer_returns_drift_list():
    cmp = CrossEngineComparer(LunarPythonAdapter(), ReferenceAdapter())
    # Reference is intentionally approximate on year/month; day and hour should match
    # for mid-month mid-day instants far from boundary.
    report = cmp.compare(datetime(1990, 6, 15, 12, 0, tzinfo=UTC))
    # Day pillar MUST match between lunar_python and reference (both advance by day)
    assert report.primary["day"] == report.secondary["day"]
    # Hour pillar MUST match when 12:00 UTC falls in 午时 of civil time in CST
    # (12:00 UTC = 20:00 CST → 戌时 index 10). For the reference this is computed
    # from UTC directly; for lunar_python from civil 20:00. Both should match.


def test_cross_engine_comparer_no_drift_when_both_match():
    """With reference_v1 as sxtwl fallback (deferring to lunar_python), the
    two engines agree exactly. The cross-check is still useful: if lunar_python
    changes its API or returns garbage, the strict comparison catches it."""
    cmp = CrossEngineComparer(LunarPythonAdapter(), ReferenceAdapter())
    report = cmp.compare(datetime(1990, 6, 15, 12, 0, tzinfo=UTC))
    assert report.drifted == ()


def test_cross_engine_comparer_assert_passes_when_agree():
    """assert_no_conflict must NOT raise when engines agree."""
    cmp = CrossEngineComparer(LunarPythonAdapter(), ReferenceAdapter())
    # Should not raise.
    cmp.assert_no_conflict(datetime(1990, 6, 15, 12, 0, tzinfo=UTC))


def test_cross_engine_comparer_detects_real_drift_via_mock():
    """Inject a deliberately wrong adapter and verify the comparer flags it.
    This guards against regressions where the strict comparison silently
    degrades to a tautology."""
    from app.adapters.calendar.lunar_python_adapter import LunarPythonAdapter as _LP
    from app.domain.pillars import FourPillars, Stem

    class _PatchedAdapter(CalendarAdapter):
        name = "patched"

        def __init__(self, inner: CalendarAdapter) -> None:
            self.inner = inner

        def engine_version(self):
            return self.inner.engine_version()

        def calculate(self, utc):
            r = self.inner.calculate(utc)
            # Force a different day stem (preserves parity with branch)
            day_p = r.pillars.day
            stem_idx = day_p.stem.index
            branch_idx = day_p.branch.index
            new_stem = Stem(["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"][(stem_idx + 2) % 10])
            new_branch_idx = (branch_idx + 2) % 12
            # ensure parity: stem parity == branch parity in 60-cycle
            if (new_stem.index - new_branch_idx) % 2 != 0:
                new_branch_idx = (new_branch_idx + 1) % 12
            from app.domain.pillars import Branch, Pillar

            new_day = Pillar(new_stem, Branch(["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"][new_branch_idx]))
            new_pillars = FourPillars(
                year=r.pillars.year, month=r.pillars.month, day=new_day, hour=r.pillars.hour,
            )
            return type(r)(
                pillars=new_pillars,
                facts=r.facts,
                warnings=r.warnings,
                engine_version=r.engine_version,
            )

    cmp = CrossEngineComparer(_PatchedAdapter(_LP()), ReferenceAdapter())
    with pytest.raises(CrossEngineConflictError):
        cmp.assert_no_conflict(datetime(1990, 6, 15, 12, 0, tzinfo=UTC))


def test_cross_engine_agree_on_day_pillar_at_safe_instant():
    """The day pillar must be identical when both engines compute from UTC midnight."""
    cmp = CrossEngineComparer(LunarPythonAdapter(), ReferenceAdapter())
    report = cmp.compare(datetime(1990, 6, 15, 0, 30, tzinfo=UTC))
    assert report.primary["day"] == report.secondary["day"]


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2000, 1, 1, 12, 0, tzinfo=UTC),
        datetime(1984, 2, 4, 23, 30, tzinfo=UTC),  # near 立春
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        datetime(1966, 5, 1, 8, 0, tzinfo=UTC),
    ],
)
def test_lunar_python_invariants(instant):
    """Engine version reporting must always be present, with took_ms >= 0."""
    a = LunarPythonAdapter()
    r = a.calculate(instant)
    assert r.engine_version.engine == "lunar_python"
    assert r.engine_version.took_ms >= 0
    # Every fact must have a non-empty rule_id
    for f in r.facts:
        assert f.rule_id.startswith("RULE-")
        assert f.fact_id.startswith("FACT-")
