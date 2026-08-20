"""CalculationProfile — frozen profile object loaded from yaml.

The Profile is the single source of truth for all calculation口径 decisions
in this run. A new profile_id requires a new file in contracts/ and a schema
bump (see DEC-001).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ProfileError

PROFILE_FILE = Path(__file__).resolve().parents[3] / "contracts" / "calculation_profile_v1.yaml"


_QIYUN_NUMBER_WORDS = {"three": 3, "four": 4, "five": 5}


def _parse_qiyun_conversion(value: str) -> int:
    """Parse 'three_days_one_year' → 3; 'four_days_one_year' → 4; else raise."""
    parts = value.split("_")
    head = parts[0].lower() if parts else ""
    if head in _QIYUN_NUMBER_WORDS:
        return _QIYUN_NUMBER_WORDS[head]
    if head.isdigit():
        return int(head)
    raise ProfileError(f"unknown qiyun_conversion format: {value!r}")


@dataclass(frozen=True, slots=True)
class TimeBasis:
    default: str
    allowed: tuple[str, ...]
    true_solar_time_enabled: bool
    equation_of_time_enabled: bool
    longitude_correction_enabled: bool


@dataclass(frozen=True, slots=True)
class DayBoundary:
    default: str
    allowed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Dayun:
    direction_rule: str
    forward_reference: str
    reverse_reference: str
    qiyun_conversion_days_per_year: int
    traditional_month_days: int
    dayun_period_years: int
    first_pillar_offset_from_month: int


@dataclass(frozen=True, slots=True)
class CalculationProfile:
    schema_version: str
    profile_id: str
    status: str
    language: str
    year_boundary: str
    month_boundary: str
    solar_term_precision: str
    lunar_calendar_variant: str
    timezone_source: str
    reject_naive_datetime: bool
    daylight_saving_policy: str
    ambiguous_time_policy: str
    nonexistent_time_policy: str
    time_basis: TimeBasis
    day_boundary: DayBoundary
    zi_hour_start: str
    dayun: Dayun
    combination_means_transformation: bool
    enable_branch_break: bool
    enable_self_punishment: bool
    relation_rule_profile: str
    shensha_rule_set: str
    shensha_rule_profile: str
    school: str
    allow_mixed_school: bool
    uncertainty_language_required: bool
    prohibit_deterministic_life_event_claims: bool
    rule_version: str
    prompt_version: str
    report_schema_version: str

    def assert_known(self) -> None:
        if self.schema_version != "calculation-profile-v1":
            raise ProfileError(
                f"unknown schema_version: {self.schema_version}",
                safe_details={"got": self.schema_version},
            )


def load_profile(path: Path | str | None = None) -> CalculationProfile:
    p = Path(path) if path else PROFILE_FILE
    if not p.exists():
        raise ProfileError(f"profile file missing: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return _parse_profile(raw)


def _parse_profile(raw: dict[str, Any]) -> CalculationProfile:
    if not isinstance(raw, dict):
        raise ProfileError("profile root must be a mapping")

    tb = raw["time_basis"]
    db = raw["day_boundary"]
    dy = raw["dayun"]

    return CalculationProfile(
        schema_version=raw["schema_version"],
        profile_id=raw["profile_id"],
        status=raw.get("status", "unknown"),
        language=raw.get("language", "zh-CN"),
        year_boundary=raw["calendar"]["year_boundary"],
        month_boundary=raw["calendar"]["month_boundary"],
        solar_term_precision=raw["calendar"]["solar_term_precision"],
        lunar_calendar_variant=raw["calendar"]["lunar_calendar_variant"],
        timezone_source=raw["civil_time"]["timezone_source"],
        reject_naive_datetime=bool(raw["civil_time"]["reject_naive_datetime"]),
        daylight_saving_policy=raw["civil_time"]["daylight_saving_policy"],
        ambiguous_time_policy=raw["civil_time"]["ambiguous_time_policy"],
        nonexistent_time_policy=raw["civil_time"]["nonexistent_time_policy"],
        time_basis=TimeBasis(
            default=tb["default"],
            allowed=tuple(tb["allowed"]),
            true_solar_time_enabled=bool(tb.get("true_solar_time", {}).get("longitude_correction", False)),
            equation_of_time_enabled=bool(tb.get("true_solar_time", {}).get("equation_of_time", False)),
            longitude_correction_enabled=bool(tb.get("true_solar_time", {}).get("longitude_correction", False)),
        ),
        day_boundary=DayBoundary(
            default=db["default"],
            allowed=tuple(db["allowed"]),
        ),
        zi_hour_start=raw.get("hour_branch", {}).get("zi_hour_start", "23:00"),
        dayun=Dayun(
            direction_rule=dy["direction_rule"],
            forward_reference=dy["forward_reference"],
            reverse_reference=dy["reverse_reference"],
            qiyun_conversion_days_per_year=_parse_qiyun_conversion(dy["qiyun_conversion"]),
            traditional_month_days=int(dy["traditional_month_days"]),
            dayun_period_years=int(dy["dayun_period_years"]),
            first_pillar_offset_from_month=int(dy["first_pillar_offset_from_month"]),
        ),
        combination_means_transformation=bool(raw["relations"]["combination_means_transformation"]),
        enable_branch_break=bool(raw["relations"]["enable_branch_break"]),
        enable_self_punishment=bool(raw["relations"]["enable_self_punishment"]),
        relation_rule_profile=str(raw["relations"].get("rule_profile", "ziping_conservative_v1")),
        shensha_rule_set=raw["shensha"]["rule_set"],
        shensha_rule_profile=str(raw["shensha"].get("rule_profile", "ziping_conservative_v1")),
        school=raw["analysis"]["school"],
        allow_mixed_school=bool(raw["analysis"]["allow_mixed_school"]),
        uncertainty_language_required=bool(raw["analysis"]["uncertainty_language_required"]),
        prohibit_deterministic_life_event_claims=bool(
            raw["analysis"]["prohibit_deterministic_life_event_claims"]
        ),
        rule_version=raw["versioning"]["rule_version"],
        prompt_version=raw["versioning"]["prompt_version"],
        report_schema_version=raw["versioning"]["report_schema_version"],
    )
