"""RAG value objects.

These models deliberately contain no provider, database, or LLM objects.  They
mirror ``contracts/schemas/rag_chunk.schema.json`` and keep approval state
explicit so retrieval cannot accidentally include quarantined material.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ChunkStatus(StrEnum):
    RAW = "raw"
    QUARANTINE = "quarantine"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EVALUATION_ONLY = "evaluation_only"


class RetrievalChannel(StrEnum):
    """Governed context groups from the v2.1 corpus retrieval policy."""

    AUTHORITATIVE_EVIDENCE = "authoritative_evidence"
    SIMILAR_CASES = "similar_cases"
    EXPLANATION_EXAMPLES = "explanation_examples"


@dataclass(frozen=True, slots=True)
class RagChunk:
    chunk_id: str
    source_id: str
    status: ChunkStatus
    content_original: str
    content_normalized: str
    content_hash: str
    license: str
    provenance: dict[str, Any]
    metadata: dict[str, Any]
    language: str = "und"
    school: str = "cross_school_core"
    task_type: str = "interpretation"
    review: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "rag-chunk-v1"

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "status": self.status.value,
            "content_original": self.content_original,
            "content_normalized": self.content_normalized,
            "content_hash": self.content_hash,
            "language": self.language,
            "school": self.school,
            "task_type": self.task_type,
            "license": self.license,
            "provenance": self.provenance,
            "metadata": self.metadata,
            "review": self.review,
        }


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    queries: tuple[str, ...]
    school: str | None = None
    task_type: str | None = None
    languages: tuple[str, ...] = ()
    top_k: int = 5
    case_top_k: int = 4
    explanation_top_k: int = 4

    def __post_init__(self) -> None:
        if not self.queries or not all(query.strip() for query in self.queries):
            raise ValueError("retrieval queries must be non-empty")
        if not 1 <= self.top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        if not 0 <= self.case_top_k <= 10:
            raise ValueError("case_top_k must be between 0 and 10")
        if not 0 <= self.explanation_top_k <= 10:
            raise ValueError("explanation_top_k must be between 0 and 10")


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    chunk_id: str
    source_id: str
    title: str
    content: str
    citation: str
    score: float
    rank_reasons: tuple[str, ...]
    channel: RetrievalChannel = RetrievalChannel.AUTHORITATIVE_EVIDENCE
    collection: str = "approved_core"
    trust_tier: str = "A"
    can_support_claim: bool = True
    can_support_case_analogy: bool = False
    can_supply_explanation: bool = True


@dataclass(frozen=True, slots=True)
class RetrievalBundle:
    authoritative_evidence: tuple[RetrievedEvidence, ...] = ()
    similar_cases: tuple[RetrievedEvidence, ...] = ()
    explanation_examples: tuple[RetrievedEvidence, ...] = ()
    conflicting_evidence: tuple[RetrievedEvidence, ...] = ()

    @property
    def all_evidence(self) -> tuple[RetrievedEvidence, ...]:
        return (
            self.authoritative_evidence
            + self.similar_cases
            + self.explanation_examples
            + self.conflicting_evidence
        )


class EvidenceRetriever(Protocol):
    def retrieve(self, plan: RetrievalPlan) -> tuple[RetrievedEvidence, ...]: ...
