"""FastAPI application factory and routes."""

import asyncio
import math
import sys
import time
from datetime import date
from typing import Any

import QuantLib as ql
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from deskpricer import __version__ as service_version
from deskpricer.errors import (
    DeskPricerError,
    InvalidInputError,
    catchall_exception_handler,
    deskpricer_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from deskpricer.logging_config import setup_logging
from deskpricer.pricing.conventions import ql_date_from_iso
from deskpricer.pricing.cross_greeks import compute_cross_greeks
from deskpricer.pricing.engine import price_vanilla
from deskpricer.pricing.implied_vol import compute_implied_vol
from deskpricer.responses import (
    serialize_greeks,
    serialize_health,
    serialize_impliedvol,
    serialize_pnl_attribution,
    serialize_portfolio,
    serialize_version,
    use_json_from_request,
)
from deskpricer.schemas import (
    GreeksRequest,
    ImpliedVolRequest,
    PnLAttributionGETRequest,
    PortfolioRequest,
)

# Protect QuantLib global state
_QL_LOCK = asyncio.Lock()

_QUANTLIB_VERSION = getattr(ql, "__version__", "unknown")
_PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

_START_TIME = time.monotonic()

_REQUEST_LOGGER = setup_logging()


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
            except Exception as exc:
                # If the request logger itself fails (disk full, broken handler,
                # etc.), at least emit a stderr line so the failure isn't silent.
                try:
                    sys.stderr.write(f"[DeskPricer] request logging failed: {exc}\n")
                except Exception:
                    pass

    app.exception_handler(DeskPricerError)(deskpricer_exception_handler)
    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(StarletteHTTPException)(http_exception_handler)
    app.exception_handler(Exception)(catchall_exception_handler)

    @app.get("/v1/health")
    async def health(request: Request):
        uptime = time.monotonic() - _START_TIME
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
                    engine=params.engine,  # type: ignore[arg-type]
                    valuation_date=valuation_date,
                    steps=params.steps,
                    bump_spot_rel=params.bump_spot_rel,
                    bump_vol_abs=params.bump_vol_abs,
                    bump_rate_abs=params.bump_rate_abs,
                )
            finally:
                ql.Settings.instance().evaluationDate = old_eval

        meta = {
            "service_version": service_version,
            "quantlib_version": _QUANTLIB_VERSION,
            "engine": params.engine,
            "valuation_date": valuation_date.isoformat(),
        }
        inputs: dict[str, Any] = {
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
        if not math.isclose(params.bump_spot_rel, 0.01, rel_tol=1e-12):
            inputs["bump_spot_rel"] = params.bump_spot_rel
        if not math.isclose(params.bump_vol_abs, 0.001, rel_tol=1e-12):
            inputs["bump_vol_abs"] = params.bump_vol_abs
        if not math.isclose(params.bump_rate_abs, 0.001, rel_tol=1e-12):
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
                    engine=params.engine,  # type: ignore[arg-type]
                    valuation_date=valuation_date,
                    steps=params.steps,
                    accuracy=params.accuracy,
                    max_iterations=params.max_iterations,
                )
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
        aggregate = {
            "delta": 0.0,
            "gamma": 0.0,
            "vega": 0.0,
            "theta": 0.0,
            "rho": 0.0,
            "charm": 0.0,
        }

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
                        engine=leg.engine,  # type: ignore[arg-type]
                        valuation_date=valuation_date,
                        steps=leg.steps,
                        bump_spot_rel=leg.bump_spot_rel,
                        bump_vol_abs=leg.bump_vol_abs,
                        bump_rate_abs=leg.bump_rate_abs,
                    )
                    if not math.isfinite(result.price):
                        raise InvalidInputError(
                            f"Pricing produced non-finite price for leg {leg.id}",
                            field="price",
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
                        val = getattr(result, greek)
                        if not math.isfinite(val):
                            raise InvalidInputError(
                                f"Pricing produced non-finite {greek} for leg {leg.id}",
                                field=greek,
                            )
                        aggregate[greek] += leg.qty * val
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

    @app.get("/v1/pnl_attribution")
    async def pnl_attribution(request: Request):
        use_json = use_json_from_request(request)
        try:
            params = PnLAttributionGETRequest.model_validate(request.query_params)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=None) from exc

        valuation_date_t_minus_1 = params.valuation_date_t_minus_1
        valuation_date_t = params.valuation_date_t
        method = params.method

        if valuation_date_t_minus_1 is None and valuation_date_t is None:
            # User omitted both dates — use same date for both pricings
            # and derive calendar days from the rounded day counts that
            # the engine actually uses (matching expiry_from_t).
            valuation_date = date.today()
            valuation_date_t_minus_1 = valuation_date
            valuation_date_t = valuation_date
            days_t_m1 = max(1, math.floor(params.t_t_minus_1 * 365 + 0.5))
            days_t = max(1, math.floor(params.t_t * 365 + 0.5))
            calendar_days = max(0, days_t_m1 - days_t)
        elif valuation_date_t_minus_1 is not None and valuation_date_t is not None:
            calendar_days = (valuation_date_t - valuation_date_t_minus_1).days
        else:
            raise InvalidInputError(
                "Provide both valuation_date_t_minus_1 and valuation_date_t, or omit both",
                field="valuation_date_t",
            )

        vanna_t_m1 = volga_t_m1 = vanna_t = volga_t = 0.0

        async with _QL_LOCK:
            old_eval = ql.Settings.instance().evaluationDate
            try:
                # Phase 1: price and optional cross-greeks at t-1
                ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date_t_minus_1)
                greeks_t_minus_1 = price_vanilla(
                    s=params.s_t_minus_1,
                    k=params.k,
                    t=params.t_t_minus_1,
                    r=params.r_t_minus_1,
                    q=params.q_t_minus_1,
                    v=params.v_t_minus_1,
                    option_type=params.type,
                    style=params.style,
                    engine=params.engine,  # type: ignore[arg-type]
                    valuation_date=valuation_date_t_minus_1,
                    steps=params.steps,
                    bump_spot_rel=params.bump_spot_rel,
                    bump_vol_abs=params.bump_vol_abs,
                    bump_rate_abs=params.bump_rate_abs,
                )
                if params.cross_greeks:
                    vanna_t_m1, volga_t_m1 = compute_cross_greeks(
                        greeks_t_minus_1.price,
                        s=params.s_t_minus_1,
                        k=params.k,
                        t=params.t_t_minus_1,
                        r=params.r_t_minus_1,
                        q=params.q_t_minus_1,
                        v=params.v_t_minus_1,
                        option_type=params.type,
                        style=params.style,
                        engine=params.engine,  # type: ignore[arg-type]
                        valuation_date=valuation_date_t_minus_1,
                        steps=params.steps,
                        bump_spot_rel=params.bump_spot_rel,
                        bump_vol_abs=params.bump_vol_abs,
                        bump_rate_abs=params.bump_rate_abs,
                    )

                # Phase 2: price and optional cross-greeks at t
                ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date_t)
                greeks_t = price_vanilla(
                    s=params.s_t,
                    k=params.k,
                    t=params.t_t,
                    r=params.r_t,
                    q=params.q_t,
                    v=params.v_t,
                    option_type=params.type,
                    style=params.style,
                    engine=params.engine,  # type: ignore[arg-type]
                    valuation_date=valuation_date_t,
                    steps=params.steps,
                    bump_spot_rel=params.bump_spot_rel,
                    bump_vol_abs=params.bump_vol_abs,
                    bump_rate_abs=params.bump_rate_abs,
                )
                if params.cross_greeks and method == "average":
                    vanna_t, volga_t = compute_cross_greeks(
                        greeks_t.price,
                        s=params.s_t,
                        k=params.k,
                        t=params.t_t,
                        r=params.r_t,
                        q=params.q_t,
                        v=params.v_t,
                        option_type=params.type,
                        style=params.style,
                        engine=params.engine,  # type: ignore[arg-type]
                        valuation_date=valuation_date_t,
                        steps=params.steps,
                        bump_spot_rel=params.bump_spot_rel,
                        bump_vol_abs=params.bump_vol_abs,
                        bump_rate_abs=params.bump_rate_abs,
                    )
            finally:
                ql.Settings.instance().evaluationDate = old_eval

        delta_s = params.s_t - params.s_t_minus_1
        delta_v_points = (params.v_t - params.v_t_minus_1) * 100.0
        delta_r_points = (params.r_t - params.r_t_minus_1) * 100.0

        delta_pnl = greeks_t_minus_1.delta * delta_s
        gamma_pnl = 0.5 * greeks_t_minus_1.gamma * (delta_s**2)

        if method == "average":
            vega_pnl = ((greeks_t_minus_1.vega + greeks_t.vega) / 2.0) * delta_v_points
            rho_pnl = ((greeks_t_minus_1.rho + greeks_t.rho) / 2.0) * delta_r_points
        else:
            vega_pnl = greeks_t_minus_1.vega * delta_v_points
            rho_pnl = greeks_t_minus_1.rho * delta_r_points

        theta_pnl = greeks_t_minus_1.theta * calendar_days

        # Cross-greeks PnL
        vanna_pnl_per_unit = 0.0
        volga_pnl_per_unit = 0.0
        if params.cross_greeks:
            if method == "average":
                vanna = (vanna_t_m1 + vanna_t) / 2.0
                volga = (volga_t_m1 + volga_t) / 2.0
            else:
                vanna, volga = vanna_t_m1, volga_t_m1
            vanna_pnl_per_unit = vanna * delta_s * delta_v_points
            volga_pnl_per_unit = 0.5 * volga * (delta_v_points**2)

        actual_pnl = greeks_t.price - greeks_t_minus_1.price
        explained_pnl = (
            delta_pnl
            + gamma_pnl
            + vega_pnl
            + theta_pnl
            + rho_pnl
            + vanna_pnl_per_unit
            + volga_pnl_per_unit
        )
        residual_pnl = actual_pnl - explained_pnl

        qty = params.qty
        outputs = {
            "price_t_minus_1": greeks_t_minus_1.price,
            "price_t": greeks_t.price,
            "actual_pnl": qty * actual_pnl,
            "delta_pnl": qty * delta_pnl,
            "gamma_pnl": qty * gamma_pnl,
            "vega_pnl": qty * vega_pnl,
            "theta_pnl": qty * theta_pnl,
            "rho_pnl": qty * rho_pnl,
            "vanna_pnl": qty * vanna_pnl_per_unit,
            "volga_pnl": qty * volga_pnl_per_unit,
            "explained_pnl": qty * explained_pnl,
            "residual_pnl": qty * residual_pnl,
        }

        meta = {
            "service_version": service_version,
            "quantlib_version": _QUANTLIB_VERSION,
            "valuation_date_t_minus_1": valuation_date_t_minus_1.isoformat(),
            "valuation_date_t": valuation_date_t.isoformat(),
            "method": method,
        }
        inputs: dict[str, Any] = {
            "s_t_minus_1": params.s_t_minus_1,
            "s_t": params.s_t,
            "k": params.k,
            "t_t_minus_1": params.t_t_minus_1,
            "t_t": params.t_t,
            "r_t_minus_1": params.r_t_minus_1,
            "r_t": params.r_t,
            "q_t_minus_1": params.q_t_minus_1,
            "q_t": params.q_t,
            "v_t_minus_1": params.v_t_minus_1,
            "v_t": params.v_t,
            "type": params.type,
            "style": params.style,
        }
        if not math.isclose(params.qty, 1.0, rel_tol=1e-12):
            inputs["qty"] = params.qty
        if params.steps != 400:
            inputs["steps"] = params.steps
        if params.engine != ("analytic" if params.style == "european" else "binomial_crr"):
            inputs["engine"] = params.engine
        if not math.isclose(params.bump_spot_rel, 0.01, rel_tol=1e-12):
            inputs["bump_spot_rel"] = params.bump_spot_rel
        if not math.isclose(params.bump_vol_abs, 0.001, rel_tol=1e-12):
            inputs["bump_vol_abs"] = params.bump_vol_abs
        if not math.isclose(params.bump_rate_abs, 0.001, rel_tol=1e-12):
            inputs["bump_rate_abs"] = params.bump_rate_abs
        if params.cross_greeks:
            inputs["cross_greeks"] = True

        body = serialize_pnl_attribution(meta, inputs, outputs, json_format=use_json)
        media = "application/json" if use_json else "application/xml; charset=utf-8"
        return Response(content=body, media_type=media)

    return app
