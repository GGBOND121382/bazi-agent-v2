"""Scope/topic prompt projection tests."""
from __future__ import annotations

from app.api.dto import ChartResultDTO, EngineVersionDTO, FactDTO, PillarDTO, TemporalContextViewDTO
from app.services.chat_context import build_model_context, detect_chat_topics


def _chart() -> ChartResultDTO:
    details = {
        "basic": {
            "gender": "male",
            "birth_datetime_local": "1995-12-22T16:00:00",
            "ren_yuan_commander": "癸水用事",
        },
        "pillars": [
            {
                "position": "year",
                "ganzhi": "乙亥",
                "stem": "乙",
                "branch": "亥",
                "major_star": "偏印",
                "hidden_stems": [
                    {"stem": "壬", "ten_god": "正官"},
                    {"stem": "甲", "ten_god": "正印"},
                ],
                "void": "申酉",
                "shensha": ["天乙贵人"],
            },
            {
                "position": "month",
                "ganzhi": "戊子",
                "stem": "戊",
                "branch": "子",
                "major_star": "伤官",
                "hidden_stems": [{"stem": "癸", "ten_god": "七杀"}],
                "shensha": ["桃花"],
            },
            {
                "position": "day",
                "ganzhi": "丁亥",
                "stem": "丁",
                "branch": "亥",
                "major_star": "日主",
                "hidden_stems": [
                    {"stem": "壬", "ten_god": "正官"},
                    {"stem": "甲", "ten_god": "正印"},
                ],
                "void": "午未",
            },
            {
                "position": "hour",
                "ganzhi": "戊申",
                "stem": "戊",
                "branch": "申",
                "major_star": "伤官",
                "hidden_stems": [
                    {"stem": "庚", "ten_god": "正财"},
                    {"stem": "壬", "ten_god": "正官"},
                    {"stem": "戊", "ten_god": "伤官"},
                ],
                "shensha": ["金舆"],
            },
        ],
        "five_elements": [
            {"element": "木", "total": 3},
            {"element": "火", "total": 1},
            {"element": "水", "total": 7},
        ],
        "shensha": [
            {"name": "桃花", "target_position": "month", "variant": "classical_or_common"},
            {"name": "金舆", "target_position": "hour", "variant": "classical_or_common"},
        ],
    }
    return ChartResultDTO(
        chart_id="chart-test",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={},
        calendar={"deterministic_details": details},
        pillars=[
            PillarDTO(position="year", ganzhi="乙亥", stem="乙", branch="亥"),
            PillarDTO(position="month", ganzhi="戊子", stem="戊", branch="子"),
            PillarDTO(position="day", ganzhi="丁亥", stem="丁", branch="亥"),
            PillarDTO(position="hour", ganzhi="戊申", stem="戊", branch="申"),
        ],
        day_master="丁",
        facts=[
            FactDTO(
                fact_id="FACT-DM-1",
                fact_type="day_master",
                value="丁",
                rule_id="RULE-DAY-MASTER",
            )
        ],
        engine_versions=[EngineVersionDTO(engine="test", version="1", took_ms=0)],
        warnings=[],
    )


def _relation(level: str) -> dict[str, object]:
    return {
        "type": "clash",
        "label": "六冲",
        "participants": ["子", "午"],
        "participant_positions": [
            {"position": "natal_month", "ganzhi": "戊子"},
            {"position": level, "ganzhi": "丙午"},
        ],
        "attention": "attention",
        "variant": "ziping_conservative_v1",
        "basis": [],
        "direction": None,
    }


