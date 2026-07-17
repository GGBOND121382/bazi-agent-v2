"""Golden regression for the twelve uploaded 问真命造 examples."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.adapters.calendar.lunar_python_adapter import LunarPythonAdapter
from app.domain.pillars import Branch, FourPillars, Pillar, Stem
from app.domain.rules.relations import evaluate_relations
from app.domain.rules.shensha import evaluate_shensha

GOLDEN = Path(__file__).with_name("wenzhen_compatibility_v1.json")


def _chart(values: list[str]) -> FourPillars:
    pillars = [Pillar(Stem(value[0]), Branch(value[1])) for value in values]
    return FourPillars(*pillars)


def _load_cases() -> list[dict[str, Any]]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return list(payload["cases"])


def test_twelve_examples_keep_pillars_and_required_compatibility_facts() -> None:
    adapter = LunarPythonAdapter(library_version="golden")
    for case in _load_cases():
        expected_pillars = list(case["pillars"])
        if case.get("birth"):
            calculated = adapter.calculate(datetime.fromisoformat(str(case["birth"]))).pillars
            assert [pillar.ganzhi for pillar in calculated.as_list()] == expected_pillars, case["id"]
            chart = calculated
        else:
            chart = _chart(expected_pillars)

        shensha = {(hit.name, hit.target_position) for hit in evaluate_shensha(
            chart, gender=str(case.get("gender", "unspecified"))
        )}
        for expected in case.get("required_shensha", []):
            assert tuple(expected) in shensha, (case["id"], expected, shensha)
        for forbidden in case.get("forbidden_shensha", []):
            assert tuple(forbidden) not in shensha, (case["id"], forbidden, shensha)

        relation_signatures = {
            (item.type, item.branches) for item in evaluate_relations(chart)
        }
        for relation_type, symbols in case.get("required_relations", []):
            expected = (str(relation_type), tuple(symbols))
            assert expected in relation_signatures, (case["id"], expected, relation_signatures)


def test_conservative_profile_excludes_wenzhen_extension_candidates() -> None:
    chart = _chart(["甲寅", "丁卯", "甲戌", "辛未"])
    types = {
        item.type
        for item in evaluate_relations(chart, rule_profile="ziping_conservative_v1")
    }
    assert not {
        "covering",
        "cut_foot",
        "hidden_combination",
        "arching_combination",
        "arching_meeting",
        "punishment_trigger",
        "four_tombs_earth_structure",
        "competing_combination",
    } & types


def test_conservative_shensha_profile_excludes_wenzhen_only_rules() -> None:
    chart = _chart(["丙寅", "己亥", "己巳", "己巳"])
    default_names = {
        hit.name for hit in evaluate_shensha(chart, gender="male")
    }
    conservative_names = {
        hit.name
        for hit in evaluate_shensha(
            chart,
            gender="male",
            rule_profile="ziping_conservative_v1",
        )
    }
    assert {"金神"} <= default_names
    assert "金神" not in conservative_names
