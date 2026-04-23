"""Vanna and volga calculator via uniform finite differences."""

import logging
import math
from datetime import date

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.constants import VOL_BUMP_CAP_FACTOR
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_CALENDAR,
    DEFAULT_STEPS,
    CalendarLiteral,
)
from deskpricer.pricing.engine import price_vanilla
from deskpricer.schemas import EngineLiteral


def compute_cross_greeks(
    base_price: float,
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    style: str,
    engine: EngineLiteral,
    valuation_date: date,
    steps: int = DEFAULT_STEPS,
    bump_spot_rel: float = DEFAULT_BUMP_SPOT_REL,
    bump_vol_abs: float = DEFAULT_BUMP_VOL_ABS,
    bump_rate_abs: float = DEFAULT_BUMP_RATE_ABS,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> tuple[float, float]:
    """Compute vanna and volga for a single market state.

    Unit conventions
    ----------------
    Vanna is returned as ∂²V / ∂S ∂σ  per **1% relative move in spot** per
    **1 vol-point** (1% absolute).  Numerically this is computed via a 4-point
    central cross difference.  The spot bump ``ds`` is a relative bump
    (``s * bump_spot_rel``), so the resulting vanna corresponds to a 1%
    relative spot move, not a $1 absolute move.

    Volga is returned as ∂²V / ∂σ²  per **(1 vol-point)²**.  Numerically this
    is a standard central second difference on vol space, again with the bump
    size cancelling in the limit.

    Both denominators use the same vol-point unit system, so the two Greeks
    are dimensionally consistent when combined in a vanna-volga PnL expansion:
        vanna_pnl = vanna * (ΔS / S * 100) * Δσ_points
        volga_pnl = 0.5 * volga * (Δσ_points)²
    """

    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if bump_spot_rel <= 0:
        raise InvalidInputError("bump_spot_rel must be positive", field="bump_spot_rel")
    if bump_vol_abs <= 0:
        raise InvalidInputError("bump_vol_abs must be positive", field="bump_vol_abs")

    # Cap the effective vol bump at v * VOL_BUMP_CAP_FACTOR to prevent negative vol on v - h_v,
    # matching the cap already applied in american.py vega computation.
    effective_bump_vol = min(bump_vol_abs, v * VOL_BUMP_CAP_FACTOR)
    if effective_bump_vol < bump_vol_abs:
        logging.getLogger("deskpricer").warning(
            "Cross-greeks vol bump auto-capped: bump_vol_abs=%.6f -> effective=%.6f (v=%.6f)",
            bump_vol_abs,
            effective_bump_vol,
            v,
        )
    if effective_bump_vol <= 0.0 or not math.isfinite(effective_bump_vol):
        raise InvalidInputError(
            "Vol bump underflowed to zero for cross-greeks; use larger vol or bump_vol_abs",
            field="bump_vol_abs",
        )

    ds = s * bump_spot_rel
    if ds <= 0.0 or not math.isfinite(ds):
        raise InvalidInputError(
            "Spot bump underflowed to zero for cross-greeks; use larger spot or bump_spot_rel",
            field="bump_spot_rel",
        )
    dv_points = effective_bump_vol * 100.0

    def _price(spot: float, vol: float):
        return price_vanilla(
            s=spot,
            k=k,
            t=t,
            r=r,
            q=q,
            v=vol,
            option_type=option_type,
            style=style,
            engine=engine,
            valuation_date=valuation_date,
            steps=steps,
            bump_spot_rel=bump_spot_rel,
            bump_vol_abs=bump_vol_abs,
            bump_rate_abs=bump_rate_abs,
            calendar_name=calendar_name,
        )

    # --- Volga: V(S,σ+Δσ) - 2V(S,σ) + V(S,σ-Δσ) over (Δσ)² ---
    # 2 extra pricing calls
    result_v_up = _price(s, v + effective_bump_vol)
    result_v_down = _price(s, v - effective_bump_vol)
    volga = (result_v_up.price - 2.0 * base_price + result_v_down.price) / (dv_points**2)

    # --- Vanna: 4-point cross difference ---
    # 4 extra pricing calls
    result_pp = _price(s + ds, v + effective_bump_vol)
    result_pm = _price(s + ds, v - effective_bump_vol)
    result_mp = _price(s - ds, v + effective_bump_vol)
    result_mm = _price(s - ds, v - effective_bump_vol)
    vanna = (result_pp.price - result_pm.price - result_mp.price + result_mm.price) / (
        4.0 * ds * dv_points
    )

    if not math.isfinite(vanna) or not math.isfinite(volga):
        raise InvalidInputError(
            "Cross-greeks computation produced non-finite result; "
            "inputs may be at numerical limits",
            field="v",
        )

    return vanna, volga