def _temporal() -> TemporalContextViewDTO:
    active = {
        "index": 3,
        "start_year": 2020,
        "end_year": 2029,
        "ganzhi": "乙酉",
        "stem_ten_god": "偏印",
        "branch_ten_god": "偏财",
        "relations": [_relation("dayun")],
        "shensha": [{"name": "天乙贵人", "source_title": "audit-only"}],
    }
    year = {
        "year": 2026,
        "ganzhi": "丙午",
        "stem_ten_god": "劫财",
        "branch_ten_god": "比肩",
        "relations": [_relation("liunian")],
        "temporal_interactions": [_relation("liunian")],
    }
    months = [
        {
            "index": index,
            "label": f"{index}月",
            "ganzhi": "乙未",
            "stem_ten_god": "偏印",
            "branch_ten_god": "食神",
            "start_datetime": f"2026-{index:02d}-01T00:00:00+08:00",
            "end_datetime": f"2026-{index:02d}-28T23:59:59+08:00",
            "relations": [_relation("liuyue")],
            "temporal_interactions": [_relation("liuyue")],
        }
        for index in range(1, 13)
    ]
    selected_month = months[6]
    selected_day = {
        "date": "2026-07-18",
        "ganzhi": "癸巳",
        "month_ganzhi": "乙未",
        "stem_ten_god": "七杀",
        "branch_ten_god": "劫财",
        "relations": [_relation("liuri")],
        "temporal_interactions": [_relation("liuri")],
    }
    return TemporalContextViewDTO(
        chart_id="chart-test",
        target_year=2026,
        breadcrumb=[],
        qiyun={"direction": "reverse", "start_age_years": 4, "rule_id": "audit-only"},
        dayuns=[active, {"index": 4, "ganzhi": "甲申", "start_year": 2030, "end_year": 2039}],
        active_dayun=active,
        year=year,
        months=months,
        selected_month=selected_month,
        selected_day=selected_day,
        interactions=[_relation("liuri")],
        interaction_summary={"total": 1},
        seasonal_strength={"木": "相", "火": "死", "水": "旺"},
    )


def test_topic_detection_supports_multiple_explicit_topics() -> None:
    assert detect_chat_topics("今年事业和财运如何") == ("wealth", "career")
    assert detect_chat_topics("今年的感情机会") == ("relationship",)
    assert detect_chat_topics("整体看一下") == ("general",)


def test_year_scope_keeps_natal_dayun_year_and_month_windows_but_not_day() -> None:
    context = build_model_context(
        _chart(),
        _temporal(),
        scope="year",
        topics=("relationship",),
        selected_dayun=_temporal().active_dayun or {},
    )
    hierarchy = context["temporal_hierarchy"]
    assert "active_dayun" in hierarchy
    assert "target_liunian" in hierarchy
    assert len(hierarchy["monthly_windows"]) == 12
    assert "target_liuyue" not in hierarchy
    assert "target_liuri" not in hierarchy
    relationship = context["topic_context"]["relationship"]
    assert relationship["primary_spouse_star"] == "正财"
    assert relationship["spouse_star_locations"] == [
        {"position": "hour", "source": "hidden_stem", "stem": "庚", "ten_god": "正财"}
    ]


def test_month_and_day_scopes_preserve_all_required_upper_layers() -> None:
    temporal = _temporal()
    month = build_model_context(
        _chart(),
        temporal,
        scope="month",
        topics=("career",),
        selected_dayun=temporal.active_dayun or {},
    )["temporal_hierarchy"]
    assert set(month) >= {"hierarchy", "active_dayun", "target_liunian", "target_liuyue"}
    assert "target_liuri" not in month

    day = build_model_context(
        _chart(),
        temporal,
        scope="day",
        topics=("health",),
        selected_dayun=temporal.active_dayun or {},
    )["temporal_hierarchy"]
    assert set(day) >= {
        "hierarchy",
        "active_dayun",
        "target_liunian",
        "target_liuyue",
        "target_liuri",
    }


def test_dayun_and_lifecycle_scopes_keep_qiyun_and_correct_dayun_detail() -> None:
    temporal = _temporal()
    dayun = build_model_context(
        _chart(),
        temporal,
        scope="dayun",
        topics=("general",),
        selected_dayun=temporal.dayuns[1],
    )["temporal_hierarchy"]
    assert dayun["qiyun"] == {"direction": "reverse", "start_age_years": 4}
    assert dayun["target_dayun"]["ganzhi"] == "甲申"
    assert len(dayun["dayun_sequence"]) == 2

    lifecycle = build_model_context(
        _chart(),
        temporal,
        scope="lifecycle",
        topics=("general",),
        selected_dayun=temporal.active_dayun or {},
    )["temporal_hierarchy"]
    assert len(lifecycle["dayun_sequence"]) == 2
    assert "target_liunian" not in lifecycle


def test_projection_removes_audit_metadata_nulls_and_empty_ten_gods() -> None:
    context = build_model_context(
        _chart(),
        _temporal(),
        scope="day",
        topics=("relationship",),
        selected_dayun=_temporal().active_dayun or {},
    )
    serialized = str(context)
    assert "source_title" not in serialized
    assert "rule_id" not in serialized
    assert "direction': None" not in serialized
    assert "basis': []" not in serialized
    assert "ten_god': ''" not in serialized
