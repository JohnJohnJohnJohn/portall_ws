"""FastAPI application factory."""

import time
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from deskpricer import __version__ as service_version
from deskpricer.errors import (
    DeskPricerError,
    catchall_exception_handler,
    deskpricer_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from deskpricer.logging_config import setup_logging

_REQUEST_LOGGER = setup_logging()


def create_app() -> FastAPI:
    app = FastAPI(title="DeskPricer", version=service_version, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def log_and_format(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except StarletteHTTPException as exc:
            status = exc.status_code
            raise
        except DeskPricerError as exc:
            status = exc.status
            raise
        except Exception:
            status = 500
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            try:
                _REQUEST_LOGGER.info(
                    "request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "query": request.url.query[:200],
                        "duration_ms": round(duration_ms, 3),
                        "status": status,
                    },
                )
            except OSError as exc:
                import sys

                try:
                    sys.stderr.write(f"[DeskPricer] request logging failed: {exc}\n")
                except OSError:
                    pass

    app.exception_handler(DeskPricerError)(deskpricer_exception_handler)
    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(catchall_exception_handler)

    from deskpricer.routers import greeks, health, impliedvol, pnl_attribution, portfolio

    app.include_router(health.router)
    app.include_router(greeks.router)
    app.include_router(impliedvol.router)
    app.include_router(portfolio.router)
    app.include_router(pnl_attribution.router)
    return app
