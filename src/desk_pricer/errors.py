"""Custom exceptions and FastAPI HTTP exception handlers."""

from fastapi import Request
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from desk_pricer.responses import serialize_error, use_json_from_request


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
            field = ".".join(str(x) for x in first.get("loc", []))
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
    return Response(content=body, status_code=400, media_type=media_type)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    use_json = use_json_from_request(request)
    body = serialize_error("INVALID_INPUT", exc.detail, None, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=exc.status_code, media_type=media_type)


async def catchall_exception_handler(request: Request, exc: Exception) -> Response:
    use_json = use_json_from_request(request)
    body = serialize_error("PRICING_FAILURE", str(exc), None, json_format=use_json)
    media_type = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, status_code=500, media_type=media_type)
