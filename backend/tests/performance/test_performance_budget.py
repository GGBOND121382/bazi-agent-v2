"""H1 local deterministic API latency budget (no provider/network calls)."""
from __future__ import annotations

import statistics
import time
import uuid

from fastapi.testclient import TestClient

from app.api.app_factory import create_app


def test_chart_creation_p95_under_500ms() -> None:
    client = TestClient(create_app())
    request = {
        "schema_version": "birth-request-v1",
        "gender": "male",
        "birth_datetime_local": "1990-06-15T12:00:00",
        "timezone": "Asia/Shanghai",
        "birthplace": {"country": "CN", "city": "Shanghai"},
        "calculation_profile_id": "ziping_standard_v1",
    }
    samples: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        response = client.post(
            "/api/v1/charts",
            json=request,
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        samples.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 201
    p95 = statistics.quantiles(samples, n=20)[18]
    assert p95 < 500, f"chart creation p95={p95:.1f}ms"

