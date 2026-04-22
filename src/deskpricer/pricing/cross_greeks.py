"""Vanna and volga calculator via uniform finite differences."""

from datetime import date

import math

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_STEPS,
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
) -> tuple[float, float]:
    """Compute vanna and volga for a single market state.

    Vanna  = ∂²V/∂S∂σ   (per $1 per 1% vol point)
    Volga  = ∂²V/∂σ²    (per (1%)²)

    Both are calculated via central finite differences using the
    existing bump_spot_rel and bump_vol_abs conventions.
    """
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if v <= bump_vol_abs:
        raise InvalidInputError(
            "volatility must be greater than bump_vol_abs for cross-greeks computation",
            field="v",
        )
    if bump_spot_rel <= 0:
        raise InvalidInputError("bump_spot_rel must be positive", field="bump_spot_rel")
    if bump_vol_abs <= 0:
        raise InvalidInputError("bump_vol_abs must be positive", field="bump_vol_abs")

    ds = s * bump_spot_rel
    if ds <= 0.0 or not math.isfinite(ds):
        raise InvalidInputError(
            "Spot bump underflowed to zero for cross-greeks; use larger spot or bump_spot_rel",
            field="bump_spot_rel",
        )
    dv_points = bump_vol_abs * 100.0
    if dv_points <= 0.0 or not math.isfinite(dv_points):
        raise InvalidInputError(
            "Vol bump underflowed to zero for cross-greeks; use larger bump_vol_abs",
            field="bump_vol_abs",
        )

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
        )

    # --- Volga: V(S,σ+Δσ) - 2V(S,σ) + V(S,σ-Δσ) over (Δσ)² ---
    # 2 extra pricing calls
    result_v_up = _price(s, v + bump_vol_abs)
    result_v_down = _price(s, v - bump_vol_abs)
    volga = (result_v_up.price - 2.0 * base_price + result_v_down.price) / (dv_points**2)

    # --- Vanna: 4-point cross difference ---
    # 4 extra pricing calls
    result_pp = _price(s + ds, v + bump_vol_abs)
    result_pm = _price(s + ds, v - bump_vol_abs)
    result_mp = _price(s - ds, v + bump_vol_abs)
    result_mm = _price(s - ds, v - bump_vol_abs)
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
