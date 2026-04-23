"""PnL attribution endpoint."""

from fastapi import APIRouter, Request

from deskpricer.responses import serialize_pnl_attribution
from deskpricer.routers._common import handle_get_endpoint
from deskpricer.schemas import PnLAttributionGETRequest
from deskpricer.services.pricing_service import run_pnl_attribution

router = APIRouter()


@router.get("/v1/pnl_attribution")
async def pnl_attribution(request: Request):
    return await handle_get_endpoint(
        request, PnLAttributionGETRequest, run_pnl_attribution, serialize_pnl_attribution
    )
