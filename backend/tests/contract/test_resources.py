"""R1 history, print/export, sharing and settings contracts."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.dto import BirthRequest, StructuredAnalysisDTO
from app.api.v1.resources import _charts, _jobs
from app.jobs import AnalysisJobService, InMemoryAnalysisStore
from app.services.chart_service import ChartService


def test_r1_resources_are_private_reversible_and_read_only(monkeypatch) -> None:
    charts = ChartService()
    request = BirthRequest.model_validate({
        "gender": "male",
        "birth_datetime_local": "1990-06-15T12:00:00",
        "timezone": "Asia/Shanghai",
        "birthplace": {"country": "CN", "city": "Shanghai"},
        "calculation_profile_id": "ziping_standard_v1",
    })
    _, chart_id, _ = charts.create_chart(request=request, idempotency_key="resource-chart")
    store = InMemoryAnalysisStore()
    analysis = StructuredAnalysisDTO(
        analysis_id="analysis_resource",
        chart_id=chart_id,
        school="engineering_policy",
        claims=[],
        limitations=[],
    )
    store.save_result(analysis, {
        "schema_version": "report-view-v1",
        "report_id": "report_resource",
        "chart_id": chart_id,
        "title": "报告",
        "generated_at": "2026-07-16T00:00:00Z",
        "toc": [], "blocks": [], "citations": [], "limitations": [],
    })
    jobs = AnalysisJobService(
        chart_service=charts,
        pipeline_factory=lambda: (_ for _ in ()).throw(AssertionError("not used")),
        store=store,
    )
    app = create_app()
    app.dependency_overrides[_charts] = lambda: charts
    app.dependency_overrides[_jobs] = lambda: jobs
    client = TestClient(app)

    assert client.patch(f"/api/v1/charts/{chart_id}/note", json={"note": "匿名备注"}).status_code == 204
    history = client.get("/api/v1/history").json()
    assert history["charts"][0]["note"] == "匿名备注"
    assert history["reports"][0]["report_id"] == "report_resource"

    export = client.post(
        "/api/v1/reports/report_resource/exports",
        headers={"Idempotency-Key": "print-key"},
    )
    assert export.status_code == 202
    assert export.json()["print_route"].endswith("/print")

    monkeypatch.delenv("ENABLE_REPORT_SHARING", raising=False)
    disabled = client.post("/api/v1/reports/report_resource/shares", json={"expires_in_hours": 1})
    assert disabled.status_code == 422
    monkeypatch.setenv("ENABLE_REPORT_SHARING", "true")
    created = client.post("/api/v1/reports/report_resource/shares", json={"expires_in_hours": 1})
    assert created.status_code == 201
    assert client.delete(f"/api/v1/shares/{created.json()['share_id']}").status_code == 204

    config = client.get("/api/v1/settings/configuration").json()
    assert config["calculation_profile_read_only"] is True
    assert config["model_configuration_read_only"] is True
