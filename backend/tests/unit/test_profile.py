"""Profile loading tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.errors import ProfileError
from app.domain.profile import load_profile

PROFILE = Path("contracts/calculation_profile_v1.yaml")


def test_default_profile_loads():
    p = load_profile()
    assert p.profile_id == "ziping_standard_v1"
    assert p.schema_version == "calculation-profile-v1"
    assert p.year_boundary == "lichun_exact_time"
    assert p.month_boundary == "jie_exact_time"
    assert p.reject_naive_datetime is True
    assert p.time_basis.default == "civil_time"
    assert p.day_boundary.default == "midnight_00"
    assert p.dayun.direction_rule == "gender_and_year_stem_yinyang"
    assert p.dayun.qiyun_conversion_days_per_year == 3
    assert p.dayun.dayun_period_years == 10
    assert p.shensha_rule_set == "classics_v2.3-wenzhen-compatible"
    assert p.relation_rule_profile == "wenzhen_compatible_v1"
    assert p.shensha_rule_profile == "wenzhen_compatible_v1"


def test_profile_deny_unknown_schema_version(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: calculation-profile-v99\n"
        "profile_id: foo\n"
        "calendar:\n  year_boundary: lichun_exact_time\n"
        "  month_boundary: jie_exact_time\n  solar_term_precision: second\n"
        "  lunar_calendar_variant: chinese_standard\n"
        "civil_time:\n  timezone_source: iana_zoneinfo\n"
        "  reject_naive_datetime: true\n  daylight_saving_policy: historical_zone_rules\n"
        "  ambiguous_time_policy: require_fold_or_candidate\n"
        "  nonexistent_time_policy: reject_and_explain\n"
        "time_basis:\n  default: civil_time\n  allowed: [civil_time]\n"
        "  true_solar_time:\n    longitude_correction: enabled\n    equation_of_time: enabled\n"
        "    implementation: strategy_adapter\n"
        "day_boundary:\n  default: midnight_00\n  allowed: [midnight_00]\n"
        "dayun: {direction_rule: a, forward_reference: a, reverse_reference: a,\n"
        "  qiyun_conversion: three_days_one_year, traditional_month_days: 30,\n"
        "  dayun_period_years: 10, first_pillar_offset_from_month: 1}\n"
        "relations:\n  combination_means_transformation: false\n  enable_branch_break: true\n  enable_self_punishment: true\n"
        "shensha:\n  rule_set: core_v1\n"
        "  default_reference_priority: [day_stem]\n  interpretation_weight: auxiliary_only\n"
        "analysis:\n  school: ziping_standard\n  allow_mixed_school: false\n"
        "  uncertainty_language_required: true\n  prohibit_deterministic_life_event_claims: true\n"
        "versioning:\n  rule_version: r1\n  prompt_version: p1\n  report_schema_version: report-v1\n"
    )
    p = load_profile(bad)
    with pytest.raises(ProfileError):
        p.assert_known()


def test_profile_missing_file_raises():
    with pytest.raises(ProfileError):
        load_profile("/nonexistent/path.yaml")