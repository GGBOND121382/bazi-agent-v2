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
    evaluate_relations,
)
from .shensha import (
    ShenShaHit,
    evaluate_shensha,
)

__all__ = [
    "BranchRelation",
    "DayunPeriod",
    "LiuyunContext",
    "QiyunResult",
    "ShenShaHit",
    "compute_liuyun",
    "compute_qiyun_and_dayun",
    "evaluate_relations",
    "evaluate_shensha",
]