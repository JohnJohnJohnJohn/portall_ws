"""Pricing orchestration service."""

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable

from deskpricer import __version__ as service_version
from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_CALENDAR,
    DEFAULT_STEPS,
    IV_SOLVER_DEFAULT_ACCURACY,
    IV_SOLVER_MAX_ITERATIONS,
)
from deskpricer.pricing.cross_greeks import compute_cross_greeks as _compute_cross_greeks
from deskpricer.pricing.engine import price_vanilla as _price_vanilla
from deskpricer.pricing.implied_vol import compute_implied_vol as _compute_implied_vol
from deskpricer.schemas import (
    GreeksOutput,
    GreeksRequest,
    ImpliedVolRequest,
    PnLAttributionGETRequest,
    PortfolioRequest,
)
from deskpricer.services.ql_runtime import QUANTLIB_VERSION, with_evaluation_date


def _meta(engine: str | None, valuation_date: date) -> dict[str, Any]:
    return {
        "service_version": service_version,
        "quantlib_version": QUANTLIB_VERSION,
        "engine": engine,
        "valuation_date": valuation_date.isoformat(),
    }


def _add_non_default_bumps(inputs: dict[str, Any], params) -> None:
    for name, default in (
        ("bump_spot_rel", DEFAULT_BUMP_SPOT_REL),
        ("bump_vol_abs", DEFAULT_BUMP_VOL_ABS),
        ("bump_rate_abs", DEFAULT_BUMP_RATE_ABS),
    ):
        if not math.isclose(getattr(params, name), default, rel_tol=1e-12):
            inputs[name] = getattr(params, name)


@dataclass(frozen=True)
class _MarketState:
    """Typed snapshot of a single-date market state for PnL attribution."""

    s: float
    t: float
    r: float
    q: float
    v: float


def _market_state(params: PnLAttributionGETRequest, suffix: str) -> _MarketState:
    return _MarketState(
        s=getattr(params, f"s{suffix}"),
        t=getattr(params, f"t{suffix}"),
        r=getattr(params, f"r{suffix}"),
        q=getattr(params, f"q{suffix}"),
        v=getattr(params, f"v{suffix}"),
    )


def _pnl_pv_kwargs(
    state: _MarketState, params: PnLAttributionGETRequest, valuation_date: date
) -> dict[str, Any]:
    return {
        **asdict(state),
        "k": params.k,
        "option_type": params.type,
        "style": params.style,
        "engine": params.engine,
        "valuation_date": valuation_date,
        "steps": params.steps,
        "bump_spot_rel": params.bump_spot_rel,
        "bump_vol_abs": params.bump_vol_abs,
        "bump_rate_abs": params.bump_rate_abs,
        "calendar_name": params.calendar,
    }


def _pnl_cg_kwargs(
    state: _MarketState,
    params: PnLAttributionGETRequest,
    valuation_date: date,
    base_price: float,
) -> dict[str, Any]:
    return {"base_price": base_price, **_pnl_pv_kwargs(state, params, valuation_date)}


