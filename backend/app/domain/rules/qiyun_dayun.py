"""起运 + 大运 computation.

Rules (per `calculation_profile_v1.yaml`):
- direction_rule: gender_and_year_stem_yinyang
    - 男+阳年 or 女+阴年 → 顺排 (forward, next 节)
    - 男+阴年 or 女+阳年 → 逆排 (reverse, previous 节)
- forward_reference: next_jie
- reverse_reference: previous_jie
- qiyun_conversion: three_days_one_year (default)
- traditional_month_days: 30
- dayun_period_years: 10
- first_pillar_offset_from_month: 1 (first 大运 柱 is month_pillar + 1)

起运 age: round((days_from_birth_to_reference_jie) / 3) years (3 days = 1 year).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..pillars import Branch, FourPillars, Pillar, Stem
from ..profile import CalculationProfile


@dataclass(frozen=True, slots=True)
class DayunPeriod:
    index: int  # 1-based
    start_age: int  # inclusive
    end_age: int  # exclusive
    ganzhi: str  # pillar ganzhi
    pillar: Pillar


@dataclass(frozen=True, slots=True)
class QiyunResult:
    start_age_years: int
    direction: str  # 'forward' | 'reverse'
    reference_jie_utc: datetime  # the 节气 used as reference
    dayun: tuple[DayunPeriod, ...]


# The 节 order in the year (used to compute next/previous 节气).
_JIE_BRANCHES_IN_ORDER = ("寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑")


def _is_yang_stem(stem: Stem) -> bool:
    return stem.yin_yang == "yang"


def _pillar_forward(p: Pillar, steps: int) -> Pillar:
    """Advance a 柱 on the 60-cycle by `steps` positions."""
    from ...domain.pillars import EARTHLY_BRANCHES as B
    from ...domain.pillars import HEAVENLY_STEMS as S

    s_idx = (p.stem.index + steps) % 10
    b_idx = (p.branch.index + steps) % 12
    # Preserve the (stem, branch) relationship of a valid 60-cycle pillar.
    # Since we're advancing both stem and branch by the same step, parity is preserved.
    return Pillar(Stem(S[s_idx]), Branch(B[b_idx]))


def _approximate_next_jie(birth_utc: datetime, month_branch_index: int) -> datetime:
    """Approximate the next 节气 instant after `birth_utc` for the given month
    branch index. This is a placeholder until a proper 节气 adapter is wired in
    (B1 left 节气 adapter as a future task). For now we use month boundaries.

    Returns the 15th of next month at 00:00 UTC as a coarse approximation.
    """
    if month_branch_index == 11:  # 丑 wraps to 寅
        year = birth_utc.year + 1
        month = 2
    else:
        # 节气 approximately falls in this month
        # Use the 15th as midpoint
        year = birth_utc.year
        # map branch_index → solar month
        solar_month = (month_branch_index + 1) % 12 + 1
        if solar_month <= birth_utc.month:
            year += 1
        month = solar_month
    return datetime(year, month, 15, tzinfo=birth_utc.tzinfo)


def _approximate_previous_jie(birth_utc: datetime, month_branch_index: int) -> datetime:
    if month_branch_index == 2:  # 寅 wraps back to 丑
        year = birth_utc.year - 1
        month = 12
    else:
        year = birth_utc.year
        solar_month = (month_branch_index + 1) % 12 - 1
        if solar_month == 0:
            solar_month = 12
            year -= 1
        if solar_month >= birth_utc.month:
            year -= 1
        month = solar_month
    return datetime(year, month, 15, tzinfo=birth_utc.tzinfo)


def compute_qiyun_and_dayun(
    *,
    pillars: FourPillars,
    birth_utc: datetime,
    gender: str,  # 'male' | 'female' | 'unspecified'
    profile: CalculationProfile,
    dayun_count: int = 8,
    reference_jie_utc: datetime | None = None,
) -> QiyunResult:
    """Compute 起运 age and the 大运 sequence.

    `birth_utc` must be timezone-aware. `gender` follows the BirthRequest enum.
    Returns a QiyunResult with up to `dayun_count` 大运 periods of
    `dayun_period_years` each.
    """
    if birth_utc.tzinfo is None:
        raise ValueError("birth_utc must be timezone-aware")

    year_stem = pillars.year.stem
    yang = _is_yang_stem(year_stem)
    if gender == "unspecified":
        # treat as yang-year default (the user can refine later)
        forward = yang
    elif gender == "male":
        forward = yang
    else:  # female
        forward = not yang

    direction = "forward" if forward else "reverse"
    month_branch_index = pillars.month.branch.index

    if reference_jie_utc is not None:
        if reference_jie_utc.tzinfo is None:
            raise ValueError("reference_jie_utc must be timezone-aware")
        ref_utc = reference_jie_utc
    elif forward:
        ref_utc = _approximate_next_jie(birth_utc, month_branch_index)
    else:
        ref_utc = _approximate_previous_jie(birth_utc, month_branch_index)

    days_diff = abs((ref_utc - birth_utc).total_seconds()) / 86400
    # 3 days = 1 year conversion
    start_age_years = round(days_diff / profile.dayun.qiyun_conversion_days_per_year)

    # Build 大运 pillars starting at month_pillar + offset
    offset = profile.dayun.first_pillar_offset_from_month
    base = pillars.month
    periods: list[DayunPeriod] = []
    for i in range(dayun_count):
        # The i-th 大运 pillar is the (offset+i)-th step forward on the 60-cycle
        steps = offset + i
        next_p = _pillar_forward(base, steps if forward else -steps)
        start_age = start_age_years + i * profile.dayun.dayun_period_years
        end_age = start_age + profile.dayun.dayun_period_years
        periods.append(
            DayunPeriod(
                index=i + 1,
                start_age=start_age,
                end_age=end_age,
                ganzhi=next_p.ganzhi,
                pillar=next_p,
            )
        )
    return QiyunResult(
        start_age_years=start_age_years,
        direction=direction,
        reference_jie_utc=ref_utc,
        dayun=tuple(periods),
    )
