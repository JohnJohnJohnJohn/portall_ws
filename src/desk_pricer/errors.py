"""Custom exceptions and FastAPI HTTP exception handlers."""

import logging

from fastapi import Request
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from desk_pricer.responses import serialize_error, use_json_from_request

_logger = logging.getLogger("desk_pricer")


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


async def desk_pricer_exception_handler(request: Request, exc: DeskPricerError) -> Response:
    use_json = use_json_from_request(request)
    body = serialize_error(exc.code, exc.message, exc.field, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=exc.status, media_type=media_type)


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle Pydantic / FastAPI validation errors as INVALID_INPUT."""
    from fastapi.exceptions import RequestValidationError

    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = first.get("loc", [])
            field = ".".join(str(x) for x in loc) if loc else None
            message = first.get("msg", "Validation error")
        else:
            field = None
            message = "Validation error"
    else:
        field = None
        message = str(exc)

    use_json = use_json_from_request(request)
    body = serialize_error("INVALID_INPUT", message, field, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=422, media_type=media_type)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    use_json = use_json_from_request(request)
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif exc.status_code == 401:
        code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code >= 500:
        code = "INTERNAL_ERROR"
    else:
        code = "INVALID_INPUT"
    body = serialize_error(code, exc.detail, None, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=exc.status_code, media_type=media_type)


async def catchall_exception_handler(request: Request, exc: Exception) -> Response:
    _logger.exception("Unhandled exception")
    use_json = use_json_from_request(request)
    body = serialize_error("PRICING_FAILURE", "An internal error occurred", None, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=500, media_type=media_type)
