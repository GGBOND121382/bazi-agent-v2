"""Dependency-free keyword + character-vector retrieval with RRF fusion."""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from .models import RagChunk, RetrievalPlan, RetrievedEvidence


def _tokens(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    words = re.findall(r"[a-z0-9_]+", lowered)
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", lowered)
    cjk_tokens = [run[i : i + 2] for run in cjk_runs for i in range(max(1, len(run) - 1))]
    return tuple(words + cjk_tokens)


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    numerator = sum(value * right[token] for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _task_matches(plan_task: str | None, chunk_task: str) -> bool:
    # "interpretation" is the umbrella professional-analysis task.  It must be
    # able to retrieve approved rule, pattern and explanation chunks; narrower
    # task names remain strict filters.
    return plan_task in (None, "interpretation") or chunk_task == plan_task


class HybridRetriever:
    def __init__(self, chunks: Iterable[RagChunk]) -> None:
        chunks = tuple(chunks)
        if any(chunk.status.value != "approved" for chunk in chunks):
            raise ValueError("retriever accepts approved chunks only")
        self._chunks = chunks

    def retrieve(self, plan: RetrievalPlan) -> tuple[RetrievedEvidence, ...]:
        candidates = [
            chunk
            for chunk in self._chunks
            if (plan.school is None or chunk.school == plan.school)
            and _task_matches(plan.task_type, chunk.task_type)
            and (not plan.languages or chunk.language in plan.languages)
        ]
        query_tokens = Counter(_tokens(" ".join(plan.queries)))
        keyword_scores: dict[str, float] = {}
        vector_scores: dict[str, float] = {}
        for chunk in candidates:
            doc_tokens = Counter(
                _tokens(
                    chunk.content_normalized
                    + " "
                    + str(chunk.metadata.get("title", ""))
                )
            )
            keyword_scores[chunk.chunk_id] = sum(
                min(count, doc_tokens[token]) for token, count in query_tokens.items()
            )
            vector_scores[chunk.chunk_id] = _cosine(query_tokens, doc_tokens)

        keyword_rank = self._rank(keyword_scores)
        vector_rank = self._rank(vector_scores)
        fused: list[tuple[float, RagChunk]] = []
        for chunk in candidates:
            if keyword_scores[chunk.chunk_id] <= 0 and vector_scores[chunk.chunk_id] <= 0:
                continue
            score = 1 / (60 + keyword_rank[chunk.chunk_id]) + 1 / (
                60 + vector_rank[chunk.chunk_id]
            )
            fused.append((score, chunk))
        fused.sort(key=lambda item: (-item[0], item[1].chunk_id))

        seen_sources_and_titles: set[tuple[str, str]] = set()
        evidence: list[RetrievedEvidence] = []
        for score, chunk in fused:
            title = str(chunk.metadata.get("title", chunk.chunk_id))
            dedupe_key = (chunk.source_id, title)
            if dedupe_key in seen_sources_and_titles:
                continue
            seen_sources_and_titles.add(dedupe_key)
            evidence.append(
                RetrievedEvidence(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    title=title,
                    content=chunk.content_normalized,
                    citation=f"{chunk.source_id}#{chunk.chunk_id}",
                    score=score,
                    rank_reasons=(
                        f"keyword_rank={keyword_rank[chunk.chunk_id]}",
                        f"vector_rank={vector_rank[chunk.chunk_id]}",
                    ),
                )
            )
            if len(evidence) == plan.top_k:
                break
        return tuple(evidence)

    @staticmethod
    def _rank(scores: dict[str, float]) -> dict[str, int]:
        ordered = sorted(scores, key=lambda key: (-scores[key], key))
        return {key: index + 1 for index, key in enumerate(ordered)}
