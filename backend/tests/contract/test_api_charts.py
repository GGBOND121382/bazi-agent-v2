"""B3 API tests — POST/GET/DELETE /v1/charts, idempotency, error mapping."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.app_factory import create_app


def _birth_request() -> dict:
    return {
        "schema_version": "birth-request-v1",
        "gender": "male",
        "birth_datetime_local": "1990-06-15T12:00:00",
        "timezone": "Asia/Shanghai",
        "birthplace": {"country": "CN", "city": "Shanghai", "longitude": 121.5, "latitude": 31.2},
        "calculation_profile_id": "ziping_standard_v1",
    }


@pytest.fixture
def client():
    return TestClient(create_app())


class TestCreateChart:
    def test_create_returns_201_and_dto(self, client):
        r = client.post(
            "/api/v1/charts",
            json=_birth_request(),
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["schema_version"] == "chart-result-v1"
        assert body["calculation_status"] == "passed"
        assert len(body["pillars"]) == 4
        assert "chart_id" in body
        assert len(body["engine_versions"]) == 2

    def test_shanghai_wall_time_is_used_for_hour_pillar(self, client):
        request = _birth_request()
        request["birth_datetime_local"] = "1995-12-22T15:00:00"
        response = client.post(
            "/api/v1/charts",
            json=request,
            headers={"Idempotency-Key": f"local-wall-time-{uuid.uuid4()}"},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["normalized_time"] == {
            "utc": "1995-12-22T07:00:00+00:00",
            "calculation_time": "1995-12-22T15:00:00+08:00",
            "time_basis": "civil_time",
        }
        assert [pillar["ganzhi"] for pillar in body["pillars"]] == [
            "乙亥",
            "戊子",
            "丁亥",
            "戊申",
        ]

        overview = client.get(f"/api/v1/charts/{body['chart_id']}/overview-view").json()
        assumptions = {item["label"]: item["value"] for item in overview["assumptions"]}
        assert assumptions["排盘时间（当地钟表）"] == "1995-12-22T15:00:00+08:00"
        assert assumptions["UTC 标准时间"] == "1995-12-22T07:00:00+00:00"

    def test_missing_idempotency_key_returns_error(self, client):
        r = client.post("/api/v1/charts", json=_birth_request())
        # FastAPI returns 422 for missing header
        assert r.status_code == 422

    def test_idempotent_repeat_returns_same_chart(self, client):
        key = f"k-{uuid.uuid4()}"
        r1 = client.post("/api/v1/charts", json=_birth_request(), headers={"Idempotency-Key": key})
        r2 = client.post("/api/v1/charts", json=_birth_request(), headers={"Idempotency-Key": key})
        assert r1.status_code == 201
        assert r2.status_code == 201
        # Both responses must point to the same chart_id
        assert r1.json()["chart_id"] == r2.json()["chart_id"]

    def test_unknown_profile_id_returns_error(self, client):
        req = _birth_request()
        req["calculation_profile_id"] = "nonexistent_v9"
        r = client.post(
            "/api/v1/charts",
            json=req,
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        # ProfileError → 422 PROFILE_UNKNOWN
        assert r.status_code == 422
        body = r.json()
        assert body["error_code"] == "PROFILE_UNKNOWN"
        assert body["schema_version"] == "api-error-v1"

    def test_unknown_timezone_returns_error(self, client):
        req = _birth_request()
        req["timezone"] = "Mars/Olympus"
        r = client.post(
            "/api/v1/charts",
            json=req,
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        assert r.status_code == 422
        assert r.json()["error_code"] == "TIMEZONE_UNKNOWN"

    def test_invalid_input_rejected(self, client):
        req = _birth_request()
        req["sneaky"] = "injection"  # extra field rejected by Pydantic
        r = client.post(
            "/api/v1/charts",
            json=req,
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        assert r.status_code == 422


class TestReadAndDelete:
    def test_get_chart(self, client):
        create = client.post(
            "/api/v1/charts",
            json=_birth_request(),
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        cid = create.json()["chart_id"]
        r = client.get(f"/api/v1/charts/{cid}")
        assert r.status_code == 200
        assert r.json()["chart_id"] == cid

        overview = client.get(f"/api/v1/charts/{cid}/overview-view")
        assert overview.status_code == 200
        assert overview.json()["schema_version"] == "chart-overview-view-v1"
        assert len(overview.json()["pillars"]) == 4

        temporal = client.get(f"/api/v1/charts/{cid}/temporal/2026")
        assert temporal.status_code == 200
        assert temporal.json()["schema_version"] == "temporal-context-view-v1"
        assert len(temporal.json()["months"]) == 12

    def test_get_unknown_chart_404(self, client):
        r = client.get("/api/v1/charts/chart_nope")
        assert r.status_code == 422  # INVALID_INPUT (mapped by service layer)

    def test_list_charts(self, client):
        # create a chart first
        client.post(
            "/api/v1/charts",
            json=_birth_request(),
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        r = client.get("/api/v1/charts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_chart(self, client):
        create = client.post(
            "/api/v1/charts",
            json=_birth_request(),
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}"},
        )
        cid = create.json()["chart_id"]
        r = client.delete(f"/api/v1/charts/{cid}")
        assert r.status_code == 204
        # Subsequent get returns 422
        r2 = client.get(f"/api/v1/charts/{cid}")
        assert r2.status_code == 422


class TestApiErrorShape:
    def test_error_includes_request_id(self, client):
        req = _birth_request()
        req["timezone"] = "Mars/Olympus"
        r = client.post(
            "/api/v1/charts",
            json=req,
            headers={"Idempotency-Key": f"k-{uuid.uuid4()}", "x-request-id": "req_test_123"},
        )
        assert r.status_code == 422
        assert r.headers.get("X-Request-ID") == "req_test_123"
        body = r.json()
        assert body["request_id"] == "req_test_123"
        assert body["schema_version"] == "api-error-v1"
        assert "message_key" in body
        assert "retryable" in body
