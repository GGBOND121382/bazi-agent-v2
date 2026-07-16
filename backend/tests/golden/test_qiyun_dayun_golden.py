"""Golden snapshots for precise 节 reference, direction and 60-cycle order."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.services.calculate_chart import calculate

CASES = json.loads((Path(__file__).with_name("qiyun_dayun_v1.json")).read_text(encoding="utf-8"))


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_qiyun_dayun_snapshot(case: dict) -> None:
    result = calculate(
        utc=datetime.fromisoformat(case["utc"]),
        gender=case["gender"],
        chart_id="golden",
    )
    assert [str(pillar) for pillar in result.pillars.as_list()] == case["pillars"]
    assert result.qiyun is not None
    assert {
        "start_age_years": result.qiyun["start_age_years"],
        "direction": result.qiyun["direction"],
        "reference_jie_utc": result.qiyun["reference_jie_utc"],
    } == case["qiyun"]
    assert [
        [item["start_age"], item["end_age"], item["ganzhi"]] for item in result.dayun
    ] == case["dayun"]
