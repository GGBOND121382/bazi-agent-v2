"""Compact, scope-aware context projection for fortune chat prompts.

The deterministic engine keeps the complete chart/temporal snapshot.  This
module projects that snapshot into one non-duplicated model context while
preserving the mandatory hierarchy:

    natal -> dayun -> liunian -> liuyue -> liuri

Only levels below the requested scope are omitted.  Audit/provenance metadata
stays in the generation trace instead of consuming model context.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, cast

from ..api.dto import ChartResultDTO, TemporalContextViewDTO
from ..domain.pillars import Branch, FourPillars, Pillar, Stem
from ..domain.profile import load_profile
from ..domain.rules import evaluate_relations
from ..domain.rules.relations import RuleProfile

ChatTopic = Literal["relationship", "wealth", "career", "health", "kinship", "general"]
ChatScopeName = Literal["general", "dayun", "lifecycle", "year", "month", "day"]
PillarPosition = Literal["year", "month", "day", "hour"]
_TOPIC_ORDER: tuple[ChatTopic, ...] = (
    "relationship",
    "wealth",
    "career",
    "health",
    "kinship",
)

_TOPIC_KEYWORDS: dict[ChatTopic, tuple[str, ...]] = {
    "relationship": (
        "感情",
        "情感",
        "爱情",
        "婚姻",
        "婚恋",
        "恋爱",
        "桃花",
        "姻缘",
        "配偶",
        "对象",
        "正缘",
        "丈夫",
        "妻子",
    ),
    "wealth": ("财运", "财富", "收入", "赚钱", "钱财", "投资", "破财", "薪资", "资产"),
    "career": ("事业", "工作", "职业", "升职", "晋升", "跳槽", "创业", "学业", "考试"),
    "health": ("健康", "身体", "疾病", "生病", "体质", "脏腑", "手术", "伤病"),
    "kinship": (
        "父亲",
        "母亲",
        "父母",
        "兄弟",
        "姐妹",
        "子女",
        "孩子",
        "家庭",
        "六亲",
        "丈夫",
        "妻子",
    ),
    "general": (),
}

_RELATIONSHIP_SHENSHA = frozenset(
    {"桃花", "咸池", "红鸾", "天喜", "孤辰", "寡宿", "阴阳差错", "童子煞"}
)
_HEALTH_SHENSHA = frozenset(
    {"天医", "羊刃", "阳刃", "飞刃", "血刃", "流霞", "天罗", "地网", "灾煞"}
)
_CAREER_SHENSHA = frozenset(
    {"将星", "国印贵人", "文昌贵人", "学堂", "词馆", "天乙贵人", "太极贵人"}
)
_WEALTH_SHENSHA = frozenset({"禄神", "金舆", "驿马", "天乙贵人"})
_RELATION_LABELS = {
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
    "fuyin": "伏吟（同柱）",
    "fanyin": "反吟候选",
    "four_tombs_earth_structure": "四库齐全（土局候选）",
    "competing_combination": "争合/妒合候选",
}


def detect_chat_topics(question: str) -> tuple[ChatTopic, ...]:
    """Return all explicit topics, preserving a deterministic priority order."""
    text = question.strip()
    detected = tuple(
        topic
        for topic in _TOPIC_ORDER
        if any(keyword in text for keyword in _TOPIC_KEYWORDS[topic])
    )
    return detected or ("general",)


def topic_label(topics: Sequence[ChatTopic]) -> str:
    labels = {
        "relationship": "感情婚恋",
        "wealth": "财运",
        "career": "事业学业",
        "health": "健康",
        "kinship": "六亲家庭",
        "general": "综合运势",
    }
    return "、".join(labels[item] for item in topics)


def _nonempty_string(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _compact_hidden_stems(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stem = _nonempty_string(item.get("stem"))
        if not stem:
            continue
        compact = {"stem": stem}
        ten_god = _nonempty_string(item.get("ten_god"))
        if ten_god:
            compact["ten_god"] = ten_god
        result.append(compact)
    return result


def _compact_shensha(raw: object) -> list[dict[str, str]]:
    """Keep model-relevant identity/position, not audit source metadata."""
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            position = ""
            variant = ""
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            position = str(item.get("target_position", "")).strip()
            variant = str(item.get("variant", "")).strip()
        else:
            continue
        if not name:
            continue
        key = (name, position, variant)
        if key in seen:
            continue
        seen.add(key)
        compact = {"name": name}
        if position:
            compact["position"] = position
        if variant and variant != "classical_or_common":
            compact["variant"] = variant
        result.append(compact)
    return result


def _compact_participant_positions(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        position = _nonempty_string(item.get("position"))
        if not position:
            continue
        compact = {"position": position}
        ganzhi = _nonempty_string(item.get("ganzhi"))
        if ganzhi:
            compact["ganzhi"] = ganzhi
        result.append(compact)
    return result


def compact_relation(raw: Mapping[str, object]) -> dict[str, object]:
    """Compact a deterministic relation without losing interpretive semantics."""
    compact: dict[str, object] = {
        "type": str(raw.get("type", "")),
        "label": str(raw.get("label", raw.get("type", ""))),
    }
    participants = raw.get("participants")
    if not isinstance(participants, list):
        participants = raw.get("branches")
    if isinstance(participants, (list, tuple)) and participants:
        compact["participants"] = [str(item) for item in participants]

    positions = _compact_participant_positions(raw.get("participant_positions"))
    if positions:
        compact["positions"] = positions
    else:
        raw_positions = raw.get("positions")
        if isinstance(raw_positions, (list, tuple)) and raw_positions:
            compact["positions"] = [str(item) for item in raw_positions]

    for key in ("element", "direction", "attention", "variant"):
        value = _nonempty_string(raw.get(key))
        if value:
            compact[key] = value
    basis = raw.get("basis")
    if isinstance(basis, (list, tuple)) and basis:
        compact["basis"] = [str(item) for item in basis]
    return compact


def _compact_relations(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [compact_relation(cast(dict[str, object], item)) for item in raw if isinstance(item, dict)]


def _compact_temporal_pillar(raw: Mapping[str, object]) -> dict[str, object]:
    """Project one dayun/year/month/day object into a model-facing form."""
    compact: dict[str, object] = {}
    scalar_keys = (
        "index",
        "start_year",
        "end_year",
        "start_age",
        "end_age",
        "year",
        "civil_target_year",
        "lichun_year",
        "age",
        "date",
        "lunar_date",
        "label",
        "jie_name",
        "start_datetime",
        "end_datetime",
        "month_ganzhi",
        "ganzhi",
        "stem",
        "branch",
        "stem_ten_god",
        "branch_ten_god",
        "growth_stage",
        "self_seat",
        "nayin",
        "xunkong",
        "xiaoyun",
    )
    for key in scalar_keys:
        value = raw.get(key)
        if value is not None and value != "":
            compact[key] = value

    hidden_stems = _compact_hidden_stems(raw.get("hidden_stems"))
    if hidden_stems:
        compact["hidden_stems"] = hidden_stems
    shensha = _compact_shensha(raw.get("shensha"))
    if shensha:
        compact["shensha"] = shensha

    natal_relations = _compact_relations(raw.get("relations"))
    if natal_relations:
        compact["natal_interactions"] = natal_relations
    cross_layer = _compact_relations(raw.get("temporal_interactions"))
    if cross_layer:
        compact["cross_layer_interactions"] = cross_layer
    return compact


def _compact_dayun_summary(raw: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "index",
        "start_year",
        "end_year",
        "start_age",
        "end_age",
        "ganzhi",
        "stem_ten_god",
        "branch_ten_god",
        "growth_stage",
    )
    return {key: raw[key] for key in keys if raw.get(key) is not None and raw.get(key) != ""}


def _natal_four_pillars(chart: ChartResultDTO) -> FourPillars | None:
    by_position = {item.position: item for item in chart.pillars}
    if not all(position in by_position for position in ("year", "month", "day", "hour")):
        return None

    def pillar(position: PillarPosition) -> Pillar:
        item = by_position[position]
        return Pillar(Stem(item.stem), Branch(item.branch))

    return FourPillars(
        year=pillar("year"),
        month=pillar("month"),
        day=pillar("day"),
        hour=pillar("hour"),
    )


def _compact_natal_relations(chart: ChartResultDTO) -> list[dict[str, object]]:
    pillars = _natal_four_pillars(chart)
    if pillars is None:
        return []
    profile = load_profile()
    relations = evaluate_relations(
        pillars,
        rule_profile=cast(RuleProfile, profile.relation_rule_profile),
    )
    result: list[dict[str, object]] = []
    for item in relations:
        raw: dict[str, object] = {
            "type": item.type,
            "label": _RELATION_LABELS.get(item.type, item.type),
            "participants": list(item.branches),
            "positions": list(item.positions),
            "element": item.element,
            "direction": item.direction,
            "basis": list(item.basis),
            "variant": item.variant,
        }
        result.append(compact_relation(raw))
    return result


def _detail_pillars(details: Mapping[str, object]) -> list[dict[str, object]]:
    raw = details.get("pillars")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        compact: dict[str, object] = {}
        for key in (
            "position",
            "ganzhi",
            "stem",
            "branch",
            "major_star",
            "growth_stage",
            "self_seat",
            "void",
            "nayin",
            "five_elements",
        ):
            value = item.get(key)
            if value is not None and value != "":
                compact[key] = value
        hidden_stems = _compact_hidden_stems(item.get("hidden_stems"))
        if hidden_stems:
            compact["hidden_stems"] = hidden_stems
        raw_shensha = item.get("shensha")
        if isinstance(raw_shensha, list) and raw_shensha:
            compact["shensha"] = [str(value) for value in raw_shensha if str(value).strip()]
        result.append(compact)
    return result


def build_natal_core(
    chart: ChartResultDTO,
    *,
    seasonal_strength: Mapping[str, object],
) -> dict[str, object]:
    details_raw = chart.calendar.get("deterministic_details", {})
    details = cast(dict[str, object], details_raw) if isinstance(details_raw, dict) else {}
    basic_raw = details.get("basic")
    basic = cast(dict[str, object], basic_raw) if isinstance(basic_raw, dict) else {}
    compact_basic: dict[str, object] = {}
    for key in (
        "gender",
        "birth_datetime_local",
        "calculation_time",
        "time_basis",
        "ren_yuan_commander",
        "birth_solar_terms",
    ):
        value = basic.get(key)
        if value is not None and value != "":
            compact_basic[key] = value

    pillars = _detail_pillars(details)
    if not pillars:
        pillars = [
            {
                key: value
                for key, value in item.model_dump(mode="json").items()
                if value not in (None, "", [])
            }
            for item in chart.pillars
        ]

    core: dict[str, object] = {
        "day_master": chart.day_master,
        "pillars": pillars,
        "natal_relations": _compact_natal_relations(chart),
    }
    if compact_basic:
        core["basic"] = compact_basic
    five_elements = details.get("five_elements")
    if isinstance(five_elements, list) and five_elements:
        core["five_elements"] = five_elements
    if seasonal_strength:
        core["seasonal_strength"] = dict(seasonal_strength)
    shensha = _compact_shensha(details.get("shensha"))
    if shensha:
        core["shensha"] = shensha
    return core


def _ten_god_locations(pillars: object, target_names: set[str]) -> list[dict[str, str]]:
    if not isinstance(pillars, list):
        return []
    result: list[dict[str, str]] = []
    for pillar in pillars:
        if not isinstance(pillar, dict):
            continue
        position = str(pillar.get("position", ""))
        major = str(pillar.get("major_star", ""))
        if major in target_names:
            result.append({"position": position, "source": "stem", "ten_god": major})
        hidden = pillar.get("hidden_stems")
        if not isinstance(hidden, list):
            continue
        for item in hidden:
            if not isinstance(item, dict):
                continue
            ten_god = str(item.get("ten_god", ""))
            if ten_god in target_names:
                result.append(
                    {
                        "position": position,
                        "source": "hidden_stem",
                        "stem": str(item.get("stem", "")),
                        "ten_god": ten_god,
                    }
                )
    return result


def _topic_shensha(natal_core: Mapping[str, object], names: frozenset[str]) -> list[dict[str, str]]:
    raw = natal_core.get("shensha")
    if not isinstance(raw, list):
        return []
    return [
        cast(dict[str, str], item)
        for item in raw
        if isinstance(item, dict) and str(item.get("name", "")) in names
    ]


def build_topic_context(
    natal_core: Mapping[str, object],
    topics: Sequence[ChatTopic],
) -> dict[str, object]:
    context: dict[str, object] = {"topics": list(topics)}
    pillars = natal_core.get("pillars")
    basic = natal_core.get("basic")
    gender = str(basic.get("gender", "unspecified")) if isinstance(basic, dict) else "unspecified"

    if "relationship" in topics:
        primary = "正财" if gender == "male" else "正官" if gender == "female" else "配偶星"
        secondary = "偏财" if gender == "male" else "七杀" if gender == "female" else "情缘星"
        day_pillar = next(
            (
                cast(dict[str, object], item)
                for item in pillars
                if isinstance(item, dict) and item.get("position") == "day"
            ),
            {},
        ) if isinstance(pillars, list) else {}
        natal_relations = natal_core.get("natal_relations")
        spouse_palace_relations = [
            cast(dict[str, object], relation)
            for relation in natal_relations
            if isinstance(relation, dict)
            and isinstance(relation.get("positions"), list)
            and "day" in relation["positions"]
        ] if isinstance(natal_relations, list) else []
        context["relationship"] = {
            "gender": gender,
            "primary_spouse_star": primary,
            "secondary_relationship_star": secondary,
            "spouse_star_locations": _ten_god_locations(pillars, {primary, secondary}),
            "spouse_palace": {
                key: day_pillar[key]
                for key in ("ganzhi", "branch", "hidden_stems", "void", "self_seat")
                if key in day_pillar
            }
            | {"relations": spouse_palace_relations},
            "relevant_shensha": _topic_shensha(natal_core, _RELATIONSHIP_SHENSHA),
        }
    if "wealth" in topics:
        context["wealth"] = {
            "wealth_star_locations": _ten_god_locations(pillars, {"正财", "偏财"}),
            "source_star_locations": _ten_god_locations(pillars, {"食神", "伤官"}),
            "relevant_shensha": _topic_shensha(natal_core, _WEALTH_SHENSHA),
        }
    if "career" in topics:
        context["career"] = {
            "authority_star_locations": _ten_god_locations(pillars, {"正官", "七杀"}),
            "support_star_locations": _ten_god_locations(pillars, {"正印", "偏印"}),
            "output_star_locations": _ten_god_locations(pillars, {"食神", "伤官"}),
            "relevant_shensha": _topic_shensha(natal_core, _CAREER_SHENSHA),
        }
    if "health" in topics:
        context["health"] = {
            "focus_paths": [
                "natal_core.five_elements",
                "natal_core.seasonal_strength",
                "natal_core.basic.ren_yuan_commander",
                "temporal_hierarchy",
            ],
            "relevant_shensha": _topic_shensha(natal_core, _HEALTH_SHENSHA),
        }
    if "kinship" in topics:
        context["kinship"] = {
            "gender": gender,
            "ten_god_locations": _ten_god_locations(
                pillars,
                {"正印", "偏印", "正财", "偏财", "比肩", "劫财", "食神", "伤官", "正官", "七杀"},
            ),
            "palace_positions": {
                "ancestors_parents": ["year", "month"],
                "self_spouse": ["day"],
                "children_later_life": ["hour"],
            },
        }
    return context


def build_temporal_hierarchy(
    temporal: TemporalContextViewDTO,
    *,
    scope: ChatScopeName,
    selected_dayun: Mapping[str, object],
) -> dict[str, object]:
    """Keep every required upper layer exactly once and stop at the requested scope."""
    hierarchy: dict[str, object] = {"hierarchy": "natal>dayun>liunian>liuyue>liuri"}

    if scope in {"dayun", "lifecycle"}:
        if temporal.qiyun:
            hierarchy["qiyun"] = {
                key: value
                for key, value in temporal.qiyun.items()
                if key
                in {
                    "direction",
                    "start_years",
                    "start_months",
                    "start_days",
                    "start_hours",
                    "start_age_years",
                    "start_datetime",
                }
                and value is not None
            }
        if scope == "lifecycle":
            hierarchy["dayun_sequence"] = [
                _compact_temporal_pillar(item) for item in temporal.dayuns
            ]
        else:
            hierarchy["target_dayun"] = _compact_temporal_pillar(selected_dayun)
            hierarchy["dayun_sequence"] = [
                _compact_dayun_summary(item) for item in temporal.dayuns
            ]
        return hierarchy

    active = temporal.active_dayun or selected_dayun
    if active:
        hierarchy["active_dayun"] = _compact_temporal_pillar(active)
    if temporal.year:
        hierarchy["target_liunian"] = _compact_temporal_pillar(temporal.year)

    if scope == "year":
        hierarchy["monthly_windows"] = [
            _compact_temporal_pillar(item) for item in temporal.months
        ]
    elif scope == "month":
        if temporal.selected_month:
            hierarchy["target_liuyue"] = _compact_temporal_pillar(temporal.selected_month)
    elif scope == "day":
        if temporal.selected_month:
            hierarchy["target_liuyue"] = _compact_temporal_pillar(temporal.selected_month)
        if temporal.selected_day:
            hierarchy["target_liuri"] = _compact_temporal_pillar(temporal.selected_day)
    elif scope == "general":
        if temporal.selected_month:
            hierarchy["current_liuyue_summary"] = _compact_dayun_summary(temporal.selected_month)
        if temporal.selected_day:
            day_summary = {
                key: temporal.selected_day[key]
                for key in ("date", "ganzhi", "stem_ten_god", "branch_ten_god")
                if temporal.selected_day.get(key) is not None
            }
            if day_summary:
                hierarchy["current_liuri_summary"] = day_summary
    return hierarchy


def build_model_context(
    chart: ChartResultDTO,
    temporal: TemporalContextViewDTO,
    *,
    scope: ChatScopeName,
    topics: Sequence[ChatTopic],
    selected_dayun: Mapping[str, object],
) -> dict[str, object]:
    natal_core = build_natal_core(chart, seasonal_strength=temporal.seasonal_strength)
    return {
        "context_version": "bazi-fortune-chat-context-v3",
        "context_policy": "deterministic_read_only",
        "natal_core": natal_core,
        "topic_context": build_topic_context(natal_core, topics),
        "temporal_hierarchy": build_temporal_hierarchy(
            temporal,
            scope=scope,
            selected_dayun=selected_dayun,
        ),
    }


def compact_history(history: Iterable[Mapping[str, str]], limit: int = 6) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in list(history)[-limit:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            result.append({"role": role, "content": content})
    return result


def build_retrieval_queries(
    *,
    question: str,
    day_master: str,
    gender: str,
    scope: ChatScopeName,
    topics: Sequence[ChatTopic],
    active_dayun_ganzhi: str,
    year_ganzhi: str,
    month_ganzhi: str,
    day_ganzhi: str,
) -> tuple[str, ...]:
    """Build focused RAG queries; never inject unrelated health/lifecycle topics."""
    queries: list[str] = [question.strip()]
    labels = topic_label(topics)
    queries.append(f"{day_master}日主 月令旺衰 格局喜用 {labels}")

    hierarchy_parts = [part for part in (active_dayun_ganzhi, year_ganzhi) if part]
    if scope in {"month", "day"} and month_ganzhi:
        hierarchy_parts.append(month_ganzhi)
    if scope == "day" and day_ganzhi:
        hierarchy_parts.append(day_ganzhi)
    if hierarchy_parts:
        queries.append(f"{' '.join(hierarchy_parts)} 原局大运岁运层级作用 {labels}")

    if "relationship" in topics:
        spouse = "男命财星夫妻宫" if gender == "male" else "女命官杀夫妻宫"
        queries.extend(
            (
                f"{spouse} 透藏根气 喜忌 岁运触发",
                "桃花红鸾天喜 合冲夫妻宫 感情成立条件",
            )
        )
    if "wealth" in topics:
        queries.append("财星 食伤生财 比劫夺财 身财承载 岁运触发")
    if "career" in topics:
        queries.append("官杀 印星 食伤 事业职位 学业考试 岁运触发")
    if "health" in topics:
        queries.append("五行偏性 寒暖燥湿 调候气机 脏腑 岁运变化")
    if "kinship" in topics:
        queries.append("六亲十神 宫位 透藏根气 喜忌 岁运触发")
    if scope in {"dayun", "lifecycle"}:
        queries.append("出生起运 大运承接 转折 格局用神变化")
    if scope == "year":
        queries.append("流年在大运背景下的流月窗口 条件与救应")
    elif scope == "month":
        queries.append("流月在大运流年背景下的阶段窗口 条件与救应")
    elif scope == "day":
        queries.append("流日在大运流年流月背景下的短期触发 条件与救应")

    return tuple(dict.fromkeys(item for item in queries if item.strip()))


def is_redundant_deterministic_evidence(*, source_id: str, title: str) -> bool:
    """Ten-god lookup rows duplicate facts already present in natal/temporal pillars."""
    return source_id == "PROJECT-CORE-RULES-V1" and "日主见" in title
