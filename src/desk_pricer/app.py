"""FastAPI application factory and routes."""

import asyncio
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import QuantLib as ql
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from desk_pricer import __version__ as service_version
from desk_pricer.errors import (
    DeskPricerError,
    InvalidInputError,
    catchall_exception_handler,
    desk_pricer_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from desk_pricer.pricing.conventions import ql_date_from_iso
from desk_pricer.pricing.engine import price_vanilla
from desk_pricer.pricing.implied_vol import compute_implied_vol
from desk_pricer.responses import (
    serialize_greeks,
    serialize_health,
    serialize_impliedvol,
    serialize_portfolio,
    serialize_version,
    use_json_from_request,
)
from desk_pricer.schemas import GreeksRequest, ImpliedVolRequest, PortfolioRequest
from pydantic import ValidationError

# Protect QuantLib global state
_QL_LOCK = asyncio.Lock()

_QUANTLIB_VERSION = getattr(ql, "__version__", "unknown")
_PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

_START_TIME = time.time()

_DEFAULT_LOG_DIR = Path(r"C:\ProgramData\DeskPricer\logs")
_LOG_FILE = _DEFAULT_LOG_DIR / "pricer.log"


def _ensure_log_dir() -> None:
    try:
        _DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _log_request(method: str, path: str, query: str, duration_ms: float, status: int) -> None:
    _ensure_log_dir()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "method": method,
        "path": path,
        "query": query[:200],
        "duration_ms": round(duration_ms, 3),
        "status": status,
    }
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        print(f"[desk-pricer] logging failed: {exc}", file=sys.stderr)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DeskPricer",
        version=service_version,
        docs_url=None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def log_and_format(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        _log_request(
            request.method,
            request.url.path,
            request.url.query,
            duration_ms,
            response.status_code,
        )
        return response

    @app.exception_handler(DeskPricerError)
    async def _desk_pricer_exc(request: Request, exc: DeskPricerError):
        return await desk_pricer_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        return await validation_exception_handler(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _catchall_exc(request: Request, exc: Exception):
        return await catchall_exception_handler(request, exc)

    @app.get("/v1/health")
    async def health(request: Request):
        uptime = time.time() - _START_TIME
        use_json = use_json_from_request(request)
        body = serialize_health("UP", uptime, json_format=use_json)
        media = "application/json" if use_json else "application/xml; charset=utf-8"
        return Response(content=body, media_type=media)

    @app.get("/v1/version")
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

    @app.get("/v1/greeks")
    async def greeks(request: Request):
        use_json = use_json_from_request(request)
        try:
            params = GreeksRequest.model_validate(request.query_params)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=None) from exc

        valuation_date = params.valuation_date or date.today()

        async with _QL_LOCK:
            old_eval = ql.Settings.instance().evaluationDate
            try:
                ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
                result = price_vanilla(
                    s=params.s,
                    k=params.k,
                    t=params.t,
                    r=params.r,
                    q=params.q,
                    v=params.v,
                    option_type=params.type,
                    style=params.style,
                    engine=params.engine,
                    valuation_date=valuation_date,
                    steps=params.steps,
                    bump_spot_rel=params.bump_spot_rel,
                    bump_vol_abs=params.bump_vol_abs,
                    bump_rate_abs=params.bump_rate_abs,
                )
            except DeskPricerError:
                raise
            except RuntimeError as exc:
                raise InvalidInputError(f"Pricing failed: {exc}") from exc
            finally:
                ql.Settings.instance().evaluationDate = old_eval

        meta = {
            "service_version": service_version,
            "quantlib_version": _QUANTLIB_VERSION,
            "engine": params.engine,
            "valuation_date": valuation_date.isoformat(),
        }
        inputs = {
            "s": params.s,
            "k": params.k,
            "t": params.t,
            "r": params.r,
            "q": params.q,
            "v": params.v,
            "type": params.type,
            "style": params.style,
        }
        if params.steps != 400:
            inputs["steps"] = params.steps
        if params.bump_spot_rel != 0.01:
            inputs["bump_spot_rel"] = params.bump_spot_rel
        if params.bump_vol_abs != 0.001:
            inputs["bump_vol_abs"] = params.bump_vol_abs
        if params.bump_rate_abs != 0.001:
            inputs["bump_rate_abs"] = params.bump_rate_abs
        outputs = result.model_dump()

        body = serialize_greeks(meta, inputs, outputs, json_format=use_json)
        media = "application/json" if use_json else "application/xml; charset=utf-8"
        return Response(content=body, media_type=media)

    @app.get("/v1/impliedvol")
    async def impliedvol(request: Request):
        use_json = use_json_from_request(request)
        try:
            params = ImpliedVolRequest.model_validate(request.query_params)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=None) from exc

        valuation_date = params.valuation_date or date.today()

        async with _QL_LOCK:
            old_eval = ql.Settings.instance().evaluationDate
            try:
                ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
                result = compute_implied_vol(
                    s=params.s,
                    k=params.k,
                    t=params.t,
                    r=params.r,
                    q=params.q,
                    target_price=params.price,
                    option_type=params.type,
                    style=params.style,
                    engine=params.engine,
                    valuation_date=valuation_date,
                    steps=params.steps,
                    accuracy=params.accuracy,
                    max_iterations=params.max_iterations,
                )
            except DeskPricerError:
                raise
            except RuntimeError as exc:
                raise InvalidInputError(f"Implied vol calculation failed: {exc}") from exc
            finally:
                ql.Settings.instance().evaluationDate = old_eval

        meta = {
            "service_version": service_version,
            "quantlib_version": _QUANTLIB_VERSION,
            "engine": params.engine,
            "valuation_date": valuation_date.isoformat(),
        }
        inputs = {
            "s": params.s,
            "k": params.k,
            "t": params.t,
            "r": params.r,
            "q": params.q,
            "price": params.price,
            "type": params.type,
            "style": params.style,
        }
        if params.steps != 400:
            inputs["steps"] = params.steps
        if params.accuracy != 1e-4:
            inputs["accuracy"] = params.accuracy
        if params.max_iterations != 1000:
            inputs["max_iterations"] = params.max_iterations
        outputs = result.model_dump()

        body = serialize_impliedvol(meta, inputs, outputs, json_format=use_json)
        media = "application/json" if use_json else "application/xml; charset=utf-8"
        return Response(content=body, media_type=media)

    @app.post("/v1/portfolio/greeks")
    async def portfolio_greeks(request: Request, payload: PortfolioRequest):
        use_json = use_json_from_request(request)
        valuation_date = payload.valuation_date or date.today()

        legs_out = []
        aggregate = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0, "charm": 0.0}

        # NOTE: Holding the lock for the entire loop serializes portfolio requests.
        # A future refactor could use per-leg locking with cloned evaluation dates
        # or a process pool to avoid blocking single-leg requests.
        async with _QL_LOCK:
            old_eval = ql.Settings.instance().evaluationDate
            try:
                ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
                for leg in payload.legs:
                    result = price_vanilla(
                        s=leg.s,
                        k=leg.k,
                        t=leg.t,
                        r=leg.r,
                        q=leg.q,
                        v=leg.v,
                        option_type=leg.type,
                        style=leg.style,
                        engine=leg.engine,
                        valuation_date=valuation_date,
                        steps=leg.steps,
                        bump_spot_rel=leg.bump_spot_rel,
                        bump_vol_abs=leg.bump_vol_abs,
                        bump_rate_abs=leg.bump_rate_abs,
                    )
                    row = {
                        "id": leg.id,
                        "engine": leg.engine,
                        "price": result.price,
                        "delta": result.delta,
                        "gamma": result.gamma,
                        "vega": result.vega,
                        "theta": result.theta,
                        "rho": result.rho,
                        "charm": result.charm,
                    }
                    legs_out.append(row)
                    for greek in aggregate:
                        aggregate[greek] += leg.qty * getattr(result, greek)
            except DeskPricerError:
                raise
            except RuntimeError as exc:
                raise InvalidInputError(f"Pricing failed: {exc}") from exc
            finally:
                ql.Settings.instance().evaluationDate = old_eval

        meta = {
            "service_version": service_version,
            "quantlib_version": _QUANTLIB_VERSION,
            "valuation_date": valuation_date.isoformat(),
        }

        body = serialize_portfolio(meta, legs_out, aggregate, json_format=use_json)
        media = "application/json" if use_json else "application/xml; charset=utf-8"
        return Response(content=body, media_type=media)

    return app
