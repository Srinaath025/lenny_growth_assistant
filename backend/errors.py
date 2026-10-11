"""
Structured error contract.

Every non-2xx response from the API has the same shape:

    {"error": {"code": "CLOUD_CREDENTIALS_MISSING",
               "message": "Anthropic API key is not configured. Use local Ollama mode.",
               "request_id": "3f2c...",
               "hint": "optional remediation text"},
     "detail": "<same message, kept for backward compatibility>"}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.logging_config import request_id_ctx
import logging

logger = logging.getLogger("backend.errors")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "UPSTREAM_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    """Domain error carrying an HTTP status, machine-readable code and remediation hint."""

    def __init__(self, status_code: int, code: str, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint


def error_body(code: str, message: str, hint: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message, "request_id": request_id_ctx.get()}
    if hint:
        err["hint"] = hint
    if extra:
        err.update(extra)
    return {"error": err, "detail": message}


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    logger.warning("app_error", extra={"code": exc.code, "status": exc.status_code, "error_message": exc.message})
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.hint))


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content=error_body(code, message))


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "problem": e.get("msg", "")}
        for e in exc.errors()
    ]
    message = "Request validation failed: " + "; ".join(f"{f['field'] or 'body'}: {f['problem']}" for f in fields)
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", message, extra={"fields": fields}),
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "An unexpected server error occurred.", "Quote the request_id when reporting this."),
    )
