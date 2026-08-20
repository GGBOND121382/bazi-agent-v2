"""API factory + health endpoint smoke tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.error_codes import ErrorCode
from app.domain.errors import ModelProviderDomainError


def test_health_returns_ok():
    client = TestClient(create_app())
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_request_id_header_round_trips():
    client = TestClient(create_app())
    r = client.get("/api/v1/health", headers={"x-request-id": "req_abc"})
    assert r.headers.get("X-Request-ID") == "req_abc"


def test_404_returns_error():
    client = TestClient(create_app())
    r = client.get("/api/v1/this-does-not-exist")
    # FastAPI returns 404 with default body; the header should still include request id
    assert "X-Request-ID" in r.headers


def test_error_code_http_status_table():
    assert ErrorCode.INVALID_INPUT.http_status == 422
    assert ErrorCode.CHART_CROSS_ENGINE_CONFLICT.http_status == 409
    assert ErrorCode.JOB_NOT_FOUND.http_status == 404
    assert ErrorCode.EVALUATION_SET_FORBIDDEN.http_status == 403
    assert ErrorCode.MODEL_PROVIDER_ERROR.http_status == 502
    assert ErrorCode.INTERNAL_ERROR.http_status == 500


def test_model_provider_failure_returns_parseable_retryable_api_error():
    app = create_app()

    @app.get("/test/model-provider-error")
    def fail_with_model_error():
        raise ModelProviderDomainError(
            "model generation failed",
            safe_details={"provider_error": "MODEL_INVALID_OUTPUT"},
        )

    response = TestClient(app, raise_server_exceptions=False).get("/test/model-provider-error")
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "schema_version": "api-error-v1",
        "request_id": response.headers["X-Request-ID"],
        "error_code": "MODEL_PROVIDER_ERROR",
        "message_key": "model.provider.error",
        "retryable": True,
        "safe_details": {"provider_error": "MODEL_INVALID_OUTPUT"},
    }
