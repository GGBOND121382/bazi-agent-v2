"""Production v2.1 corpus identity, channel permissions, and FTS retrieval."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.rag import (
    DatasetIntegrityError,
    DatasetV2Retriever,
    RetrievalChannel,
    RetrievalPlan,
)

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "data" / "bazi_rag_dataset_v2_1"


@pytest.mark.rag
def test_dataset_v2_retrieves_three_strictly_governed_channels() -> None:
    bundle = DatasetV2Retriever(DATASET).retrieve_bundle(
        RetrievalPlan(queries=("甲日主", "财运"), school="engineering_policy", top_k=8)
    )
    assert bundle.authoritative_evidence
    assert bundle.similar_cases
    assert bundle.explanation_examples
    assert all(
        item.channel is RetrievalChannel.AUTHORITATIVE_EVIDENCE
        and item.collection == "approved_core"
        and item.trust_tier in {"A", "B"}
        and item.can_support_claim
        for item in bundle.authoritative_evidence
    )
    assert all(
        item.channel is RetrievalChannel.SIMILAR_CASES
        and item.collection == "benchmark_case_qa"
        and item.trust_tier == "C"
        and item.can_support_case_analogy
        and not item.can_support_claim
        for item in bundle.similar_cases
    )
    assert all(
        item.channel is RetrievalChannel.EXPLANATION_EXAMPLES
        and item.collection == "qa_explanations"
        and item.trust_tier == "C"
        and item.can_supply_explanation
        and not item.can_support_claim
        for item in bundle.explanation_examples
    )


@pytest.mark.rag
def test_two_character_focus_uses_safe_substring_fallback() -> None:
    evidence = DatasetV2Retriever(DATASET).retrieve(
        RetrievalPlan(queries=("事业",), case_top_k=2, explanation_top_k=2)
    )
    assert evidence
    assert any("match=substring_fallback" in item.rank_reasons for item in evidence)


@pytest.mark.rag
def test_multi_query_fusion_keeps_exact_relation_and_hidden_stem_rules() -> None:
    bundle = DatasetV2Retriever(DATASET).retrieve_bundle(
        RetrievalPlan(
            queries=("辛日主见庚", "地支午的藏干", "地支寅亥六合"),
            top_k=8,
            case_top_k=0,
            explanation_top_k=0,
        )
    )
    ids = {item.chunk_id for item in bundle.authoritative_evidence}
    assert {"CORE-TENGOD-辛-庚", "CORE-HIDDEN-午", "CORE-BRANCH-COMBINE-02"} <= ids


@pytest.mark.rag
def test_fts_syntax_is_treated_as_text_not_executable_query() -> None:
    evidence = DatasetV2Retriever(DATASET).retrieve(
        RetrievalPlan(queries=('" OR * NOT (', "甲日主"), top_k=2, case_top_k=0)
    )
    assert evidence


@pytest.mark.rag
def test_dataset_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"dataset": "unexpected", "version": "2.1.0"}), encoding="utf-8"
    )
    with pytest.raises(DatasetIntegrityError, match="unsupported"):
        DatasetV2Retriever(tmp_path)
