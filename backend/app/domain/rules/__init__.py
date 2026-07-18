"""Pure rule layer — relations, 神煞 seeds, 起运, 大运, 流运.

No I/O. Each rule module exports a single `evaluate(...) -> Result` entry point.
"""
from .liuyun import (
    LiuyunContext,
    compute_liuyun,
)
from .qiyun_dayun import (
    DayunPeriod,
    QiyunResult,
    compute_qiyun_and_dayun,
)
from .relations import (
    BranchRelation,
    PositionedPillar,
    PositionedRelation,
    RelationRuleCatalog,
    evaluate_positioned_relations,
    evaluate_relations,
    relation_rule_catalog,
)
from .shensha import (
    ShenShaHit,
    evaluate_shensha,
    evaluate_shensha_for_target,
)
from .temporal import build_temporal_context, compute_exact_yun, describe_temporal_pillar

__all__ = [
    "BranchRelation",
    "DayunPeriod",
    "LiuyunContext",
    "PositionedPillar",
    "PositionedRelation",
    "QiyunResult",
    "RelationRuleCatalog",
    "ShenShaHit",
    "build_temporal_context",
    "compute_exact_yun",
    "compute_liuyun",
    "compute_qiyun_and_dayun",
    "describe_temporal_pillar",
    "evaluate_positioned_relations",
    "evaluate_relations",
    "relation_rule_catalog",
    "evaluate_shensha",
    "evaluate_shensha_for_target",
]
