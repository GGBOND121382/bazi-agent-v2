"""Read-only, policy-gated retrieval for ``bazi_rag_dataset_v2_1``.

The bundled SQLite FTS5 index contains production records only.  This adapter
still re-checks every returned JSON payload so a malformed or replaced index
cannot silently widen a channel's permissions.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import (
    RetrievalBundle,
    RetrievalChannel,
    RetrievalPlan,
    RetrievedEvidence,
)


class DatasetIntegrityError(RuntimeError):
    """Raised without including corpus content when the production bundle is invalid."""


@dataclass(frozen=True, slots=True)
class ChannelPolicy:
    channel: RetrievalChannel
    collection: str
    trust_tiers: frozenset[str]
    permission: str
    expected_status: str


@dataclass(slots=True)
class _Candidate:
    row: sqlite3.Row
    fusion_score: float = 0.0
    match_kinds: set[str] = field(default_factory=set)


_POLICIES = (
    ChannelPolicy(
        RetrievalChannel.AUTHORITATIVE_EVIDENCE,
        "approved_core",
        frozenset({"A", "B"}),
        "can_support_claim",
        "approved",
    ),
    ChannelPolicy(
        RetrievalChannel.SIMILAR_CASES,
        "benchmark_case_qa",
        frozenset({"C"}),
        "can_support_case_analogy",
        "source_curated",
    ),
    ChannelPolicy(
        RetrievalChannel.EXPLANATION_EXAMPLES,
        "qa_explanations",
        frozenset({"C"}),
        "can_supply_explanation",
        "auto_screened",
    ),
)
_EXPECTED_COUNTS = {
    "approved_core": 234,
    "benchmark_case_qa": 200,
    "qa_explanations": 7203,
}
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_LATIN_WORD = re.compile(r"[A-Za-z0-9_]{3,}")


def default_dataset_root() -> Path:
    configured = os.environ.get("BAZI_RAG_DATASET_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[4] / "data" / "bazi_rag_dataset_v2_1"


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro&immutable=1"


@lru_cache(maxsize=4)
def _validated_database(root_value: str) -> Path:
    root = Path(root_value).resolve()
    manifest_path = root / "manifest.json"
    database_path = root / "import" / "sqlite" / "bazi_rag.sqlite"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetIntegrityError("RAG manifest is missing or invalid") from exc
    if manifest.get("dataset") != "bazi_rag_dataset_v2_1" or manifest.get("version") != "2.1.0":
        raise DatasetIntegrityError("unsupported RAG dataset identity or version")
    if not database_path.is_file():
        raise DatasetIntegrityError("production RAG SQLite index is missing")

    try:
        connection = sqlite3.connect(_read_only_uri(database_path), uri=True)
        connection.execute("PRAGMA query_only=ON")
        counts = dict(
            connection.execute(
                "SELECT collection_name, count(*) FROM records GROUP BY collection_name"
            ).fetchall()
        )
        fts_count = int(connection.execute("SELECT count(*) FROM records_fts").fetchone()[0])
    except sqlite3.Error as exc:
        raise DatasetIntegrityError("production RAG SQLite index is invalid") from exc
    finally:
        if "connection" in locals():
            connection.close()
    if counts != _EXPECTED_COUNTS or fts_count != sum(_EXPECTED_COUNTS.values()):
        raise DatasetIntegrityError("production RAG collection counts do not match policy")
    return database_path


def _fts_expression(queries: tuple[str, ...]) -> str:
    terms: list[str] = []
    for query in queries:
        normalized = unicodedata.normalize("NFKC", query)
        for run in _CJK_RUN.findall(normalized):
            if len(run) >= 3:
                terms.extend(run[index : index + 3] for index in range(len(run) - 2))
        terms.extend(_LATIN_WORD.findall(normalized.casefold()))
    unique = tuple(dict.fromkeys(term.replace('"', "") for term in terms if term.strip()))[:24]
    return " OR ".join(f'"{term}"' for term in unique)


def _like_terms(queries: tuple[str, ...]) -> tuple[str, ...]:
    terms: list[str] = []
    for query in queries:
        normalized = unicodedata.normalize("NFKC", query).strip()
        terms.extend(run for run in _CJK_RUN.findall(normalized) if len(run) >= 2)
        terms.extend(_LATIN_WORD.findall(normalized.casefold()))
    return tuple(dict.fromkeys(terms))[:16]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DatasetV2Retriever:
    """SQLite FTS5 retriever implementing the bundle's three production channels."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_dataset_root()).resolve()
        self.database_path = _validated_database(str(self.root))

    def retrieve(self, plan: RetrievalPlan) -> tuple[RetrievedEvidence, ...]:
        return self.retrieve_bundle(plan).all_evidence

    def retrieve_bundle(self, plan: RetrievalPlan) -> RetrievalBundle:
        limits = {
            RetrievalChannel.AUTHORITATIVE_EVIDENCE: plan.top_k,
            RetrievalChannel.SIMILAR_CASES: plan.case_top_k,
            RetrievalChannel.EXPLANATION_EXAMPLES: plan.explanation_top_k,
        }
        results: dict[RetrievalChannel, tuple[RetrievedEvidence, ...]] = {}
        with sqlite3.connect(_read_only_uri(self.database_path), uri=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            for policy in _POLICIES:
                results[policy.channel] = self._retrieve_channel(
                    connection, plan, policy, limits[policy.channel]
                )
        return RetrievalBundle(
            authoritative_evidence=results[RetrievalChannel.AUTHORITATIVE_EVIDENCE],
            similar_cases=results[RetrievalChannel.SIMILAR_CASES],
            explanation_examples=results[RetrievalChannel.EXPLANATION_EXAMPLES],
        )

    def _retrieve_channel(
        self,
        connection: sqlite3.Connection,
        plan: RetrievalPlan,
        policy: ChannelPolicy,
        limit: int,
    ) -> tuple[RetrievedEvidence, ...]:
        if limit == 0:
            return ()
        per_query_pool = max(limit * 3, 12)
        candidates: dict[str, _Candidate] = {}

        def add_candidate(
            row: sqlite3.Row, *, match_kind: str, rank: int, weight: float
        ) -> None:
            chunk_id = str(row["chunk_id"])
            candidate = candidates.setdefault(chunk_id, _Candidate(row=row))
            candidate.fusion_score += weight / (60 + rank)
            candidate.match_kinds.add(match_kind)

        for query in plan.queries:
            expression = _fts_expression((query,))
            if expression:
                sql = """
                    SELECT r.*, bm25(records_fts) AS match_score
                    FROM records_fts JOIN records r USING(chunk_id)
                    WHERE records_fts MATCH ? AND r.collection_name = ?
                    ORDER BY match_score ASC, r.quality_score DESC, r.chunk_id ASC
                    LIMIT ?
                """
                for rank, row in enumerate(
                    connection.execute(
                        sql, (expression, policy.collection, per_query_pool)
                    ),
                    start=1,
                ):
                    add_candidate(row, match_kind="fts5_trigram", rank=rank, weight=1.0)

            like_terms = _like_terms((query,))
            if like_terms:
                clauses: list[str] = []
                parameters: list[Any] = [policy.collection]
                for term in like_terms:
                    pattern = f"%{_escape_like(term)}%"
                    clauses.append(
                        "(r.title LIKE ? ESCAPE '\\' OR r.question LIKE ? ESCAPE '\\' "
                        "OR r.answer LIKE ? ESCAPE '\\' OR r.retrieval_text LIKE ? ESCAPE '\\' "
                        "OR r.topics LIKE ? ESCAPE '\\')"
                    )
                    parameters.extend([pattern] * 5)
                parameters.append(per_query_pool)
                sql = f"""
                    SELECT r.*, 0.0 AS match_score FROM records r
                    WHERE r.collection_name = ? AND ({' OR '.join(clauses)})
                    ORDER BY r.quality_score DESC, r.chunk_id ASC LIMIT ?
                """
                for rank, row in enumerate(
                    connection.execute(sql, parameters), start=1
                ):
                    add_candidate(
                        row, match_kind="substring_fallback", rank=rank, weight=0.9
                    )

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                -item.fusion_score,
                -float(item.row["quality_score"] or 0.0),
                str(item.row["chunk_id"]),
            ),
        )

        evidence: list[RetrievedEvidence] = []
        for rank, candidate in enumerate(ranked, start=1):
            row = candidate.row
            try:
                payload = json.loads(str(row["json_payload"]))
            except json.JSONDecodeError as exc:
                raise DatasetIntegrityError("RAG record payload is invalid") from exc
            if not self._policy_allows(payload, policy):
                raise DatasetIntegrityError("RAG record violates its retrieval channel policy")
            if not self._matches_plan(payload, plan):
                continue
            permissions = payload["permissions"]
            source = payload.get("source", {})
            source_id = str(source.get("source_id") or "UNKNOWN-SOURCE")
            quality = float(payload.get("quality", {}).get("score", 0.0))
            evidence.append(
                RetrievedEvidence(
                    chunk_id=str(payload["chunk_id"]),
                    source_id=source_id,
                    title=str(payload.get("title") or payload["chunk_id"]),
                    content=str(payload.get("content_normalized") or payload["retrieval_text"]),
                    citation=f"{source_id}#{payload['chunk_id']}",
                    score=candidate.fusion_score + quality / 100_000,
                    rank_reasons=(
                        f"channel={policy.channel.value}",
                        *(f"match={kind}" for kind in sorted(candidate.match_kinds)),
                        f"fusion_rank={rank}",
                        f"trust_tier={payload['trust_tier']}",
                    ),
                    channel=policy.channel,
                    collection=policy.collection,
                    trust_tier=str(payload["trust_tier"]),
                    can_support_claim=bool(permissions.get("can_support_claim", False)),
                    can_support_case_analogy=bool(
                        permissions.get("can_support_case_analogy", False)
                    ),
                    can_supply_explanation=bool(
                        permissions.get("can_supply_explanation", False)
                    ),
                )
            )
            if len(evidence) == limit:
                break
        return tuple(evidence)

    @staticmethod
    def _policy_allows(payload: dict[str, Any], policy: ChannelPolicy) -> bool:
        return not (
            payload.get("schema_version") != "bazi-rag-record-v2"
            or payload.get("collection") != policy.collection
            or payload.get("status") != policy.expected_status
            or payload.get("production_enabled") is not True
            or payload.get("trust_tier") not in policy.trust_tiers
            or payload.get("permissions", {}).get(policy.permission) is not True
        )

    @staticmethod
    def _matches_plan(payload: dict[str, Any], plan: RetrievalPlan) -> bool:
        if plan.languages and payload.get("language") not in plan.languages:
            return False
        school = payload.get("school")
        return plan.school is None or school in {
            plan.school,
            "cross_school_core",
            "mixed_or_unspecified",
        }
