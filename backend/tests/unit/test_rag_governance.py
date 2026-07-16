"""A1 corpus governance and retrieval gates."""
from __future__ import annotations

import hashlib
from pathlib import Path

import jsonschema
import pytest

from app.services.rag import (
    ChunkStatus,
    CorpusGovernance,
    GovernanceError,
    HybridRetriever,
    RetrievalPlan,
    ReviewDecision,
    SourceCatalog,
)
from app.services.rag.chunking import chunk_document
from app.services.rag.seed import import_approved_seed

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "contracts" / "rag_seed" / "source_catalog.json"
SEED = ROOT / "contracts" / "rag_seed" / "rules_seed.jsonl"


def _governance() -> CorpusGovernance:
    return CorpusGovernance(SourceCatalog.load(CATALOG))


def _decision(**overrides: bool) -> ReviewDecision:
    values = {
        "license_verified": True,
        "language_verified": True,
        "provenance_verified": True,
        **overrides,
    }
    return ReviewDecision(reviewer_id="reviewer-test", **values)


@pytest.mark.rag
def test_state_machine_requires_review_before_approval() -> None:
    governance = _governance()
    chunk = governance.ingest_text(
        source_id="HANDOFF-CORE",
        chunk_id="test-1",
        content="木生火。\r\n",
        provenance={"path": "contracts/rag_seed/manual.txt", "version": "test-v1"},
        school="cross_school_core",
        task_type="calculation",
    )
    assert chunk.status is ChunkStatus.QUARANTINE
    assert chunk.content_normalized == "木生火。"
    with pytest.raises(GovernanceError, match="reviewed"):
        governance.approve(chunk.chunk_id)
    assert governance.review(chunk.chunk_id, _decision()).status is ChunkStatus.REVIEWED
    assert governance.approve(chunk.chunk_id).status is ChunkStatus.APPROVED


@pytest.mark.rag
def test_unknown_source_duplicate_and_evaluation_contamination_fail_closed() -> None:
    governance = _governance()
    common = dict(
        chunk_id="test-2",
        content="十神以日干为参照。",
        provenance={"path": "contracts/rag_seed/manual.txt", "version": "test-v1"},
        school="cross_school_core",
        task_type="calculation",
    )
    with pytest.raises(GovernanceError, match="registry"):
        governance.ingest_text(source_id="UNKNOWN", **common)
    governance.ingest_text(source_id="HANDOFF-CORE", **common)
    with pytest.raises(GovernanceError, match="duplicate"):
        governance.ingest_text(source_id="HANDOFF-CORE", **{**common, "chunk_id": "test-3"})
    with pytest.raises(GovernanceError, match="physically isolated"):
        governance.ingest_text(
            source_id="HANDOFF-CORE",
            **{
                **common,
                "chunk_id": "test-4",
                "content": "另一条",
                "provenance": {"path": "contracts/evaluation/x.jsonl", "version": "eval-v1"},
            },
        )


@pytest.mark.rag
def test_known_evaluation_hash_is_rejected_without_reading_evaluation_files() -> None:
    text = "隔离样本"
    digest = hashlib.sha256(text.encode()).hexdigest()
    governance = CorpusGovernance(SourceCatalog.load(CATALOG), evaluation_hashes=[digest])
    with pytest.raises(GovernanceError, match="contamination"):
        governance.ingest_text(
            source_id="HANDOFF-CORE",
            chunk_id="eval-hash",
            content=text,
            provenance={"path": "contracts/rag_seed/input.txt", "version": "test-v1"},
            school="engineering_policy",
            task_type="rag",
        )


@pytest.mark.rag
def test_personal_data_or_high_risk_review_cannot_be_approved() -> None:
    governance = _governance()
    governance.ingest_text(
        source_id="HANDOFF-CORE",
        chunk_id="risk",
        content="此规则保证发财。",
        provenance={"path": "contracts/rag_seed/input.txt", "version": "test-v1"},
        school="engineering_policy",
        task_type="interpretation",
    )
    governance.review("risk", _decision())
    with pytest.raises(GovernanceError, match="checks"):
        governance.approve("risk")


@pytest.mark.rag
def test_seed_import_contract_and_hybrid_retrieval() -> None:
    governance = _governance()
    imported = import_approved_seed(governance, SEED)
    assert len(imported) == 10
    schema = __import__("json").loads(
        (ROOT / "contracts" / "schemas" / "rag_chunk.schema.json").read_text(encoding="utf-8")
    )
    for chunk in governance.approved_chunks():
        jsonschema.validate(chunk.to_contract(), schema)

    retriever = HybridRetriever(governance.approved_chunks())
    hits = retriever.retrieve(
        RetrievalPlan(queries=("十神 日干",), task_type="calculation", top_k=3)
    )
    assert hits
    assert hits[0].chunk_id == "RULE-SEED-003"
    assert hits[0].citation == "HANDOFF-CORE#RULE-SEED-003"
    assert all(hit.source_id == "HANDOFF-CORE" for hit in hits)


@pytest.mark.rag
def test_retriever_refuses_quarantine_chunks() -> None:
    governance = _governance()
    chunk = governance.ingest_text(
        source_id="HANDOFF-CORE",
        chunk_id="quarantined",
        content="未审核内容",
        provenance={"path": "contracts/rag_seed/input.txt", "version": "test-v1"},
        school="engineering_policy",
        task_type="rag",
    )
    with pytest.raises(ValueError, match="approved"):
        HybridRetriever([chunk])


@pytest.mark.rag
def test_source_version_is_mandatory() -> None:
    governance = _governance()
    with pytest.raises(GovernanceError, match="version"):
        governance.ingest_text(
            source_id="HANDOFF-CORE",
            chunk_id="no-version",
            content="缺少来源版本",
            provenance={"path": "contracts/rag_seed/input.txt"},
            school="engineering_policy",
            task_type="rag",
        )


@pytest.mark.rag
def test_layered_chunking_preserves_case_and_classic_section_boundaries() -> None:
    case = chunk_document(document_type="case", title="案例", text="命盘\n推理\n结论")
    assert len(case) == 1
    assert case[0].metadata["atomic"] is True

    classic = chunk_document(
        document_type="classic",
        title="古籍",
        text="# 卷一\n" + "甲" * 140 + "\n# 卷二\n" + "乙" * 140,
        max_chars=100,
        overlap=10,
    )
    assert {chunk.metadata["section"] for chunk in classic} == {"卷一", "卷二"}
    assert all("甲" not in chunk.content or "乙" not in chunk.content for chunk in classic)
