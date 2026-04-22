"""Pricing orchestration service."""

import math
from datetime import date
from typing import Any

import QuantLib as ql

from deskpricer import __version__ as service_version
from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_STEPS,
    ql_date_from_iso,
)
from deskpricer.schemas import (
    GreeksRequest,
    ImpliedVolRequest,
    PnLAttributionGETRequest,
    PortfolioRequest,
)
from deskpricer.services.ql_runtime import _QL_LOCK, with_evaluation_date

# Import from app so monkeypatches of ``deskpricer.app.price_vanilla`` still work.
import deskpricer.app as _app

_QUANTLIB_VERSION = getattr(ql, "__version__", "unknown")


def _default_engine(style: str) -> str:
    return "analytic" if style == "european" else "binomial_crr"


def _meta(engine: str | None, valuation_date: date) -> dict[str, Any]:
    return {
        "service_version": service_version,
        "quantlib_version": _QUANTLIB_VERSION,
        "engine": engine,
        "valuation_date": valuation_date.isoformat(),
    }


def _add_non_default_bumps(inputs: dict[str, Any], params) -> None:
    if not math.isclose(params.bump_spot_rel, DEFAULT_BUMP_SPOT_REL, rel_tol=1e-12):
        inputs["bump_spot_rel"] = params.bump_spot_rel
    if not math.isclose(params.bump_vol_abs, DEFAULT_BUMP_VOL_ABS, rel_tol=1e-12):
        inputs["bump_vol_abs"] = params.bump_vol_abs
    if not math.isclose(params.bump_rate_abs, DEFAULT_BUMP_RATE_ABS, rel_tol=1e-12):
        inputs["bump_rate_abs"] = params.bump_rate_abs


async def run_greeks(
    params: GreeksRequest,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    valuation_date = params.valuation_date or date.today()
    async with with_evaluation_date(valuation_date):
        result = _app.price_vanilla(
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
    meta = _meta(params.engine, valuation_date)
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
    if params.steps != DEFAULT_STEPS:
        inputs["steps"] = params.steps
    _add_non_default_bumps(inputs, params)
    return meta, inputs, result.model_dump()


async def run_impliedvol(
    params: ImpliedVolRequest,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    valuation_date = params.valuation_date or date.today()
    async with with_evaluation_date(valuation_date):
        result = _app.compute_implied_vol(
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
    meta = _meta(params.engine, valuation_date)
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
    if params.steps != DEFAULT_STEPS:
        inputs["steps"] = params.steps
    if params.accuracy != 1e-4:
        inputs["accuracy"] = params.accuracy
    if params.max_iterations != 1000:
        inputs["max_iterations"] = params.max_iterations
    return meta, inputs, result.model_dump()


async def run_portfolio(
    payload: PortfolioRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, float]]:
    valuation_date = payload.valuation_date or date.today()
    legs_out: list[dict[str, Any]] = []
    aggregate: dict[str, float] = {
        "delta": 0.0,
        "gamma": 0.0,
        "vega": 0.0,
        "theta": 0.0,
        "rho": 0.0,
        "charm": 0.0,
    }
    # NOTE: Holding the lock for the entire loop serializes portfolio requests.
    async with _QL_LOCK:
        old_eval = ql.Settings.instance().evaluationDate
        try:
            ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
            for leg in payload.legs:
                result = _app.price_vanilla(
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
    return meta, legs_out, aggregate


def _pnl_pv_kwargs(
    params: PnLAttributionGETRequest, suffix: str, valuation_date: date
) -> dict[str, Any]:
    return {
        "s": getattr(params, f"s{suffix}"),
        "k": params.k,
        "t": getattr(params, f"t{suffix}"),
        "r": getattr(params, f"r{suffix}"),
        "q": getattr(params, f"q{suffix}"),
        "v": getattr(params, f"v{suffix}"),
        "option_type": params.type,
        "style": params.style,
        "engine": params.engine,
        "valuation_date": valuation_date,
        "steps": params.steps,
        "bump_spot_rel": params.bump_spot_rel,
        "bump_vol_abs": params.bump_vol_abs,
        "bump_rate_abs": params.bump_rate_abs,
    }


def _pnl_cg_kwargs(
    params: PnLAttributionGETRequest, suffix: str, valuation_date: date, base_price: float
) -> dict[str, Any]:
    return {
        "base_price": base_price,
        "s": getattr(params, f"s{suffix}"),
        "k": params.k,
        "t": getattr(params, f"t{suffix}"),
        "r": getattr(params, f"r{suffix}"),
        "q": getattr(params, f"q{suffix}"),
        "v": getattr(params, f"v{suffix}"),
        "option_type": params.type,
        "style": params.style,
        "engine": params.engine,
        "valuation_date": valuation_date,
        "steps": params.steps,
        "bump_spot_rel": params.bump_spot_rel,
        "bump_vol_abs": params.bump_vol_abs,
        "bump_rate_abs": params.bump_rate_abs,
    }


async def run_pnl_attribution(
    params: PnLAttributionGETRequest,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    valuation_date_t_minus_1 = params.valuation_date_t_minus_1
    valuation_date_t = params.valuation_date_t
    method = params.method
    if valuation_date_t_minus_1 is None and valuation_date_t is None:
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
            ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date_t_minus_1)
            greeks_t_minus_1 = _app.price_vanilla(
                **_pnl_pv_kwargs(params, "_t_minus_1", valuation_date_t_minus_1)
            )
            if params.cross_greeks:
                vanna_t_m1, volga_t_m1 = _app.compute_cross_greeks(
                    **_pnl_cg_kwargs(
                        params, "_t_minus_1", valuation_date_t_minus_1, greeks_t_minus_1.price
                    )
                )
            ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date_t)
            greeks_t = _app.price_vanilla(**_pnl_pv_kwargs(params, "_t", valuation_date_t))
            if params.cross_greeks and method == "average":
                vanna_t, volga_t = _app.compute_cross_greeks(
                    **_pnl_cg_kwargs(params, "_t", valuation_date_t, greeks_t.price)
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
    outputs: dict[str, Any] = {
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
    if params.steps != DEFAULT_STEPS:
        inputs["steps"] = params.steps
    if params.engine != _default_engine(params.style):
        inputs["engine"] = params.engine
    _add_non_default_bumps(inputs, params)
    if params.cross_greeks:
        inputs["cross_greeks"] = True
    return meta, inputs, outputs
