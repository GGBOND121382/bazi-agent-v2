"""Fail-closed corpus ingestion, review, and approval workflow."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .models import ChunkStatus, RagChunk


class GovernanceError(ValueError):
    """Safe governance failure; messages never contain source content."""


_TRANSITIONS: dict[ChunkStatus, frozenset[ChunkStatus]] = {
    ChunkStatus.RAW: frozenset({ChunkStatus.QUARANTINE}),
    ChunkStatus.QUARANTINE: frozenset({ChunkStatus.REVIEWED, ChunkStatus.REJECTED}),
    ChunkStatus.REVIEWED: frozenset({ChunkStatus.APPROVED, ChunkStatus.REJECTED}),
    ChunkStatus.APPROVED: frozenset(),
    ChunkStatus.REJECTED: frozenset(),
    ChunkStatus.EVALUATION_ONLY: frozenset(),
}

_HIGH_RISK_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"必(?:死|得病|离婚|破产)",
        r"保证(?:发财|盈利)",
        r"certain(?: death| illness)",
    )
)


def assert_not_evaluation_path(path: Path) -> None:
    """Reject evaluation paths before any file is opened."""
    if any(part.casefold() in {"evaluation", "eval", "benchmarks"} for part in path.parts):
        raise GovernanceError("evaluation corpus is physically isolated from production RAG")


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip()


def _language(text: str) -> str:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk and latin and min(cjk, latin) / max(cjk, latin) >= 0.2:
        return "mixed"
    if cjk:
        return "zh"
    if latin:
        return "en"
    return "und"


@dataclass(frozen=True, slots=True)
class CatalogSource:
    source_id: str
    title: str
    license: str
    status: str
    allowed_uses: tuple[str, ...]


class SourceCatalog:
    def __init__(self, sources: Iterable[CatalogSource]) -> None:
        self._sources = {source.source_id: source for source in sources}

    @classmethod
    def load(cls, path: Path) -> SourceCatalog:
        assert_not_evaluation_path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "source-catalog-v1":
            raise GovernanceError("unsupported source catalog schema")
        return cls(
            CatalogSource(
                source_id=item["source_id"],
                title=item["title"],
                license=item["license"],
                status=item["status"],
                allowed_uses=tuple(item.get("allowed_uses", ())),
            )
            for item in payload["sources"]
        )

    def require_rag_source(self, source_id: str) -> CatalogSource:
        source = self._sources.get(source_id)
        if source is None:
            raise GovernanceError("source is absent from the registry")
        if source.status != "approved" or "rag" not in source.allowed_uses:
            raise GovernanceError("source is not licensed and approved for RAG")
        return source


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    reviewer_id: str
    license_verified: bool
    language_verified: bool
    provenance_verified: bool
    contains_personal_data: bool = False
    contains_high_risk_claims: bool = False
    notes: str = ""

    @property
    def approved(self) -> bool:
        return (
            self.license_verified
            and self.language_verified
            and self.provenance_verified
            and not self.contains_personal_data
            and not self.contains_high_risk_claims
        )


class CorpusGovernance:
    """Process-local A1 corpus repository with auditable state transitions."""

    def __init__(self, catalog: SourceCatalog, *, evaluation_hashes: Iterable[str] = ()) -> None:
        self.catalog = catalog
        self._chunks: dict[str, RagChunk] = {}
        self._by_hash: dict[str, str] = {}
        # Hashes are supplied by an isolated H1 process; A1 never reads eval files.
        self._evaluation_hashes = frozenset(evaluation_hashes)

    def ingest_text(
        self,
        *,
        source_id: str,
        chunk_id: str,
        content: str,
        provenance: dict[str, Any],
        school: str,
        task_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> RagChunk:
        source = self.catalog.require_rag_source(source_id)
        if not chunk_id or chunk_id in self._chunks:
            raise GovernanceError("chunk id is empty or already exists")
        origin_path = provenance.get("path")
        if origin_path:
            assert_not_evaluation_path(Path(str(origin_path)))
        if not str(provenance.get("version", "")).strip():
            raise GovernanceError("source version is required for provenance")
        if not content.strip():
            raise GovernanceError("empty content cannot enter quarantine")

        normalized = _normalize(content)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest in self._by_hash:
            raise GovernanceError("duplicate content hash")
        if digest in self._evaluation_hashes:
            raise GovernanceError("evaluation contamination detected")

        raw = RagChunk(
            chunk_id=chunk_id,
            source_id=source_id,
            status=ChunkStatus.RAW,
            content_original=content,
            content_normalized=normalized,
            content_hash=digest,
            language=_language(normalized),
            school=school,
            task_type=task_type,
            license=source.license,
            provenance=dict(provenance),
            metadata=dict(metadata or {}),
        )
        quarantined = self._transition(raw, ChunkStatus.QUARANTINE)
        self._chunks[chunk_id] = quarantined
        self._by_hash[digest] = chunk_id
        return quarantined

    def review(self, chunk_id: str, decision: ReviewDecision) -> RagChunk:
        chunk = self.require(chunk_id)
        if chunk.status is not ChunkStatus.QUARANTINE:
            raise GovernanceError("only quarantined chunks can be reviewed")
        automated_risk = any(pattern.search(chunk.content_normalized) for pattern in _HIGH_RISK_PATTERNS)
        review = {
            "reviewer_id": decision.reviewer_id,
            "license_verified": decision.license_verified,
            "language_verified": decision.language_verified,
            "provenance_verified": decision.provenance_verified,
            "contains_personal_data": decision.contains_personal_data,
            "contains_high_risk_claims": decision.contains_high_risk_claims or automated_risk,
            "notes": decision.notes,
        }
        reviewed = self._transition(replace(chunk, review=review), ChunkStatus.REVIEWED)
        self._chunks[chunk_id] = reviewed
        return reviewed

    def approve(self, chunk_id: str) -> RagChunk:
        chunk = self.require(chunk_id)
        if chunk.status is not ChunkStatus.REVIEWED:
            raise GovernanceError("only reviewed chunks can be approved")
        checks = (
            chunk.review.get("license_verified"),
            chunk.review.get("language_verified"),
            chunk.review.get("provenance_verified"),
            not chunk.review.get("contains_personal_data", True),
            not chunk.review.get("contains_high_risk_claims", True),
        )
        if not all(checks):
            raise GovernanceError("review checks did not pass")
        approved = self._transition(chunk, ChunkStatus.APPROVED)
        self._chunks[chunk_id] = approved
        return approved

    def reject(self, chunk_id: str, *, reviewer_id: str, reason: str) -> RagChunk:
        chunk = self.require(chunk_id)
        rejected = self._transition(
            replace(chunk, review={**chunk.review, "reviewer_id": reviewer_id, "rejection_reason": reason}),
            ChunkStatus.REJECTED,
        )
        self._chunks[chunk_id] = rejected
        return rejected

    def require(self, chunk_id: str) -> RagChunk:
        try:
            return self._chunks[chunk_id]
        except KeyError as exc:
            raise GovernanceError("unknown chunk id") from exc

    def approved_chunks(self) -> tuple[RagChunk, ...]:
        return tuple(chunk for chunk in self._chunks.values() if chunk.status is ChunkStatus.APPROVED)

    @staticmethod
    def _transition(chunk: RagChunk, target: ChunkStatus) -> RagChunk:
        if target not in _TRANSITIONS[chunk.status]:
            raise GovernanceError(f"invalid corpus transition: {chunk.status.value} -> {target.value}")
        return replace(chunk, status=target)