async def run_greeks(
    params: GreeksRequest,
    price_vanilla_fn: Callable[..., GreeksOutput] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if price_vanilla_fn is None:
        price_vanilla_fn = _price_vanilla
    valuation_date = params.valuation_date or date.today()
    assert params.engine is not None
    async with with_evaluation_date(valuation_date):
        result = price_vanilla_fn(
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
            calendar_name=params.calendar,
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
    if params.calendar != DEFAULT_CALENDAR:
        inputs["calendar"] = params.calendar
    _add_non_default_bumps(inputs, params)
    return meta, inputs, result.model_dump()


async def run_impliedvol(
    params: ImpliedVolRequest,
    compute_implied_vol_fn: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if compute_implied_vol_fn is None:
        compute_implied_vol_fn = _compute_implied_vol
    valuation_date = params.valuation_date or date.today()
    assert params.engine is not None
    async with with_evaluation_date(valuation_date):
        result = compute_implied_vol_fn(
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
            calendar_name=params.calendar,
            verify_reprice=params.verify_reprice,
        )
    meta = _meta(params.engine, valuation_date)
    inputs: dict[str, Any] = {
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
    if params.calendar != DEFAULT_CALENDAR:
        inputs["calendar"] = params.calendar
    if params.accuracy != IV_SOLVER_DEFAULT_ACCURACY:
        inputs["accuracy"] = params.accuracy
    if params.max_iterations != IV_SOLVER_MAX_ITERATIONS:
        inputs["max_iterations"] = params.max_iterations
    if not params.verify_reprice:
        inputs["verify_reprice"] = False
    return meta, inputs, result.model_dump()


async def run_portfolio(
    payload: PortfolioRequest,
    price_vanilla_fn: Callable[..., GreeksOutput] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, float]]:
    if price_vanilla_fn is None:
        price_vanilla_fn = _price_vanilla
    valuation_date = payload.valuation_date or date.today()
    legs_out: list[dict[str, Any]] = []
    aggregate: dict[str, float] = {
        "price": 0.0,
        "delta": 0.0,
        "gamma": 0.0,
        "vega": 0.0,
        "theta": 0.0,
        "rho": 0.0,
        "charm": 0.0,
    }
    async with with_evaluation_date(valuation_date):
        for leg in payload.legs:
            assert leg.engine is not None
            result = price_vanilla_fn(
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
                calendar_name=leg.calendar,
            )
            row = {"id": leg.id, "engine": leg.engine, **result.model_dump()}
            legs_out.append(row)
            for greek in aggregate:
                val = getattr(result, greek)
                if not math.isfinite(val):
                    raise InvalidInputError(
                        f"Pricing produced non-finite {greek} for leg {leg.id}",
                        field=greek,
                    )
                aggregate[greek] += leg.qty * val
    meta = {
        "service_version": service_version,
        "quantlib_version": QUANTLIB_VERSION,
        "valuation_date": valuation_date.isoformat(),
    }
    return meta, legs_out, aggregate


async def run_pnl_attribution(
    params: PnLAttributionGETRequest,
    price_vanilla_fn: Callable[..., GreeksOutput] | None = None,
    compute_cross_greeks_fn: Callable[..., tuple[float, float]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if price_vanilla_fn is None:
        price_vanilla_fn = _price_vanilla
    if compute_cross_greeks_fn is None:
        compute_cross_greeks_fn = _compute_cross_greeks
    valuation_date_t_minus_1 = params.valuation_date_t_minus_1
    valuation_date_t = params.valuation_date_t
    method = params.method
    if valuation_date_t_minus_1 is None and valuation_date_t is None:
        valuation_date_t_minus_1 = date.today()
        valuation_date_t = date.today()
        calendar_days = 1
    elif valuation_date_t_minus_1 is not None and valuation_date_t is not None:
        calendar_days = max((valuation_date_t - valuation_date_t_minus_1).days, 1)
    else:
        raise InvalidInputError(
            "Provide both valuation_date_t_minus_1 and valuation_date_t, or omit both",
            field="valuation_date_t",
        )
    vanna_t_m1 = volga_t_m1 = vanna_t = volga_t = 0.0
    state_t_m1 = _market_state(params, "_t_minus_1")
    state_t = _market_state(params, "_t")
    async with with_evaluation_date(valuation_date_t_minus_1):
        greeks_t_minus_1 = price_vanilla_fn(
            **_pnl_pv_kwargs(state_t_m1, params, valuation_date_t_minus_1),
        )
        if params.cross_greeks:
            vanna_t_m1, volga_t_m1 = compute_cross_greeks_fn(
                **_pnl_cg_kwargs(
                    state_t_m1, params, valuation_date_t_minus_1, greeks_t_minus_1.price
                )
            )
    async with with_evaluation_date(valuation_date_t):
        greeks_t = price_vanilla_fn(
            **_pnl_pv_kwargs(state_t, params, valuation_date_t),
        )
        if params.cross_greeks and method == "average":
            vanna_t, volga_t = compute_cross_greeks_fn(
                **_pnl_cg_kwargs(state_t, params, valuation_date_t, greeks_t.price)
            )
    delta_s = params.s_t - params.s_t_minus_1
    delta_v_points = (params.v_t - params.v_t_minus_1) * 100.0
    delta_r_points = (params.r_t - params.r_t_minus_1) * 100.0
    delta_s_pct = delta_s / params.s_t_minus_1 * 100.0
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
        vanna_pnl_per_unit = vanna * delta_s_pct * delta_v_points
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
    outputs: dict[str, Any] = {
        "price_t_minus_1": greeks_t_minus_1.price,
        "price_t": greeks_t.price,
        "actual_pnl": actual_pnl,
        "delta_pnl": delta_pnl,
        "gamma_pnl": gamma_pnl,
        "vega_pnl": vega_pnl,
        "theta_pnl": theta_pnl,
        "rho_pnl": rho_pnl,
        "vanna_pnl": vanna_pnl_per_unit,
        "volga_pnl": volga_pnl_per_unit,
        "explained_pnl": explained_pnl,
        "residual_pnl": residual_pnl,
    }
    meta = {
        "service_version": service_version,
        "quantlib_version": QUANTLIB_VERSION,
        "valuation_date_t_minus_1": valuation_date_t_minus_1.isoformat(),
        "valuation_date_t": valuation_date_t.isoformat(),
        "method": method,
        "calendar_days": calendar_days,
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
    if params.steps != DEFAULT_STEPS:
        inputs["steps"] = params.steps
    if params.calendar != DEFAULT_CALENDAR:
        inputs["calendar"] = params.calendar
    expected_engine = "analytic" if params.style == "european" else "binomial_crr"
    if params.engine != expected_engine:
        inputs["engine"] = params.engine
    _add_non_default_bumps(inputs, params)
    if params.cross_greeks:
        inputs["cross_greeks"] = True

    return meta, inputs, outputs
