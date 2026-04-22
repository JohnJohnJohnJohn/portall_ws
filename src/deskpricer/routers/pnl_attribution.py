"""PnL attribution endpoint."""

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError

from deskpricer.responses import serialize_pnl_attribution, use_json_from_request
from deskpricer.schemas import PnLAttributionGETRequest
from deskpricer.services.pricing_service import run_pnl_attribution

router = APIRouter()


@router.get("/v1/pnl_attribution")
async def pnl_attribution(request: Request):
    use_json = use_json_from_request(request)
    try:
        params = PnLAttributionGETRequest.model_validate(request.query_params)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(), body=None) from exc

    meta, inputs, outputs = await run_pnl_attribution(params)
    body = serialize_pnl_attribution(meta, inputs, outputs, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)
