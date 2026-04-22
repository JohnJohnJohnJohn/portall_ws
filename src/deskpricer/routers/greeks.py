"""Single-leg Greeks endpoint."""

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError

from deskpricer.responses import serialize_greeks, use_json_from_request
from deskpricer.schemas import GreeksRequest
from deskpricer.services.pricing_service import run_greeks

router = APIRouter()


@router.get("/v1/greeks")
async def greeks(request: Request):
    use_json = use_json_from_request(request)
    try:
        params = GreeksRequest.model_validate(request.query_params)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=None) from exc

    meta, inputs, outputs = await run_greeks(params)
    body = serialize_greeks(meta, inputs, outputs, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)
