"""Custom exceptions and FastAPI HTTP exception handlers."""

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from deskpricer.responses import serialize_error, use_json_from_request

_logger = logging.getLogger("deskpricer")


class DeskPricerError(Exception):
    """Base exception for the service."""

    def __init__(self, code: str, message: str, field: str | None = None, status: int = 400):
        self.code = code
        self.message = message
        self.field = field
        self.status = status
        super().__init__(message)


class InvalidInputError(DeskPricerError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__("INVALID_INPUT", message, field, status=400)


class UnsupportedCombinationError(DeskPricerError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__("UNSUPPORTED_COMBINATION", message, field, status=422)


def _error_response(
    request: Request, code: str, message: str, status: int, field: str | None = None
) -> Response:
    use_json = use_json_from_request(request)
    body = serialize_error(code, message, field, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=status, media_type=media_type)


async def deskpricer_exception_handler(request: Request, exc: DeskPricerError) -> Response:
    return _error_response(request, exc.code, exc.message, exc.status, exc.field)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    """Handle Pydantic / FastAPI validation errors as INVALID_INPUT."""
    errors = exc.errors()
    if errors:
        first = errors[0]
        loc = first.get("loc", [])
        field = ".".join(str(x) for x in loc) if loc else None
        message = first.get("msg", "Validation error")
    else:
        field = None
        message = "Validation error"

    return _error_response(request, "INVALID_INPUT", message, 422, field)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif exc.status_code >= 500:
        code = "INTERNAL_ERROR"
    else:
        code = "INVALID_INPUT"
    message = str(exc.detail) if exc.detail is not None else ""
    return _error_response(request, code, message, exc.status_code)


async def catchall_exception_handler(request: Request, exc: Exception) -> Response:
    # Log concisely — full tracebacks from Excel/WEBSERVICE malformed requests
    # clog the log.  We keep the request context and exception type/message only.
    try:
        _logger.warning(
            "Invalid request: %s %s — %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
            exc,
            extra={
                "path": request.url.path,
                "method": request.method,
                "query": request.url.query[:200],
                "error_type": type(exc).__name__,
            },
        )
    except Exception:
        # If the request object is too malformed to extract URL info,
        # swallow the logging failure so the user still gets a 500 response.
        pass
    return _error_response(request, "PRICING_FAILURE", "An internal error occurred", 500)
