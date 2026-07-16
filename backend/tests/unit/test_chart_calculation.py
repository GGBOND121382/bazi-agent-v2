"""End-to-end calculation tests — exercise the full B1 pipeline
(domain + adapters + service + DTO mapper)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.api.dto import ChartResultDTO
from app.domain.chart import ChartResult
from app.domain.profile import load_profile
from app.services.calculate_chart import calculate
from app.services.viewmodel_mapper import to_chart_result_dto


def test_calculate_returns_chart_result():
    p = load_profile()
    result = calculate(utc=datetime(1990, 6, 15, 12, 0, tzinfo=UTC), profile=p)
    assert isinstance(result, ChartResult)
    assert result.calculation_status == "passed"
    assert result.calculation_profile_id == "ziping_standard_v1"
    assert result.day_master in {"甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"}


def test_calculate_to_dto_roundtrip():
    p = load_profile()
    result = calculate(utc=datetime(1990, 6, 15, 12, 0, tzinfo=UTC), profile=p)
    dto = to_chart_result_dto(result)
    assert isinstance(dto, ChartResultDTO)
    assert dto.schema_version == "chart-result-v1"
    assert len(dto.pillars) == 4
    assert dto.chart_id == result.chart_id
    # Engine versions reported by both engines
    assert len(dto.engine_versions) == 2
    engine_names = {ev.engine for ev in dto.engine_versions}
    assert "lunar_python" in engine_names
    # Day pillar string round-trips
    assert dto.pillars[2].ganzhi == str(result.pillars.day)


def test_calculate_naive_datetime_rejected():
    with pytest.raises(ValueError):
        calculate(utc=datetime(1990, 6, 15, 12, 0))  # no tzinfo


def test_calculate_chart_id_provided():
    p = load_profile()
    result = calculate(
        utc=datetime(1990, 6, 15, 12, 0, tzinfo=UTC),
        profile=p,
        chart_id="chart_test_001",
    )
    assert result.chart_id == "chart_test_001"


def test_calculate_facts_cover_all_four_pillars_and_day_master():
    p = load_profile()
    result = calculate(utc=datetime(1990, 6, 15, 12, 0, tzinfo=UTC), profile=p)
    fact_types = {f.fact_type for f in result.facts}
    assert "pillar" in fact_types
    assert "day_master" in fact_types
    # Four pillars + day master (per engine)
    pillar_facts = [f for f in result.facts if f.fact_type == "pillar"]
    assert len(pillar_facts) == 8  # 4 from each engine
