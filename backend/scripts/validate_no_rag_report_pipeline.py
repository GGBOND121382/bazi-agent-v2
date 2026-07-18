"""Generate twelve offline simulated reports and calibrated token estimates.

This is a validation harness, not a second production model. It uses the exact
production prompt/context/schema, simulates a conservative model response, runs
the production validator, and writes reviewable JSON/Markdown artifacts.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.adapters.llm import ProviderResponse  # noqa: E402
from app.api.dto import (  # noqa: E402
    BirthRequest,
    ChartResultDTO,
    EngineVersionDTO,
    FactDTO,
    PillarDTO,
)
from app.domain.pillars import Branch, FourPillars, Pillar, Stem, ten_god_of  # noqa: E402
from app.domain.rules.shensha import evaluate_shensha  # noqa: E402
from app.services.agent.professional_core import AnalysisPipeline  # noqa: E402
from app.services.chart_service import ChartService  # noqa: E402

POSITIONS = ("year", "month", "day", "hour")
ELEMENT_ZH = {"wood": "木", "fire": "火", "earth": "土", "metal": "金", "water": "水"}
GENERATED_BY = {"木": "水", "火": "木", "土": "火", "金": "土", "水": "金"}
CONTROLS = {"木": "土", "火": "金", "土": "水", "金": "木", "水": "火"}
SEASON = {
    "寅": ("春", "木"),
    "卯": ("春", "木"),
    "辰": ("春末", "土"),
    "巳": ("夏", "火"),
    "午": ("夏", "火"),
    "未": ("夏末", "土"),
    "申": ("秋", "金"),
    "酉": ("秋", "金"),
    "戌": ("秋末", "土"),
    "亥": ("冬", "水"),
    "子": ("冬", "水"),
    "丑": ("冬末", "土"),
}
RELATION_LABELS = {
    "stem_combination": "天干五合",
    "stem_clash": "天干相冲",
    "stem_control": "天干相克",
    "six_combination": "六合",
    "three_combination": "三合",
    "half_combination": "半合",
    "three_meeting": "三会",
    "half_meeting": "半会",
    "clash": "六冲",
    "harm": "六害",
    "break": "相破",
    "punishment": "相刑",
    "punishment_trigger": "两支刑触发",
    "hidden_combination": "暗合候选",
    "arching_combination": "拱合候选",
    "arching_meeting": "拱会候选",
    "covering": "盖头",
    "cut_foot": "截脚",
    "fuyin": "伏吟",
    "fanyin": "反吟候选",
    "four_tombs_earth_structure": "四库结构候选",
    "competing_combination": "争合候选",
    "branch_repeat": "地支同现",
    "stem_repeat": "天干同现",
}
# Calibrated from the user's latest real DeepSeek trace. These are estimates, not provider billing counts.
INPUT_CHARS_PER_TOKEN = 2.89
VISIBLE_OUTPUT_CHARS_PER_TOKEN = 1.55
REASONING_TO_VISIBLE_RATIO = 0.32


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    chart: ChartResultDTO
    prompt_payload: dict[str, Any]
    output: dict[str, Any]
    report: dict[str, Any]
    validation: dict[str, Any]
    metrics: dict[str, Any]


def _four_pillars(values: list[str]) -> FourPillars:
    return FourPillars(*[Pillar(Stem(value[0]), Branch(value[1])) for value in values])


def _manual_chart(case: dict[str, Any]) -> ChartResultDTO:
    pillars = _four_pillars(list(case["pillars"]))
    gender = str(case.get("gender", "unspecified"))
    hits = evaluate_shensha(pillars, gender=gender)
    details: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for position, pillar in zip(POSITIONS, pillars.as_list(), strict=True):
        counts[pillar.stem.element] += 1
        counts[pillar.branch.element] += 1
        for hidden in pillar.hidden_stems():
            counts[hidden.element] += 1
        details.append(
            {
                "position": position,
                "ganzhi": pillar.ganzhi,
                "stem": pillar.stem.char,
                "branch": pillar.branch.char,
                "major_star": "日主"
                if position == "day"
                else ten_god_of(pillars.day_master, pillar.stem),
                "hidden_stems": [
                    {"stem": stem.char, "ten_god": ten_god_of(pillars.day_master, stem)}
                    for stem in pillar.hidden_stems()
                ],
                "nayin": pillar.nayin,
                "five_elements": f"{ELEMENT_ZH[pillar.stem.element]}{ELEMENT_ZH[pillar.branch.element]}",
                "shensha": [hit.name for hit in hits if hit.target_position == position],
            }
        )
    facts = [
        FactDTO(
            fact_id=f"FACT-{position[0].upper()}-1",
            fact_type="pillar",
            value=pillar.ganzhi,
            rule_id=f"RULE-PILLAR-{position.upper()}",
        )
        for position, pillar in zip(POSITIONS, pillars.as_list(), strict=True)
    ]
    facts.append(
        FactDTO(
            fact_id="FACT-DM-1",
            fact_type="day_master",
            value=pillars.day_master.char,
            rule_id="RULE-DAY-MASTER",
        )
    )
    return ChartResultDTO(
        chart_id=f"chart_{case['id']}",
        calculation_status="passed",
        calculation_profile_id="ziping_standard_v1",
        normalized_time={},
        calendar={
            "deterministic_details": {
                "basic": {"gender": gender},
                "pillars": details,
                "five_elements": [
                    {"element": ELEMENT_ZH[element], "total": counts[element]}
                    for element in ("wood", "fire", "earth", "metal", "water")
                ],
                "shensha": [
                    {
                        "name": hit.name,
                        "target_position": hit.target_position,
                        "variant": hit.variant,
                        "rule_id": hit.rule_id,
                    }
                    for hit in hits
                ],
            }
        },
        pillars=[
            PillarDTO(
                position=position,
                ganzhi=pillar.ganzhi,
                stem=pillar.stem.char,
                branch=pillar.branch.char,
            )
            for position, pillar in zip(POSITIONS, pillars.as_list(), strict=True)
        ],
        day_master=pillars.day_master.char,
        facts=facts,
        engine_versions=[EngineVersionDTO(engine="golden", version="1", took_ms=0)],
        warnings=[],
    )


def _calculated_chart(case: dict[str, Any], service: ChartService) -> ChartResultDTO:
    birth = datetime.fromisoformat(str(case["birth"]))
    request = BirthRequest.model_validate(
        {
            "gender": case["gender"],
            "birth_datetime_local": birth.replace(tzinfo=None).isoformat(),
            "timezone": "Asia/Shanghai",
            "birthplace": {"country": "CN", "city": "Shanghai"},
            "calculation_profile_id": "ziping_standard_v1",
        }
    )
    chart, _, _ = service.create_chart(
        request=request,
        idempotency_key=f"offline-validation-{case['id']}",
        chart_id=f"chart_{case['id']}",
    )
    return chart


def _element_counts(natal: dict[str, Any]) -> dict[str, int]:
    return {
        str(item.get("element")): int(item.get("total", 0))
        for item in natal.get("five_elements", [])
        if isinstance(item, dict)
    }


def _strength(natal: dict[str, Any]) -> tuple[str, str, list[str], list[str]]:
    dm = Stem(str(natal["day_master"]))
    dm_element = ELEMENT_ZH[dm.element]
    month = next(item for item in natal["pillars"] if item["position"] == "month")
    season_name, season_element = SEASON[str(month["branch"])]
    counts = _element_counts(natal)
    support = counts.get(dm_element, 0) + counts.get(GENERATED_BY[dm_element], 0)
    other = sum(counts.values()) - support
    seasonal = (
        2
        if season_element == dm_element
        else 1
        if season_element == GENERATED_BY[dm_element]
        else -1
    )
    score = support - other * 0.55 + seasonal
    if score >= 4:
        label = "偏旺"
    elif score >= 1:
        label = "中和偏旺"
    elif score >= -2:
        label = "中和偏弱"
    else:
        label = "偏弱"
    supports = [
        f"同类与生扶元素合计约{support}份",
        f"月支处于{season_name}，当令五行为{season_element}",
    ]
    counters = [
        f"克泄耗及异类合计约{other}份",
        "该等级只是结构化模拟判断，正式结论仍需结合根气、制化与成局条件",
    ]
    return label, f"{season_name}{season_element}气主令", supports, counters


def _relation_text(relations: list[dict[str, Any]], limit: int = 5) -> str:
    parts: list[str] = []
    for item in relations[:limit]:
        label = RELATION_LABELS.get(str(item.get("type")), str(item.get("type")))
        participants = "、".join(str(value) for value in item.get("participants", []))
        suffix = (
            "（候选）" if "candidate" in str(item.get("variant", "")) or "候选" in label else ""
        )
        parts.append(f"{participants}{label}{suffix}" if participants else label)
    return "；".join(parts) or "未列出需重点解释的原局关系"


def _star_locations(natal: dict[str, Any], gods: set[str]) -> list[str]:
    result: list[str] = []
    for pillar in natal["pillars"]:
        position = str(pillar["position"])
        if pillar.get("major_star") in gods:
            result.append(f"{position}干{pillar['stem']}（{pillar['major_star']}）")
        for hidden in pillar.get("hidden_stems", []):
            if hidden.get("ten_god") in gods:
                result.append(
                    f"{position}支{pillar['branch']}藏{hidden['stem']}（{hidden['ten_god']}）"
                )
    return result


def _dayun_theme(item: dict[str, Any]) -> str:
    gods = {str(item.get("stem_ten_god", "")), str(item.get("branch_ten_god", ""))}
    career = (
        "责任、组织规则与能力输出并行"
        if gods & {"正官", "七杀", "正印", "偏印", "食神", "伤官"}
        else "以既有能力和环境适配为主"
    )
    wealth = (
        "财务机会与承载压力需同步评估"
        if gods & {"正财", "偏财", "食神", "伤官", "比肩", "劫财"}
        else "财务主题不是本运唯一主线"
    )
    relationship = (
        "关系议题会随财官与宫位触发而增强"
        if gods & {"正财", "偏财", "正官", "七杀", "比肩", "劫财"}
        else "关系变化更依赖具体流年触发"
    )
    return f"事业上{career}；财运上{wealth}；感情六亲方面{relationship}；健康只作传统五行偏性提示，重点是作息和压力管理。"


def _simulate_analysis(input_payload: dict[str, Any]) -> dict[str, Any]:
    context = cast(dict[str, Any], input_payload["analysis_context"])
    natal = cast(dict[str, Any], context["natal_core"])
    temporal = cast(dict[str, Any], context["temporal_hierarchy"])
    chart_id = str(input_payload["chart_id"])
    dm = str(natal["day_master"])
    pillars = cast(list[dict[str, Any]], natal["pillars"])
    month = next(item for item in pillars if item["position"] == "month")
    day = next(item for item in pillars if item["position"] == "day")
    gender = str(cast(dict[str, Any], natal.get("basic", {})).get("gender", "unspecified"))
    strength, seasonal, support, counter = _strength(natal)
    relations = cast(list[dict[str, Any]], natal.get("natal_relations", []))
    rel_text = _relation_text(relations)
    counts = _element_counts(natal)
    dominant = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    dominant_text = "、".join(f"{name}{value}" for name, value in dominant)
    dm_element = ELEMENT_ZH[Stem(dm).element]
    support_elements = [GENERATED_BY[dm_element], dm_element]
    control_target = CONTROLS[dm_element]
    pattern_candidate = str(month.get("major_star") or "月令结构")
    executive = (
        f"日主{dm}，四柱为{'、'.join(str(item['ganzhi']) for item in pillars)}。月支{month['branch']}处于{seasonal}，"
        f"五行分布为{dominant_text}，综合判为{strength}。分析以月令、根气和制化为主，"
        f"暂将{pattern_candidate}相关结构作为格局候选，不因单一关系或神煞直接定吉凶。"
    )
    reasoning = [
        {
            "dimension": "月令与日主强弱",
            "conclusion": f"{dm}日主在{month['branch']}月，综合得令、根气与五行配置判为{strength}。",
            "fact_ids": ["FACT-DM-1", "FACT-M-1"],
            "rule_ids": [],
            "evidence_ids": [],
            "counterpoints": counter,
            "confidence": 0.72,
        },
        {
            "dimension": "藏干与十神",
            "conclusion": "四柱透藏并见，需区分明透、藏根和受制状态；不能只按十神数量下结论。",
            "fact_ids": ["FACT-Y-1", "FACT-M-1", "FACT-D-1", "FACT-H-1"],
            "rule_ids": [],
            "evidence_ids": [],
            "counterpoints": ["部分作用是否成立仍取决于合冲后的有效性"],
            "confidence": 0.75,
        },
        {
            "dimension": "原局关系",
            "conclusion": f"确定性关系包括：{rel_text}。这些仅表示结构触发，需结合旺衰和制化解释。",
            "fact_ids": [str(item["fact_id"]) for item in relations[:4] if item.get("fact_id")]
            or ["FACT-D-1"],
            "rule_ids": [],
            "evidence_ids": [],
            "counterpoints": ["候选关系不等于已成局"],
            "confidence": 0.78,
        },
        {
            "dimension": "格局与喜用候选",
            "conclusion": f"以{pattern_candidate}相关结构起格，扶抑上先观察{support_elements[0]}、{support_elements[1]}的生扶，"
            f"同时检查{control_target}及其他克泄耗是否形成制化；调候优先级需结合季节另判。",
            "fact_ids": ["FACT-DM-1", "FACT-M-1"],
            "rule_ids": [],
            "evidence_ids": [],
            "counterpoints": ["这只是模拟解释，不强定唯一用神"],
            "confidence": 0.65,
        },
    ]
    structure = {
        "day_master_strength": strength,
        "seasonal_state": seasonal,
        "supporting_factors": support,
        "counter_factors": counter,
        "pattern_candidate": f"{pattern_candidate}相关结构候选",
        "useful_element_candidates": support_elements,
        "climate_adjustment": "寒局重温养、热局重润燥，土旺季节兼顾疏通；具体取用不作机械补缺。",
        "key_relations": rel_text,
        "nayin_and_shensha": "纳音与神煞仅作为辅助层，不覆盖月令、十神和干支生克。",
    }

    spouse_gods = {"正财", "偏财"} if gender == "male" else {"正官", "七杀"}
    kinship = [
        {
            "relation": "父亲",
            "analysis": "父亲专题结合财星、年柱父母宫及后续岁运共同判断；当前只说明星宫状态，不由单一藏干推出现实事件。",
            "confidence": 0.62,
        },
        {
            "relation": "母亲",
            "analysis": f"母亲专题结合印星与年柱父母宫观察，印星位置包括：{'；'.join(_star_locations(natal, {'正印', '偏印'})) or '未明显列出'}。",
            "confidence": 0.68,
        },
        {
            "relation": "兄弟姐妹",
            "analysis": f"兄弟姐妹专题结合比劫及月柱环境观察，比劫位置包括：{'；'.join(_star_locations(natal, {'比肩', '劫财'})) or '未明显列出'}；数量和亲疏不能仅凭此确定。",
            "confidence": 0.64,
        },
        {
            "relation": "配偶婚恋",
            "analysis": f"夫妻宫为日支{day['branch']}；配偶/情缘星位置包括：{'；'.join(_star_locations(natal, spouse_gods)) or '未明显列出'}。应结合夫妻宫与岁运共同触发，不把受冲受合直接等同婚变或婚成。",
            "confidence": 0.7,
        },
        {
            "relation": "子女",
            "analysis": "子女专题以时柱子女宫、相关十神及岁运共同观察；本报告不由单一食伤或官杀直接推断子女数量与健康。",
            "confidence": 0.6,
        },
        {
            "relation": "家庭互动",
            "analysis": "家庭互动受年、月、日、时四宫位及原局关系共同影响；建议将关系结构理解为沟通模式和责任分配倾向。",
            "confidence": 0.65,
        },
    ]

    climate = SEASON[str(month["branch"])][0]
    health = [
        {
            "dimension": "五行偏性",
            "analysis": f"五行统计为{dominant_text}；偏多偏少只代表传统结构倾向，不等同医学结论。",
            "confidence": 0.75,
        },
        {
            "dimension": "寒暖燥湿",
            "analysis": f"月令处于{climate}，需结合全局火水、燥湿和调候关系理解体感与作息倾向。",
            "confidence": 0.7,
        },
        {
            "dimension": "传统脏腑象义",
            "analysis": "传统象义可用于提示关注方向，但不能据此诊断具体疾病；不适应症应以正规医学检查为准。",
            "confidence": 0.55,
        },
        {
            "dimension": "保护因素",
            "analysis": f"生扶候选元素为{support_elements[0]}、{support_elements[1]}，原局贵人类神煞仅可作为辅助，不代表风险自动消失。",
            "confidence": 0.62,
        },
        {
            "dimension": "大运变化",
            "analysis": "每步大运对寒暖燥湿和五行流通的影响已在生命周期部分逐项说明；流年流月只作为进一步触发层。",
            "confidence": 0.66,
        },
        {
            "dimension": "生活建议",
            "analysis": "保持规律作息、适量运动和稳定饮食；避免把传统命理倾向替代专业健康评估。",
            "confidence": 0.8,
        },
    ]

    dayun_sequence = cast(list[dict[str, Any]], temporal.get("dayun_sequence", []))
    dayun_assessment: list[dict[str, Any]] = []
    qiyun = cast(dict[str, Any], temporal.get("qiyun", {}))
    if dayun_sequence:
        start = qiyun.get("start_datetime") or qiyun.get("start_age_years") or "已提供"
        dayun_assessment.append(
            {
                "stage": "出生至起运",
                "analysis": f"起运信息为{start}。此阶段以原局和成长环境为主，后续进入第一步大运后长期主题逐渐显化。",
                "fact_ids": [],
                "rule_ids": [],
                "evidence_ids": [],
                "coverage_status": "interpreted",
            }
        )
        for item in dayun_sequence:
            interactions = cast(list[dict[str, Any]], item.get("natal_interactions", []))
            interaction_text = _relation_text(interactions, limit=3)
            dayun_assessment.append(
                {
                    "stage": f"{item.get('ganzhi')}大运（{item.get('start_year')}—{item.get('end_year')}，{item.get('start_age')}—{item.get('end_age')}岁）",
                    "analysis": f"天干十神为{item.get('stem_ten_god', '未列')}，地支主气十神为{item.get('branch_ten_god', '未列')}，"
                    f"藏干为{'、'.join(str(x.get('stem')) for x in item.get('hidden_stems', [])) or '未列'}。"
                    f"与原局的重点关系为{interaction_text}。{_dayun_theme(item)}承接下一运时应关注五行主导权是否转换。",
                    "fact_ids": [str(item["fact_id"])] if item.get("fact_id") else [],
                    "rule_ids": [],
                    "evidence_ids": [],
                    "coverage_status": "interpreted",
                }
            )
    else:
        dayun_assessment.append(
            {
                "stage": "大运资料不可用",
                "analysis": "该样例只有四柱，没有足以复算起运与大运的出生日期；本报告不虚构生命周期结论。",
                "fact_ids": [],
                "rule_ids": [],
                "evidence_ids": [],
                "coverage_status": "unavailable",
            }
        )

    temporal_assessment = [
        {"period": item["stage"], "summary": item["analysis"], "fact_ids": item.get("fact_ids", [])}
        for item in dayun_assessment[:4]
    ]
    base_facts = ["FACT-DM-1", "FACT-M-1"]
    relation_fact_ids = [str(item["fact_id"]) for item in relations[:2] if item.get("fact_id")]
    claims = [
        {
            "claim_id": "CL-001",
            "topic": "原局",
            "statement": f"日主为{dm}，月支为{month['branch']}，强弱模拟结论为{strength}。",
            "fact_ids": base_facts,
            "rule_ids": [],
            "evidence_ids": [],
            "counterevidence": counter,
            "confidence": 0.72,
            "temporal_scope": "原局",
        },
        {
            "claim_id": "CL-002",
            "topic": "五行",
            "statement": f"确定性五行统计为{dominant_text}，解释时需结合月令和制化。",
            "fact_ids": base_facts,
            "rule_ids": [],
            "evidence_ids": [],
            "counterevidence": [],
            "confidence": 0.78,
            "temporal_scope": "原局",
        },
        {
            "claim_id": "CL-003",
            "topic": "关系",
            "statement": f"原局已确定的重点关系包括：{rel_text}；关系命中本身不等于现实事件。",
            "fact_ids": relation_fact_ids or ["FACT-D-1"],
            "rule_ids": [],
            "evidence_ids": [],
            "counterevidence": ["候选关系需核验成局与救应"],
            "confidence": 0.76,
            "temporal_scope": "原局",
        },
    ]
    if dayun_sequence:
        claims.append(
            {
                "claim_id": "CL-004",
                "topic": "大运",
                "statement": f"生命周期分析按确定性顺序覆盖{len(dayun_sequence)}步大运，并保留出生至起运阶段。",
                "fact_ids": [str(dayun_sequence[0]["fact_id"])],
                "rule_ids": [],
                "evidence_ids": [],
                "counterevidence": [],
                "confidence": 0.9,
                "temporal_scope": "生命周期",
            }
        )

    limitations = [
        "这是离线模拟模型输出，用于验证 Prompt 信息量和校验流程，不代替真实 DeepSeek 调用。"
    ]
    if not dayun_sequence:
        limitations.append("缺少完整出生日期，无法核验起运和大运，只分析原局。")
    return {
        "schema_version": "analysis-output-v1",
        "analysis_id": f"{chart_id}_analysis",
        "chart_id": chart_id,
        "school": "engineering_policy",
        "executive_summary": executive,
        "reasoning_summary": reasoning,
        "structure_assessment": structure,
        "temporal_assessment": temporal_assessment,
        "kinship_assessment": kinship,
        "health_assessment": health,
        "dayun_assessment": dayun_assessment,
        "claims": claims,
        "limitations": limitations,
    }


class SimulatedProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        payload = _simulate_analysis(cast(dict[str, Any], kwargs["input_payload"]))
        self.calls.append(
            {
                "system_prompt": kwargs["system_prompt"],
                "input_payload": kwargs["input_payload"],
                "schema": kwargs["schema"],
                "output": payload,
            }
        )
        return ProviderResponse(
            payload=payload,
            model_id="offline-simulated-llm",
            prompt_version=kwargs["prompt_version"],
            streamed=False,
        )


class RepairProbeProvider:
    """Inject one deterministic fact error, then repair only the allowed JSON block."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.correct_output: dict[str, Any] | None = None

    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        schema = cast(dict[str, Any], kwargs["schema"])
        input_payload = cast(dict[str, Any], kwargs["input_payload"])
        payload: dict[str, Any]
        if schema.get("$id") == "analysis-json-patch-v2":
            if self.correct_output is None:
                raise RuntimeError("repair probe did not retain the primary output")
            path = str(input_payload["allowed_paths"][0])
            value: Any = self.correct_output
            for part in (item for item in path.split("/") if item):
                value = value[int(part)] if isinstance(value, list) else value[part]
            payload = {
                "schema_version": "analysis-json-patch-v2",
                "operations": [{"op": "replace", "path": path, "value": value}],
                "repair_summary": "按确定性十神、藏干与五行关系修复单个六亲块",
            }
        else:
            self.correct_output = _simulate_analysis(input_payload)
            payload = copy.deepcopy(self.correct_output)
            payload["kinship_assessment"][1]["analysis"] = (
                "母亲星乙为正印，辛藏于申，且土克木，因此母亲专题按该结构判断。"
            )
        self.calls.append(
            {
                "system_prompt": kwargs["system_prompt"],
                "input_payload": input_payload,
                "schema": schema,
                "output": payload,
            }
        )
        return ProviderResponse(
            payload=payload,
            model_id="offline-repair-probe",
            prompt_version=kwargs["prompt_version"],
            streamed=False,
        )


