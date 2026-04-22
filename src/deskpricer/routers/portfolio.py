"""Portfolio / bulk Greeks endpoint."""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from deskpricer.responses import serialize_portfolio, use_json_from_request
from deskpricer.schemas import PortfolioRequest
from deskpricer.services.pricing_service import run_portfolio

router = APIRouter()


@router.post("/v1/portfolio/greeks")
async def portfolio_greeks(request: Request, payload: PortfolioRequest):
    use_json = use_json_from_request(request)
    meta, legs_out, aggregate = await run_portfolio(payload)

    body = serialize_portfolio(meta, legs_out, aggregate, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)
