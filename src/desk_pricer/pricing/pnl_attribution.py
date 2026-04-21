"""PnL attribution calculator."""

from datetime import date
from typing import Any

from desk_pricer.pricing.engine import price_vanilla
from desk_pricer.schemas import GreeksOutput, PnLLegInput


def _compute_attribution_buckets(
    leg: PnLLegInput,
    greeks_t_minus_1: GreeksOutput,
    greeks_t: GreeksOutput,
    calendar_days: int,
    method: str,
) -> dict[str, Any]:
    """Core attribution math. Returns per-unit PnL buckets."""
    delta_s = leg.t.s - leg.t_minus_1.s
    delta_v_points = (leg.t.v - leg.t_minus_1.v) * 100.0  # vol change in percentage points
    delta_r_points = (leg.t.r - leg.t_minus_1.r) * 100.0  # rate change in percentage points

    # Delta & Gamma: always backward-looking (t-1 Greeks)
    delta_pnl = greeks_t_minus_1.delta * delta_s
    gamma_pnl = 0.5 * greeks_t_minus_1.gamma * (delta_s ** 2)

    # Vega: backward or average (vega is per 1 vol point)
    if method == "average":
        vega_pnl = ((greeks_t_minus_1.vega + greeks_t.vega) / 2.0) * delta_v_points
    else:
        vega_pnl = greeks_t_minus_1.vega * delta_v_points

    # Theta: always backward-looking (per calendar day)
    theta_pnl = greeks_t_minus_1.theta * calendar_days

    # Rho: backward or average (rho is per 1% rate point)
    if method == "average":
        rho_pnl = ((greeks_t_minus_1.rho + greeks_t.rho) / 2.0) * delta_r_points
    else:
        rho_pnl = greeks_t_minus_1.rho * delta_r_points

    actual_pnl = greeks_t.price - greeks_t_minus_1.price
    explained_pnl = delta_pnl + gamma_pnl + vega_pnl + theta_pnl + rho_pnl
    residual_pnl = actual_pnl - explained_pnl

    return {
        "id": leg.id,
        "qty": leg.qty,
        "price_t_minus_1": greeks_t_minus_1.price,
        "price_t": greeks_t.price,
        "actual_pnl": actual_pnl,
        "delta_pnl": delta_pnl,
        "gamma_pnl": gamma_pnl,
        "vega_pnl": vega_pnl,
        "theta_pnl": theta_pnl,
        "rho_pnl": rho_pnl,
        "explained_pnl": explained_pnl,
        "residual_pnl": residual_pnl,
    }


def compute_pnl_attribution_leg(
    leg: PnLLegInput,
    valuation_date_t_minus_1: date,
    valuation_date_t: date,
    method: str,
) -> dict[str, Any]:
    """Compute PnL attribution for a single leg.

    Prices the leg at t-1 and t, then applies Greek-based attribution.
    All PnL figures are **per-unit** (qty applied afterward by the caller).
    """
    greeks_t_minus_1 = price_vanilla(
        s=leg.t_minus_1.s,
        k=leg.k,
        t=leg.t_minus_1.t,
        r=leg.t_minus_1.r,
        q=leg.t_minus_1.q,
        v=leg.t_minus_1.v,
        option_type=leg.type,
        style=leg.style,
        engine=leg.engine,
        valuation_date=valuation_date_t_minus_1,
        steps=leg.steps,
        bump_spot_rel=leg.bump_spot_rel,
        bump_vol_abs=leg.bump_vol_abs,
        bump_rate_abs=leg.bump_rate_abs,
    )

    greeks_t = price_vanilla(
        s=leg.t.s,
        k=leg.k,
        t=leg.t.t,
        r=leg.t.r,
        q=leg.t.q,
        v=leg.t.v,
        option_type=leg.type,
        style=leg.style,
        engine=leg.engine,
        valuation_date=valuation_date_t,
        steps=leg.steps,
        bump_spot_rel=leg.bump_spot_rel,
        bump_vol_abs=leg.bump_vol_abs,
        bump_rate_abs=leg.bump_rate_abs,
    )

    calendar_days = (valuation_date_t - valuation_date_t_minus_1).days
    return _compute_attribution_buckets(leg, greeks_t_minus_1, greeks_t, calendar_days, method)


def compute_pnl_attribution_leg_from_results(
    leg: PnLLegInput,
    greeks_t_minus_1: GreeksOutput,
    greeks_t: GreeksOutput,
    valuation_date_t_minus_1: date,
    valuation_date_t: date,
    method: str,
) -> dict[str, Any]:
    """Compute PnL attribution from pre-computed Greeks.

    Used by the endpoint when Greeks have already been priced inside the lock.
    """
    calendar_days = (valuation_date_t - valuation_date_t_minus_1).days
    return _compute_attribution_buckets(leg, greeks_t_minus_1, greeks_t, calendar_days, method)
