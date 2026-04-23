"""Single-leg Greeks endpoint."""

from fastapi import APIRouter, Request

from deskpricer.responses import serialize_greeks
from deskpricer.routers._common import handle_get_endpoint
from deskpricer.schemas import GreeksRequest
from deskpricer.services.pricing_service import run_greeks

router = APIRouter()


@router.get("/v1/greeks")
async def greeks(request: Request):
    return await handle_get_endpoint(request, GreeksRequest, run_greeks, serialize_greeks)
