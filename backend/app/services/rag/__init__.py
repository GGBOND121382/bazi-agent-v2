"""Approved-corpus governance and deterministic hybrid retrieval (A1)."""

from .dataset_v2 import DatasetIntegrityError, DatasetV2Retriever, default_dataset_root
from .governance import CorpusGovernance, GovernanceError, ReviewDecision, SourceCatalog
from .models import (
    ChunkStatus,
    EvidenceRetriever,
    RagChunk,
    RetrievalBundle,
    RetrievalChannel,
    RetrievalPlan,
    RetrievedEvidence,
)
from .retrieval import HybridRetriever

__all__ = [
    "ChunkStatus",
    "CorpusGovernance",
    "DatasetIntegrityError",
    "DatasetV2Retriever",
    "EvidenceRetriever",
    "GovernanceError",
    "HybridRetriever",
    "RagChunk",
    "RetrievalBundle",
    "RetrievalChannel",
    "RetrievalPlan",
    "RetrievedEvidence",
    "ReviewDecision",
    "SourceCatalog",
    "default_dataset_root",
]
