"""The prompt projection must retain every golden natal fact from the 12 examples."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.api.dto import ChartResultDTO, EngineVersionDTO, FactDTO, PillarDTO
from app.domain.pillars import Branch, FourPillars, Pillar, Stem, ten_god_of
from app.domain.rules.shensha import evaluate_shensha
from app.services.chat_context import build_natal_core

GOLDEN = Path(__file__).with_name("wenzhen_compatibility_v1.json")
POSITIONS = ("year", "month", "day", "hour")


def _four_pillars(values: list[str]) -> FourPillars:
    pillars = [Pillar(Stem(value[0]), Branch(value[1])) for value in values]
    return FourPillars(*pillars)


def _chart_dto(case: dict[str, Any]) -> ChartResultDTO:
    chart = _four_pillars(list(case["pillars"]))
    gender = str(case.get("gender", "unspecified"))
    hits = evaluate_shensha(chart, gender=gender)
    details: list[dict[str, object]] = []
    element_counts: Counter[str] = Counter()
    for position, pillar in zip(POSITIONS, chart.as_list(), strict=True):
        element_counts[pillar.stem.element] += 1
        element_counts[pillar.branch.element] += 1
        hidden_stems = [
            {"stem": stem.char, "ten_god": ten_god_of(chart.day_master, stem)}
            for stem in pillar.hidden_stems()
        ]
        details.append(
            {
                "position": position,
                "ganzhi": pillar.ganzhi,
                "stem": pillar.stem.char,
                "branch": pillar.branch.char,
                "major_star": (
                    "日主" if position == "day" else ten_god_of(chart.day_master, pillar.stem)
                ),
                "hidden_stems": hidden_stems,
                "nayin": pillar.nayin,
                "shensha": [hit.name for hit in hits if hit.target_position == position],
            }
        )
    return ChartResultDTO(
        chart_id=f"prompt-{case['id']}",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={},
        calendar={
            "deterministic_details": {
                "basic": {"gender": gender},
                "pillars": details,
                "five_elements": [
                    {"element": element, "total": element_counts[element]}
                    for element in ("wood", "fire", "earth", "metal", "water")
                ],
                "shensha": [
                    {
                        "name": hit.name,
                        "target_position": hit.target_position,
                        "variant": hit.variant,
                    }
                    for hit in hits
                ],
            }
        },
        pillars=[
            PillarDTO(
                position=position,  # type: ignore[arg-type]
                ganzhi=pillar.ganzhi,
                stem=pillar.stem.char,
                branch=pillar.branch.char,
            )
            for position, pillar in zip(POSITIONS, chart.as_list(), strict=True)
        ],
        day_master=chart.day_master.char,
        facts=[
            FactDTO(
                fact_id="FACT-DM-1",
                fact_type="day_master",
                value=chart.day_master.char,
                rule_id="RULE-DAY-MASTER",
            )
        ],
        engine_versions=[EngineVersionDTO(engine="golden", version="1", took_ms=0)],
        warnings=[],
    )


def test_prompt_projection_retains_twelve_example_pillars_shensha_and_relations() -> None:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for case in payload["cases"]:
        core = build_natal_core(_chart_dto(case), seasonal_strength={})
        pillars = [item["ganzhi"] for item in core["pillars"]]
        assert pillars == list(case["pillars"]), case["id"]

        shensha = {
            (item["name"], item.get("position", ""))
            for item in core.get("shensha", [])
        }
        for expected in case.get("required_shensha", []):
            assert tuple(expected) in shensha, (case["id"], expected, shensha)
        for forbidden in case.get("forbidden_shensha", []):
            assert tuple(forbidden) not in shensha, (case["id"], forbidden, shensha)

        relations = {
            (item["type"], tuple(item.get("participants", [])))
            for item in core["natal_relations"]
        }
        for relation_type, symbols in case.get("required_relations", []):
            expected = (str(relation_type), tuple(symbols))
            assert expected in relations, (case["id"], expected, relations)

        serialized = json.dumps(core, ensure_ascii=False)
        assert '"ten_god": ""' not in serialized, case["id"]
        assert "source_title" not in serialized, case["id"]
        assert "rule_id" not in serialized, case["id"]
