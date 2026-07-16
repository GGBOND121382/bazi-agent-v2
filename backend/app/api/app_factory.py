"""FastAPI app factory + error handlers.

Single shared FastAPI instance; main.py imports `app` from here.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..domain.errors import DomainError
from .dto import ApiError
from .error_codes import ErrorCode
from .v1 import analyses as analyses_v1
from .v1 import charts as charts_v1
from .v1 import resources as resources_v1

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bazi Agent API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.include_router(charts_v1.router)
    app.include_router(analyses_v1.router)
    app.include_router(resources_v1.router)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "req_unknown")
        code = ErrorCode(exc.error_code)
        body = ApiError(
            schema_version="api-error-v1",
            request_id=rid,
            error_code=code.value,
            message_key=_message_key_for(code),
            retryable=exc.retryable,
            safe_details=exc.safe_details or None,
        )
        return JSONResponse(status_code=code.http_status, content=body.model_dump(exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def pydantic_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "req_unknown")
        body = ApiError(
            schema_version="api-error-v1",
            request_id=rid,
            error_code=ErrorCode.INVALID_INPUT.value,
            message_key="input.invalid",
            retryable=False,
            field_errors=[{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()],
        )
        return JSONResponse(
            status_code=ErrorCode.INVALID_INPUT.http_status,
            content=body.model_dump(exclude_none=True),
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


def _message_key_for(code: ErrorCode) -> str:
    return code.name.lower().replace("_", ".")
