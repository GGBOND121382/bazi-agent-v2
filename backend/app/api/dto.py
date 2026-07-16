"""Pydantic v2 DTOs mirroring contracts/schemas/json_schema/*.json.

Each model pins `model_config = ConfigDict(extra='forbid')` to match
`additionalProperties: false` in JSON Schema. The schema files are the source
of truth; this module is hand-mirrored and validated by contract tests in
tests/contract/.

If a schema changes, update both the JSON Schema and this file in the same
PR. The contract tests will fail otherwise.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- BirthRequest ----------------------------------------------------------


class Birthplace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str
    province: str | None = None
    city: str
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)


class AnalysisRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: date | None = None
    end: date | None = None


class BirthRequest(_Frozen):
    schema_version: Literal["birth-request-v1"] = "birth-request-v1"
    gender: Literal["male", "female", "unspecified"]
    birth_datetime_local: datetime
    timezone: str = Field(min_length=1)
    fold: Literal[0, 1] | None = None
    birthplace: Birthplace
    time_precision: Literal["second", "minute", "hour", "unknown"] | None = None
    uncertainty_minutes: int | None = Field(default=None, ge=0)
    calculation_profile_id: str
    user_focus: list[str] | None = None
    analysis_range: AnalysisRange | None = None


# ---- ChartResult -----------------------------------------------------------


class PillarDTO(_Frozen):
    position: Literal["year", "month", "day", "hour"]
    ganzhi: str = Field(min_length=2, max_length=2)
    stem: str = Field(min_length=1, max_length=1)
    branch: str = Field(min_length=1, max_length=1)
    nayin: str | None = None
    hidden_stems: list[dict[str, Any]] | None = None
    ten_god_of_stem: str | None = None


class FactDTO(_Frozen):
    fact_id: str
    fact_type: str
    value: Any | None = None
    rule_id: str
    inputs: list[Any] | None = None


class EngineVersionDTO(_Frozen):
    engine: str
    version: str
    took_ms: float


class WarningDTO(_Frozen):
    severity: Literal["info", "warning", "error"]
    code: str
    message: str


class ChartResultDTO(_Frozen):
    schema_version: Literal["chart-result-v1"] = "chart-result-v1"
    chart_id: str
    calculation_status: Literal["passed", "needs_review", "ambiguous", "failed"]
    calculation_profile_id: str
    normalized_time: dict[str, Any]
    calendar: dict[str, Any]
    pillars: list[PillarDTO] = Field(min_length=4, max_length=4)
    day_master: str = Field(min_length=1, max_length=1)
    facts: list[FactDTO]
    qiyun: dict[str, Any] | None = None
    dayun: list[dict[str, Any]] | None = None
    temporal_context: list[dict[str, Any]] | None = None
    engine_versions: list[EngineVersionDTO]
    warnings: list[WarningDTO]


# ---- ApiError --------------------------------------------------------------


class ApiError(_Frozen):
    schema_version: Literal["api-error-v1"] = "api-error-v1"
    request_id: str
    error_code: str
    message_key: str
    retryable: bool
    field_errors: list[dict[str, Any]] | None = None
    safe_details: dict[str, Any] | None = None


# ---- ChartOverviewView (DTO mirror; the mapper is in services/viewmodels)


class PillarViewDTO(_Frozen):
    position: Literal["year", "month", "day", "hour"]
    stem: str
    branch: str
    ten_god: str | None
    hidden_stems: list[dict[str, Any]]
    nayin: str | None
    growth_stage: str | None
    fact_ids: list[str]


class ChartOverviewViewDTO(_Frozen):
    schema_version: Literal["chart-overview-view-v1"] = "chart-overview-view-v1"
    chart_id: str
    display_name: str
    status: Literal["calculated", "needs_user_resolution", "needs_review"]
    pillars: list[PillarViewDTO] = Field(min_length=4, max_length=4)
    assumptions: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    five_elements: list[dict[str, Any]] | None = None


# ---- JobEvent --------------------------------------------------------------


class JobEventDTO(_Frozen):
    schema_version: Literal["job-event-v1"] = "job-event-v1"
    event_id: str
    job_id: str
    stage: Literal[
        "queued",
        "calculating",
        "needs_user_resolution",
        "retrieving",
        "interpreting",
        "verifying",
        "revision_pending",
        "report_building",
        "completed",
        "failed",
        "cancelled",
    ]
    progress: int = Field(ge=0, le=100)
    message_key: str
    occurred_at: datetime
    retryable: bool
    safe_details: dict[str, Any] | None = None
    result_ref: str | None = None
    error_code: str | None = None


class TemporalContextViewDTO(_Frozen):
    schema_version: Literal["temporal-context-view-v1"] = "temporal-context-view-v1"
    chart_id: str
    target_year: int
    breadcrumb: list[dict[str, Any]]
    active_dayun: dict[str, Any] | None = None
    year: dict[str, Any]
    months: list[dict[str, Any]] = Field(min_length=12, max_length=12)


# ---- ValidationResult ------------------------------------------------------


class ValidationResultDTO(_Frozen):
    schema_version: Literal["validation-result-v1"] = "validation-result-v1"
    validation_id: str
    analysis_id: str
    status: Literal["passed", "failed", "needs_human_review"]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    approved_claim_ids: list[str]
    required_revisions: list[str]


# ---- StructuredAnalysis ----------------------------------------------------


class ClaimDTO(_Frozen):
    claim_id: str
    topic: str
    statement: str
    fact_ids: list[str] = Field(min_length=1)
    rule_ids: list[str]
    evidence_ids: list[str]
    counterevidence: list[str] | None = None
    confidence: float = Field(ge=0, le=1)
    temporal_scope: str
    school: str | None = None


class StructuredAnalysisDTO(_Frozen):
    schema_version: Literal["analysis-output-v1"] = "analysis-output-v1"
    analysis_id: str
    chart_id: str
    school: str
    claims: list[ClaimDTO]
    limitations: list[str]


class ReportViewDTO(_Frozen):
    schema_version: Literal["report-view-v1"] = "report-view-v1"
    report_id: str
    chart_id: str
    title: str
    generated_at: datetime
    calculation_profile_label: str | None = None
    toc: list[dict[str, Any]]
    blocks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    limitations: list[str]


# ---- UserPreferences -------------------------------------------------------


class UserPreferencesDTO(_Frozen):
    schema_version: Literal["user-preferences-v1"] = "user-preferences-v1"
    language: Literal["zh-CN", "zh-TW"]
    detail_level: Literal["concise", "professional"]
    theme: Literal["light", "dark", "system"]
    reduce_motion: bool | None = None
    default_analysis_topics: list[str] | None = None


# ---- CalculationProfile ----------------------------------------------------


class CalculationProfileDTO(_Frozen):
    schema_version: Literal["calculation-profile-v1"] = "calculation-profile-v1"
    profile_id: str
    status: str | None = None
    calendar: dict[str, Any]
    civil_time: dict[str, Any]
    time_basis: dict[str, Any]
    day_boundary: dict[str, Any]
    hour_branch: dict[str, Any] | None = None
    dayun: dict[str, Any]
    relations: dict[str, Any]
    shensha: dict[str, Any]
    analysis: dict[str, Any] | None = None
    versioning: dict[str, Any]

    @field_validator("schema_version")
    @classmethod
    def _check_schema(cls, v: str) -> str:
        if v != "calculation-profile-v1":
            raise ValueError(f"unknown schema_version: {v}")
        return v
