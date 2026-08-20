from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_nginx_helper():
    path = Path(__file__).resolve().parents[3] / "scripts" / "as1455_portal_nginx.py"
    spec = importlib.util.spec_from_file_location("as1455_portal_nginx", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_payload_preserves_dashboard_and_execution_api_routes() -> None:
    helper = _load_nginx_helper()
    payload = helper.dashboard_payload(8101, 8501, "stock", 8510, "stock-exec-api")

    assert "location ^~ /stock/" in payload
    assert "auth_request /_as1455_portal_auth;" in payload
    assert "proxy_pass http://127.0.0.1:8501;" in payload

    execution = payload.split("location ^~ /stock-exec-api/", 1)[1].split(
        "# END AS1455 DASHBOARD", 1
    )[0]
    assert "proxy_pass http://127.0.0.1:8510/;" in execution
    assert "proxy_set_header Authorization $http_authorization;" in execution
    assert "proxy_set_header X-Forwarded-Prefix /stock-exec-api;" in execution
    assert "auth_request" not in execution


def test_execution_proxy_defaults_are_backward_compatible() -> None:
    helper = _load_nginx_helper()
    payload = helper.dashboard_payload(8101, 8501, "stock")

    assert "location ^~ /stock-exec-api/" in payload
    assert "proxy_pass http://127.0.0.1:8510/;" in payload


def test_dashboard_and_execution_paths_must_differ() -> None:
    helper = _load_nginx_helper()

    with pytest.raises(ValueError, match="must differ"):
        helper.dashboard_payload(8101, 8501, "stock", 8510, "stock")
