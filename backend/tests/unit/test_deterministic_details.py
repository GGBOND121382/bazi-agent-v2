"""Deterministic detail coverage for the mobile chart view."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.calendar.lunar_python_adapter import LunarPythonAdapter
from app.domain.rules.renyuan_commander import compute_renyuan_commander


def test_common_renyuan_commander_subdivides_solar_term_month() -> None:
    assert compute_renyuan_commander("子", 5).label == "壬水用事"
    assert compute_renyuan_commander("子", 14).label == "癸水用事"
    assert compute_renyuan_commander("子", 31).label == "癸水用事"


def test_1995_screenshot_example_uses_jie_boundaries_and_complete_details() -> None:
    result = LunarPythonAdapter(library_version="test").calculate(
        datetime(1995, 12, 22, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    basic = result.details["basic"]
    assert isinstance(basic, dict)
    assert "大雪" in str(basic["birth_solar_terms"])
    assert "小寒" in str(basic["birth_solar_terms"])
    assert basic["ren_yuan_commander"] == "癸水用事"
    assert basic["tai_yuan"]
    assert basic["tai_xi"]
    assert basic["ming_gong"]
    assert basic["shen_gong"]

    pillars = result.details["pillars"]
    assert isinstance(pillars, list) and len(pillars) == 4
    required = {
        "major_star",
        "hidden_stems",
        "secondary_stars",
        "growth_stage",
        "self_seat",
        "void",
        "nayin",
        "five_elements",
        "shensha",
    }
    assert all(required <= set(item) for item in pillars if isinstance(item, dict))
