"""Implied volatility endpoint."""

from fastapi import APIRouter, Request

from deskpricer.responses import serialize_impliedvol
from deskpricer.routers._common import handle_get_endpoint
from deskpricer.schemas import ImpliedVolRequest
from deskpricer.services.pricing_service import run_impliedvol

router = APIRouter()


@router.get("/v1/impliedvol")
async def impliedvol(request: Request):
    return await handle_get_endpoint(request, ImpliedVolRequest, run_impliedvol, serialize_impliedvol)
