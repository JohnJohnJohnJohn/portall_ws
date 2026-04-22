"""Implied volatility endpoint."""

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError

from deskpricer.responses import serialize_impliedvol, use_json_from_request
from deskpricer.schemas import ImpliedVolRequest
from deskpricer.services.pricing_service import run_impliedvol

router = APIRouter()


@router.get("/v1/impliedvol")
async def impliedvol(request: Request):
    use_json = use_json_from_request(request)
    try:
        params = ImpliedVolRequest.model_validate(request.query_params)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=None) from exc

    meta, inputs, outputs = await run_impliedvol(params)
    body = serialize_impliedvol(meta, inputs, outputs, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)
