"""H1 trust-boundary regression tests."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.adapters.llm import DeepSeekProvider
from app.api.dto import StructuredAnalysisDTO
from app.jobs import InMemoryAnalysisStore

ROOT = Path(__file__).resolve().parents[3]


def test_production_code_never_references_evaluation_corpus_path() -> None:
    violations: list[str] = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8").replace("\\", "/").casefold()
        if "contracts/evaluation" in text or "04_data/evaluation" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_provider_repr_and_configuration_error_do_not_reveal_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-secret-must-never-appear"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    provider = DeepSeekProvider()
    assert secret not in repr(provider)


def test_share_storage_hashes_token_and_supports_revocation() -> None:
    store = InMemoryAnalysisStore()
    analysis = StructuredAnalysisDTO(
        analysis_id="a", chart_id="c", school="s", claims=[], limitations=[]
    )
    store.save_result(analysis, {
        "report_id": "r", "chart_id": "c", "schema_version": "report-view-v1",
        "title": "r", "generated_at": "2026-01-01T00:00:00Z",
        "toc": [], "blocks": [], "citations": [], "limitations": [],
    })
    record, token = store.create_share("r", datetime.now(UTC) + timedelta(hours=1))
    assert token not in repr(record)
    assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert store.revoke_share(record.share_id).revoked is True

