"""Health and version endpoints."""

import sys
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

from deskpricer import __version__ as service_version
from deskpricer.responses import serialize_health, serialize_version, use_json_from_request

router = APIRouter()

_QUANTLIB_VERSION = getattr(
    __import__("QuantLib", fromlist=["__version__"]), "__version__", "unknown"
)
_PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
_START_TIME = time.monotonic()


@router.get("/v1/health")
async def health(request: Request):
    uptime = time.monotonic() - _START_TIME
    use_json = use_json_from_request(request)
    body = serialize_health("UP", uptime, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)


@router.get("/v1/version")
async def version(request: Request):
    info = {
        "service": service_version,
        "quantlib": _QUANTLIB_VERSION,
        "python": _PYTHON_VERSION,
    }
    use_json = use_json_from_request(request)
    body = serialize_version(info, json_format=use_json)
    media = "application/json" if use_json else "application/xml; charset=utf-8"
    return Response(content=body, media_type=media)
