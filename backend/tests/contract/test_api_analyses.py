"""I2 HTTP/SSE contract test with a deterministic provider."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import jsonschema
from fastapi.testclient import TestClient

from app.adapters.llm import ProviderResponse
from app.api.app_factory import create_app
from app.api.dto import BirthRequest
from app.api.v1.analyses import _analysis_service
from app.jobs import AnalysisJobService, InMemoryAnalysisStore
from app.services.agent import AnalysisPipeline
from app.services.chart_service import ChartService
from app.services.rag import CorpusGovernance, HybridRetriever, SourceCatalog
from app.services.rag.seed import import_approved_seed

ROOT = Path(__file__).resolve().parents[3]


class ContractProvider:
    def complete_json(self, **kwargs: Any) -> ProviderResponse:
        item = kwargs["input_payload"]["retrieval_context"]["authoritative_evidence"][0]
        return ProviderResponse(
            model_id="contract-mock",
            prompt_version=kwargs["prompt_version"],
            payload={
                "schema_version": "analysis-output-v1",
                "analysis_id": "analysis_contract",
                "chart_id": kwargs["input_payload"]["chart_id"],
                "school": "engineering_policy",
                "kinship_assessment": [
                    {"relation": name, "conclusion": "结合六亲星、宫位和岁运分析。"}
                    for name in ["父亲", "母亲", "兄弟姐妹", "配偶婚恋", "子女", "家庭互动"]
                ],
                "health_assessment": [
                    {"dimension": name, "conclusion": "结合原局偏性和岁运变化分析。"}
                    for name in ["五行偏性", "寒暖燥湿", "传统脏腑", "保护因素", "大运变化", "生活建议"]
                ],
                "dayun_assessment": [
                    {"stage": "出生至起运", "conclusion": "说明起运前阶段。"},
                    *[
                        {"stage": str(item.get("ganzhi", "大运")), "conclusion": "逐柱分析该步大运。"}
                        for item in kwargs["input_payload"]["analysis_context"]["temporal"]["dayun_table"]
                    ],
                ],
                "claims": [{
                    "claim_id": "claim_contract",
                    "topic": "引用",
                    "statement": "在本规则体系下，解释可能保持可追溯。",
                    "fact_ids": ["FACT-Y-1"],
                    "rule_ids": [item["evidence_id"]],
                    "evidence_ids": [item["evidence_id"]],
                    "counterevidence": [],
                    "confidence": 0.6,
                    "temporal_scope": "natal",
                    "school": "engineering_policy",
                }],
                "limitations": ["传统文化解释存在不确定性。"],
            },
        )


def test_analysis_job_sse_resume_and_report_contract() -> None:
    charts = ChartService()
    request = BirthRequest.model_validate({
        "gender": "male",
        "birth_datetime_local": "1990-06-15T12:00:00",
        "timezone": "Asia/Shanghai",
        "birthplace": {"country": "CN", "city": "Shanghai"},
        "calculation_profile_id": "ziping_standard_v1",
    })
    _, chart_id, _ = charts.create_chart(request=request, idempotency_key="contract-chart")
    governance = CorpusGovernance(
        SourceCatalog.load(ROOT / "contracts" / "rag_seed" / "source_catalog.json")
    )
    import_approved_seed(governance, ROOT / "contracts" / "rag_seed" / "rules_seed.jsonl")
    retriever = HybridRetriever(governance.approved_chunks())
    service = AnalysisJobService(
        chart_service=charts,
        pipeline_factory=lambda: AnalysisPipeline(provider=ContractProvider(), retriever=retriever),
        store=InMemoryAnalysisStore(),
    )
    app = create_app()
    app.dependency_overrides[_analysis_service] = lambda: service
    client = TestClient(app)

    started = client.post(
        f"/api/v1/charts/{chart_id}/analyses",
        json={"user_focus": ["引用必须可追溯"]},
        headers={"Idempotency-Key": "analysis-contract-key"},
    )
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    for _ in range(100):
        snapshot = client.get(f"/api/v1/jobs/{job_id}").json()
        if snapshot["stage"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert snapshot["stage"] == "completed"

    stream = client.get(f"/api/v1/jobs/{job_id}/events", headers={"Last-Event-ID": "1"})
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    assert "id: 1\n" not in stream.text
    assert "event: job" in stream.text

    report = client.get(f"/api/v1/reports/{snapshot['result_ref']}")
    assert report.status_code == 200
    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "report_view.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(report.json(), schema)