def _estimate_metrics(call: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    request_text = json.dumps(
        {"input": call["input_payload"], "required_schema": call["schema"]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    input_chars = len(call["system_prompt"]) + len(request_text)
    output_text = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    output_chars = len(output_text)
    input_tokens = math.ceil(input_chars / INPUT_CHARS_PER_TOKEN)
    visible_tokens = math.ceil(output_chars / VISIBLE_OUTPUT_CHARS_PER_TOKEN)
    reasoning_tokens = math.ceil(visible_tokens * REASONING_TO_VISIBLE_RATIO)
    return {
        "input_chars": input_chars,
        "output_chars": output_chars,
        "estimated_input_tokens": input_tokens,
        "estimated_visible_output_tokens": visible_tokens,
        "estimated_reasoning_tokens": reasoning_tokens,
        "estimated_completion_tokens": visible_tokens + reasoning_tokens,
        "estimated_total_tokens": input_tokens + visible_tokens + reasoning_tokens,
        "estimate_method": "calibrated_from_latest_real_deepseek_trace",
        "estimate_uncertainty": "±15%; not provider billing counts",
    }


def _markdown(case: dict[str, Any], result: CaseResult) -> str:
    a = result.output
    lines = [
        f"# {case['id']} 模拟完整报告",
        "",
        f"- 四柱：{' '.join(case['pillars'])}",
        f"- 性别：{case.get('gender')}",
        f"- 出生时间：{case.get('birth', '未提供，仅原局')}",
        f"- 校验：{result.validation['status']}",
        f"- 估算总 token：{result.metrics['estimated_total_tokens']:,}",
        "",
        "## 总论",
        "",
        str(a.get("executive_summary", "")),
        "",
        "## 结构分析",
        "",
    ]
    for item in a.get("reasoning_summary", []):
        lines.append(f"### {item['dimension']}")
        lines.append("")
        lines.append(str(item["conclusion"]))
        if item.get("counterpoints"):
            lines.append("")
            lines.append("反向因素：" + "；".join(item["counterpoints"]))
        lines.append("")
    lines.extend(["## 六亲", ""])
    for item in a.get("kinship_assessment", []):
        lines.append(f"- **{item.get('relation')}**：{item.get('analysis')}")
    lines.extend(["", "## 健康（传统倾向）", ""])
    for item in a.get("health_assessment", []):
        lines.append(f"- **{item.get('dimension')}**：{item.get('analysis')}")
    lines.extend(["", "## 大运生命周期", ""])
    for item in a.get("dayun_assessment", []):
        lines.append(f"### {item.get('stage')}")
        lines.append("")
        lines.append(str(item.get("analysis", "")))
        lines.append("")
    lines.extend(["## 局限", ""])
    for item in a.get("limitations", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


def main() -> None:  # noqa: PLR0915
    output_dir = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "no_rag_validation"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    golden = json.loads(
        (ROOT / "backend/tests/golden/wenzhen_compatibility_v1.json").read_text(encoding="utf-8")
    )
    service = ChartService()
    results: list[CaseResult] = []
    for case in golden["cases"]:
        chart = _calculated_chart(case, service) if case.get("birth") else _manual_chart(case)
        assert [item.ganzhi for item in chart.pillars] == list(case["pillars"]), case["id"]
        provider = SimulatedProvider()
        pipeline_result = AnalysisPipeline(provider=provider).run(
            chart=chart,
            user_focus=("完整命造、六亲、健康与大运生命周期",),
            max_revisions=0,
        )
        if pipeline_result.report is None:
            raise RuntimeError(
                f"{case['id']} failed: {pipeline_result.validation.model_dump(mode='json')}"
            )
        call = provider.calls[0]
        metrics = _estimate_metrics(call, pipeline_result.analysis.model_dump(mode="json"))
        result = CaseResult(
            case_id=str(case["id"]),
            chart=chart,
            prompt_payload=call["input_payload"],
            output=pipeline_result.analysis.model_dump(mode="json"),
            report=pipeline_result.report,
            validation=pipeline_result.validation.model_dump(mode="json"),
            metrics=metrics,
        )
        results.append(result)
        case_dir = output_dir / str(case["id"])
        case_dir.mkdir(exist_ok=True)
        (case_dir / "prompt.json").write_text(
            json.dumps(
                {
                    "system_prompt": call["system_prompt"],
                    "input_payload": call["input_payload"],
                    "required_schema": call["schema"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (case_dir / "model_output.json").write_text(
            json.dumps(result.output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (case_dir / "validation.json").write_text(
            json.dumps(result.validation, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (case_dir / "report.md").write_text(_markdown(case, result), encoding="utf-8")

    probe_case = next(case for case in golden["cases"] if case["id"] == "case-01-1995")
    probe_chart = _calculated_chart(probe_case, service)
    probe_provider = RepairProbeProvider()
    probe_result = AnalysisPipeline(provider=probe_provider).run(
        chart=probe_chart,
        user_focus=("完整命造、六亲、健康与大运生命周期",),
        max_revisions=1,
    )
    if probe_result.report is None or probe_result.validation.status != "passed":
        raise RuntimeError("minimal local repair probe failed")
    if len(probe_provider.calls) != 2:
        raise RuntimeError("minimal local repair probe did not execute exactly two model calls")
    probe_main_metrics = _estimate_metrics(
        probe_provider.calls[0], cast(dict[str, Any], probe_provider.calls[0]["output"])
    )
    probe_repair_metrics = _estimate_metrics(
        probe_provider.calls[1], cast(dict[str, Any], probe_provider.calls[1]["output"])
    )
    main_payload_chars = len(
        json.dumps(
            probe_provider.calls[0]["input_payload"],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    repair_payload_chars = len(
        json.dumps(
            probe_provider.calls[1]["input_payload"],
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    repair_probe: dict[str, Any] = {
        "validation_status": probe_result.validation.status,
        "model_calls": 2,
        "allowed_paths": probe_provider.calls[1]["input_payload"]["allowed_paths"],
        "main_call": probe_main_metrics,
        "local_repair_call": probe_repair_metrics,
        "repair_input_to_main_input_ratio": round(repair_payload_chars / main_payload_chars, 4),
        "combined_estimated_total_tokens": (
            int(probe_main_metrics["estimated_total_tokens"])
            + int(probe_repair_metrics["estimated_total_tokens"])
        ),
    }
    probe_dir = output_dir / "repair-probe-case-01"
    probe_dir.mkdir(exist_ok=True)
    for index, call in enumerate(probe_provider.calls, start=1):
        (probe_dir / f"call-{index}-prompt.json").write_text(
            json.dumps(
                {
                    "system_prompt": call["system_prompt"],
                    "input_payload": call["input_payload"],
                    "required_schema": call["schema"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (probe_dir / f"call-{index}-raw-output.json").write_text(
            json.dumps(call["output"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (probe_dir / "result.json").write_text(
        json.dumps(repair_probe, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    case_metrics: list[dict[str, Any]] = [
        {
            "id": item.case_id,
            "pillars": [pillar.ganzhi for pillar in item.chart.pillars],
            "dayun_count": len(item.chart.dayun or []),
            "validation_status": item.validation["status"],
            **item.metrics,
        }
        for item in results
    ]
    totals = [int(item.metrics["estimated_total_tokens"]) for item in results]
    aggregate: dict[str, Any] = {
        "case_count": len(results),
        "all_passed": all(item.validation["status"] == "passed" for item in results),
        "min_total_tokens": min(totals),
        "max_total_tokens": max(totals),
        "mean_total_tokens": round(sum(totals) / len(totals), 1),
        "sum_total_tokens": sum(totals),
    }
    summary: dict[str, Any] = {
        "schema_version": "no-rag-report-validation-v1",
        "simulation_notice": "Offline simulated model outputs; token counts are calibrated estimates, not actual DeepSeek billing counts.",
        "calibration": {
            "input_chars_per_token": INPUT_CHARS_PER_TOKEN,
            "visible_output_chars_per_token": VISIBLE_OUTPUT_CHARS_PER_TOKEN,
            "reasoning_to_visible_ratio": REASONING_TO_VISIBLE_RATIO,
        },
        "cases": case_metrics,
        "aggregate": aggregate,
        "repair_probe": repair_probe,
    }
    (output_dir / "token_metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    table = [
        "# 去 RAG 后 12 命造报告验证与 Token 统计",
        "",
        "> 说明：报告由离线模拟模型生成；token 使用最新真实 DeepSeek 日志校准估算，误差约 ±15%，不是 API 实际计费数。",
        "",
        "| 命造 | 大运数 | 输入估算 | 可见输出 | 推理估算 | 总计 | 校验 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in case_metrics:
        table.append(
            f"| {item['id']} | {item['dayun_count']} | {item['estimated_input_tokens']:,} | "
            f"{item['estimated_visible_output_tokens']:,} | {item['estimated_reasoning_tokens']:,} | "
            f"{item['estimated_total_tokens']:,} | {item['validation_status']} |"
        )
    agg = aggregate
    table.extend(
        [
            "",
            "## 汇总",
            "",
            f"- 12/12 校验通过：{agg['all_passed']}",
            f"- 单份最小：{agg['min_total_tokens']:,} token",
            f"- 单份最大：{agg['max_total_tokens']:,} token",
            f"- 单份平均：{agg['mean_total_tokens']:,.1f} token",
            f"- 12 份合计：{agg['sum_total_tokens']:,} token",
        ]
    )
    table.extend(
        [
            "",
            "## 最小局部修复探针",
            "",
            f"- 允许修改路径：{', '.join(repair_probe['allowed_paths'])}",
            f"- 局部修复输入约为主输入的：{repair_probe['repair_input_to_main_input_ratio']:.2%}",
            f"- 局部修复调用估算：{repair_probe['local_repair_call']['estimated_total_tokens']:,} token",
            f"- 主调用加一次局部修复：{repair_probe['combined_estimated_total_tokens']:,} token",
            f"- 最终校验：{repair_probe['validation_status']}",
        ]
    )
    (output_dir / "SUMMARY.md").write_text("\n".join(table), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
