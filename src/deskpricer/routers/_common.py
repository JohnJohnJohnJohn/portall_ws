"""Shared GET endpoint handler for query-param based routers."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError

from deskpricer.responses import use_json_from_request


async def handle_get_endpoint(request: Request, schema_cls, run_fn, serialize_fn) -> Response:
    use_json = use_json_from_request(request)
    try:
        params = schema_cls.model_validate(request.query_params)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=None) from exc

    meta, inputs, outputs = await run_fn(params)
    body = serialize_fn(meta, inputs, outputs, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)
